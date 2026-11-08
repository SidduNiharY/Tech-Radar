import { describe, it } from "node:test";
import assert from "node:assert";
import {
  buildCsp,
  csrfOk,
  isAllowedHost,
  isOwner,
  securityHeaders,
} from "./security";

describe("buildCsp", () => {
  it("injects nonce and exact spec directives", () => {
    const csp = buildCsp("test-nonce-abc-123");

    // Nonce insertion
    assert.ok(csp.includes("'nonce-test-nonce-abc-123'"));

    // Key directives from SEC-28
    assert.ok(csp.includes("default-src 'self'"));
    assert.ok(csp.includes("script-src 'self' 'nonce-test-nonce-abc-123' 'strict-dynamic'"));
    assert.ok(csp.includes("style-src 'self' 'unsafe-inline'"));
    assert.ok(csp.includes("img-src 'self' data: blob:"));
    assert.ok(csp.includes("font-src 'self'"));
    assert.ok(csp.includes("connect-src 'self'"));
    assert.ok(csp.includes("media-src 'self' blob:"));
    assert.ok(csp.includes("worker-src 'self' blob:"));
    assert.ok(csp.includes("frame-ancestors 'none'"));
    assert.ok(csp.includes("base-uri 'self'"));
    assert.ok(csp.includes("form-action 'self'"));
    assert.ok(csp.includes("object-src 'none'"));

    // Exact string match check
    const expected =
      "default-src 'self'; script-src 'self' 'nonce-test-nonce-abc-123' 'strict-dynamic'; " +
      "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; " +
      "connect-src 'self'; media-src 'self' blob:; worker-src 'self' blob:; " +
      "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'";
    assert.strictEqual(csp, expected);
  });
});

describe("securityHeaders", () => {
  it("includes all required security headers", () => {
    const headers = securityHeaders("sample-nonce");

    assert.strictEqual(
      headers["Content-Security-Policy"],
      buildCsp("sample-nonce")
    );
    assert.strictEqual(headers["Referrer-Policy"], "no-referrer");
    assert.strictEqual(headers["X-Content-Type-Options"], "nosniff");
    assert.strictEqual(
      headers["Permissions-Policy"],
      "microphone=(self), camera=(), geolocation=(), payment=(), usb=()"
    );
    assert.strictEqual(headers["Cross-Origin-Opener-Policy"], "same-origin");
    assert.strictEqual(headers["Strict-Transport-Security"], "max-age=31536000");
  });
});

describe("isOwner", () => {
  it("matches owner case-insensitively and trimmed with Headers instance", () => {
    const headers = new Headers({
      "tailscale-user-login": "Me@Example.com ",
    });
    assert.strictEqual(isOwner(headers, "me@example.com"), true);
  });

  it("matches owner case-insensitively and trimmed with Record", () => {
    const headers = {
      "Tailscale-User-Login": "  OWNER@LOCAL  ",
    };
    assert.strictEqual(isOwner(headers, "owner@local"), true);
  });

  it("rejects mismatched identity", () => {
    const headers = new Headers({
      "tailscale-user-login": "attacker@evil.com",
    });
    assert.strictEqual(isOwner(headers, "owner@local"), false);
  });

  it("rejects missing header", () => {
    const headers = new Headers();
    assert.strictEqual(isOwner(headers, "owner@local"), false);
  });

  it("rejects null or empty inputs", () => {
    assert.strictEqual(isOwner(null, "owner@local"), false);
    assert.strictEqual(isOwner(undefined, "owner@local"), false);
    assert.strictEqual(isOwner(new Headers(), ""), false);
    assert.strictEqual(
      isOwner(new Headers({ "tailscale-user-login": "   " }), "owner@local"),
      false
    );
  });
});

describe("isAllowedHost", () => {
  const allowed = ["brain.tailnet.ts.net", "127.0.0.1:3000", "localhost:3000"];

  it("accepts allowed hosts case-insensitively", () => {
    assert.strictEqual(isAllowedHost("brain.tailnet.ts.net", allowed), true);
    assert.strictEqual(isAllowedHost("BRAIN.TAILNET.TS.NET", allowed), true);
    assert.strictEqual(isAllowedHost("127.0.0.1:3000", allowed), true);
  });

  it("rejects disallowed or missing hosts", () => {
    assert.strictEqual(isAllowedHost("evil.example", allowed), false);
    assert.strictEqual(isAllowedHost(null, allowed), false);
    assert.strictEqual(isAllowedHost("", allowed), false);
  });
});

describe("csrfOk", () => {
  const publicOrigin = "https://brain.tailnet.ts.net";

  it("permits safe HTTP methods without origin check", () => {
    assert.strictEqual(csrfOk("GET", new Headers(), publicOrigin), true);
    assert.strictEqual(csrfOk("HEAD", new Headers(), publicOrigin), true);
    assert.strictEqual(csrfOk("OPTIONS", new Headers(), publicOrigin), true);
  });

  it("permits mutating requests with valid origin and x-tr-request: 1", () => {
    const headers = new Headers({
      "x-tr-request": "1",
      origin: "https://brain.tailnet.ts.net",
    });
    assert.strictEqual(csrfOk("POST", headers, publicOrigin), true);
  });

  it("permits mutating requests with valid referer and x-tr-request: 1", () => {
    const headers = new Headers({
      "x-tr-request": "1",
      referer: "https://brain.tailnet.ts.net/ask",
    });
    assert.strictEqual(csrfOk("POST", headers, publicOrigin), true);
  });

  it("rejects mutating requests missing x-tr-request", () => {
    const headers = new Headers({
      origin: "https://brain.tailnet.ts.net",
    });
    assert.strictEqual(csrfOk("POST", headers, publicOrigin), false);
  });

  it("rejects mutating requests from untrusted origin", () => {
    const headers = new Headers({
      "x-tr-request": "1",
      origin: "https://evil.example",
    });
    assert.strictEqual(csrfOk("POST", headers, publicOrigin), false);
  });
});
