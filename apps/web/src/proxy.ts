import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { isOwner, securityHeaders } from "./lib/security";

/**
 * TechRadar Brain Security Proxy Middleware (SEC-28, SEC-41).
 *
 * 1. Extracts `tailscale-user-login`.
 * 2. Generates crypto random UUID nonce (base64 encoded).
 * 3. Enforces owner identity; returns 403 Forbidden if missing or non-matching.
 * 4. Appends all security headers with nonce and forwards `x-nonce`.
 */
export function proxy(request: NextRequest): NextResponse {
  const ownerLogin =
    process.env.OWNER_LOGIN ||
    process.env.TECHRADAR_OWNER_LOGIN ||
    "owner@local";

  const isDevBypass =
    process.env.NODE_ENV === "development" &&
    process.env.DEV_BYPASS_AUTH === "1";

  // Validate owner identity from tailscale-user-login header (SEC-41)
  if (!isDevBypass && !isOwner(request.headers, ownerLogin)) {
    return new NextResponse(
      JSON.stringify({ error: "Forbidden: Tailscale owner identity required" }),
      {
        status: 403,
        headers: {
          "Content-Type": "application/json",
          "X-Content-Type-Options": "nosniff",
        },
      }
    );
  }

  // Generate cryptographically random base64 nonce (SEC-28)
  const nonce = btoa(crypto.randomUUID());

  // Forward x-nonce header to Server Components
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);

  const response = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });

  // Append security headers including Content-Security-Policy with nonce
  const secHeaders = securityHeaders(nonce);
  for (const [key, value] of Object.entries(secHeaders)) {
    response.headers.set(key, value);
  }
  response.headers.set("x-nonce", nonce);

  return response;
}

export default proxy;

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
