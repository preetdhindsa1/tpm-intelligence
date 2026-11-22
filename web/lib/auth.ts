// Sign-in with GitHub (next-auth 4, stable; ADR-0016). The session carries the GitHub
// login, which the web server signs onto actions it forwards to the API.
import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import GitHubProvider from "next-auth/providers/github";

type Env = Record<string, string | undefined>;

/** The "sign in as" form for testing without GitHub: local mode only, never deployed. */
export function devLoginEnabled(env: Env = process.env): boolean {
  return env.AUTH_DEV_LOGIN === "true" && env.AUTH_MODE === "local";
}

/** A setting that is present and not the deploy placeholder (ADR-0017). */
const set = (v: string | undefined) => Boolean(v && v.trim() && v.trim() !== "unconfigured");

export function githubEnabled(env: Env = process.env): boolean {
  return set(env.AUTH_GITHUB_ID) && set(env.AUTH_GITHUB_SECRET);
}

const LOGIN = /^[a-z\d](?:[a-z\d-]{0,38})$/i; // GitHub login rules

export function authOptions(env: Env = process.env): NextAuthOptions {
  const providers: NextAuthOptions["providers"] = [];
  if (githubEnabled(env)) {
    // Identity only: no repository scopes are requested.
    providers.push(GitHubProvider({ clientId: env.AUTH_GITHUB_ID!, clientSecret: env.AUTH_GITHUB_SECRET!, authorization: { params: { scope: "read:user" } } }));
  }
  if (devLoginEnabled(env)) {
    providers.push(
      CredentialsProvider({
        id: "dev",
        name: "Development login (local only)",
        credentials: { login: { label: "GitHub login", type: "text" } },
        authorize: async (c) => (c?.login && LOGIN.test(c.login) ? { id: c.login, name: c.login } : null),
      }),
    );
  }
  return {
    secret: env.AUTH_SECRET,
    session: { strategy: "jwt" },
    providers,
    callbacks: {
      jwt: async ({ token, profile, user }) => {
        const login = (profile as { login?: string } | undefined)?.login ?? user?.name;
        if (login) token.login = login.toLowerCase();
        return token;
      },
      session: async ({ session, token }) => ({ ...session, login: (token.login as string | undefined) ?? null }),
    },
  };
}

export type TpmSession = { login: string | null } | null;
