// Load test (#258): two tenants reading at once, plus a burst of signed GitHub webhooks.
//
//   k6 run -e API=http://localhost:8100 -e HOOKS=http://localhost:8180 \
//     -e SECRET=<TPM_ACTION_SECRET> -e HOOK_SECRET=<GITHUB_WEBHOOK_SECRET> \
//     -e MODE=two scripts/load/two_tenants.js
//
// MODE=burst sends only the webhooks (to watch a stall with a probe). MODE=one runs only the demo reads (the 2026-11-24 profile), as a baseline on the same
// machine. MODE=two adds the second tenant's signed reads and the webhook burst.
// The reads are the pages of docs/results/load-test-cloud-20261124.json. Webhook PRs are
// numbered from 990000 with a marker title, so a leak into the other tenant is detectable:
// the script fails a check if the marker ever appears in a second-tenant response.
import crypto from "k6/crypto";
import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";

const API = __ENV.API || "http://localhost:8100";
const HOOKS = __ENV.HOOKS || "http://localhost:8180";
const SECRET = __ENV.SECRET || "";
const HOOK_SECRET = __ENV.HOOK_SECRET || "";
const MODE = __ENV.MODE || "two";
const TENANT = __ENV.TENANT || "acme";
const LOGIN = __ENV.LOGIN || "loadtest";
export const MARKER = "LOADTEST-MARKER";
const PAGES = [
  "/releases",
  "/releases/v1.38/summary",
  "/releases/v1.38/features",
  "/releases/v1.38/dependencies",
  "/releases/4.5.0/features",
];
const leaks = new Counter("cross_tenant_leaks");

const reads = (exec) => ({
  executor: "ramping-vus",
  exec,
  startVUs: 0,
  stages: [
    { duration: "10s", target: 10 },
    { duration: "60s", target: 10 },
    { duration: "10s", target: 20 },
    { duration: "60s", target: 20 },
  ],
});

const scenarios = MODE === "burst" ? {} : { demo: reads("demoReads") };
if (MODE === "two" || MODE === "burst") {
  if (MODE === "two") scenarios.second = reads("secondReads");
  scenarios.webhooks = {
    executor: "constant-arrival-rate",
    exec: "webhook",
    rate: 20,
    timeUnit: "1s",
    duration: "30s",
    startTime: MODE === "burst" ? "0s" : "60s",
    preAllocatedVUs: 20,
  };
}

export const options = {
  scenarios,
  // Per-tenant and per-page submetrics, so the summary shows where time goes.
  thresholds: Object.fromEntries([
    ["cross_tenant_leaks", ["count==0"]],
    ...["demo", "second", "webhook"].map((t) => [`http_req_duration{tenant:${t}}`, ["max>=0"]]),
    ...PAGES.map((p) => [`http_req_duration{page:${p}}`, ["max>=0"]]),
  ]),
  summaryTrendStats: ["med", "p(95)", "max"],
};

function signed(method, path, body) {
  const ts = String(Math.floor(Date.now() / 1000));
  const digest = crypto.sha256(body, "hex");
  const message = [LOGIN, ts, method, path, digest, TENANT].join("\n");
  return {
    "x-tpm-user": LOGIN,
    "x-tpm-time": ts,
    "x-tpm-tenant": TENANT,
    "x-tpm-signature-version": "2",
    "x-tpm-signature": crypto.hmac("sha256", SECRET, message, "hex"),
  };
}

export function demoReads() {
  for (const path of PAGES) {
    const res = http.get(`${API}${path}`, { tags: { tenant: "demo", page: path } });
    check(res, { "demo 200": (r) => r.status === 200 });
  }
  sleep(1);
}

export function secondReads() {
  for (const path of PAGES) {
    const res = http.get(`${API}${path}`, {
      headers: signed("GET", path, ""),
      tags: { tenant: "second", page: path },
    });
    check(res, { "second 200": (r) => r.status === 200 });
    if (res.body && res.body.includes(MARKER)) leaks.add(1);
  }
  sleep(1);
}

export function webhook() {
  const n = 990000 + (__ITER % 100000);
  const at = new Date().toISOString();
  const body = JSON.stringify({
    action: "synchronize",
    repository: { full_name: "kubernetes/kubernetes" },
    pull_request: {
      number: n,
      title: `${MARKER} ${n}`,
      body: "",
      state: "open",
      user: { login: "load-test-bot" },
      labels: [{ name: "sig/node" }],
      base: { ref: "master" },
      head: { sha: crypto.sha1(`${n}-${at}`, "hex"), ref: "load" },
      created_at: at,
      updated_at: at,
      html_url: `https://github.com/kubernetes/kubernetes/pull/${n}`,
    },
  });
  const sig = "sha256=" + crypto.hmac("sha256", HOOK_SECRET, body, "hex");
  const res = http.post(`${HOOKS}/github`, body, {
    headers: {
      "Content-Type": "application/json",
      "X-GitHub-Event": "pull_request",
      "X-GitHub-Delivery": `load-${__VU}-${__ITER}-${Date.now()}`,
      "X-Hub-Signature-256": sig,
    },
    tags: { tenant: "webhook" },
  });
  check(res, { "webhook 202": (r) => r.status === 202 });
}
