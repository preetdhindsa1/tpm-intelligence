import { afterEach, describe, expect, it, vi } from "vitest";
import { act, messageFor, serverGet } from "./api-http";

afterEach(() => vi.unstubAllGlobals());

describe("API errors and the signed route", () => {
  it("maps 401, 403, 404, 409 and 422, and never repeats a login", () => {
    expect(messageFor(401, "sign in with GitHub to do this")).toBe("Sign in to do this.");
    expect(messageFor(403, "octocat is not an approver")).toBe("Only an approver can change this. The page is read-only.");
    expect(messageFor(404, "unknown RAID item 9")).toBe("Not found.");
    expect(messageFor(409, "a rejected item cannot be decided again")).toBe("This item was already rejected, so it cannot be changed.");
    expect(messageFor(422, [{ msg: "too short" }])).toBe("That change was not accepted. A reason or note needs at least 3 characters.");
    expect(messageFor(422, "decision must be go, no_go or defer")).toBe("decision must be go, no_go or defer");
  });

  it("GETs the API and POSTs actions through /api/act", async () => {
    const fetch = vi.fn<(url: string) => Promise<Response>>(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    await expect(serverGet("/raid?project=kubernetes&release=v1.38")).resolves.toEqual({ ok: true });
    expect(String(fetch.mock.calls[0][0])).toContain("/raid?project=kubernetes&release=v1.38");
    await act("/raid/4/confirm", {});
    expect(String(fetch.mock.calls[1][0])).toBe("/api/act/raid/4/confirm");
    fetch.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "octocat is not an approver" }), { status: 403 }));
    await expect(act("/raid/4/reject", { reason: "no" })).rejects.toMatchObject({ status: 403 });
  });
});
