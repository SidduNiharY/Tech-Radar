/**
 * TechRadar Brain Security Module.
 * Implements SEC-28, SEC-41, SEC-51, SEC-54.
 */

/**
 * Builds exact Content Security Policy string from SEC-28 spec with request nonce.
 */
export function buildCsp(nonce: string): string {
  return `default-src 'self'; script-src 'self' 'nonce-${nonce}' 'strict-dynamic'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; media-src 'self' blob:; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'`;
}

/**
 * Builds standard security headers map with Content-Security-Policy and protective directives.
 */
export function securityHeaders(nonce: string): Record<string, string> {
  return {
    "Content-Security-Policy": buildCsp(nonce),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Strict-Transport-Security": "max-age=31536000",
  };
}

/**
 * Validates Tailscale owner identity from request headers (SEC-41).
 * Compares `tailscale-user-login` case-insensitively and trimmed against `ownerLogin`.
 * Returns false if header is missing, empty, or does not match ownerLogin.
 */
export function isOwner(
  headers: Headers | Record<string, string | null | undefined> | undefined | null,
  ownerLogin: string
): boolean {
  if (!headers || !ownerLogin) {
    return false;
  }

  const normalizedOwner = ownerLogin.trim().toLowerCase();
  if (!normalizedOwner) {
    return false;
  }

  let rawHeader: string | null | undefined = null;

  if (typeof (headers as Headers).get === "function") {
    rawHeader = (headers as Headers).get("tailscale-user-login");
  } else {
    const record = headers as Record<string, string | null | undefined>;
    for (const [key, value] of Object.entries(record)) {
      if (key.toLowerCase() === "tailscale-user-login") {
        rawHeader = value;
        break;
      }
    }
  }

  if (typeof rawHeader !== "string") {
    return false;
  }

  const normalizedHeader = rawHeader.trim().toLowerCase();
  return normalizedHeader.length > 0 && normalizedHeader === normalizedOwner;
}

/**
 * Validates whether the incoming Host matches allowed hosts list (SEC-51).
 */
export function isAllowedHost(
  host: string | null | undefined,
  allowed: string[]
): boolean {
  if (!host) {
    return false;
  }
  const cleanHost = host.trim().toLowerCase();
  return allowed.some((a) => a.trim().toLowerCase() === cleanHost);
}

/**
 * Enforces cross-site request forgery protection (SEC-54).
 * Safe methods (GET, HEAD, OPTIONS) are permitted.
 * Mutating methods require matching origin/referer and x-tr-request header.
 */
export function csrfOk(
  method: string,
  headers: Headers | Record<string, string | null | undefined> | undefined | null,
  publicOrigin: string
): boolean {
  const upper = method.toUpperCase();
  if (upper === "GET" || upper === "HEAD" || upper === "OPTIONS") {
    return true;
  }

  if (!headers || !publicOrigin) {
    return false;
  }

  const getHeader = (name: string): string | null => {
    if (typeof (headers as Headers).get === "function") {
      return (headers as Headers).get(name);
    }
    const record = headers as Record<string, string | null | undefined>;
    const target = name.toLowerCase();
    for (const [k, v] of Object.entries(record)) {
      if (k.toLowerCase() === target) {
        return typeof v === "string" ? v : null;
      }
    }
    return null;
  };

  const trRequest = getHeader("x-tr-request");
  if (trRequest !== "1") {
    return false;
  }

  const origin = getHeader("origin");
  const cleanOrigin = publicOrigin.trim().replace(/\/+$/, "").toLowerCase();

  if (origin) {
    return origin.trim().replace(/\/+$/, "").toLowerCase() === cleanOrigin;
  }

  const referer = getHeader("referer");
  if (referer) {
    return referer.toLowerCase().startsWith(`${cleanOrigin}/`);
  }

  return false;
}

/**
 * SEC-28: may this Markdown link become a real <a href>?
 *
 * Same-site paths ("/x") and in-page anchors ("#x") are fine. "//host" and
 * "/\host" are not same-site: browsers treat both as a link to another site,
 * and they drop tabs and newlines inside URLs first, so "/\t/host" is the
 * same as "//host". Outside links pass only with a listed prefix.
 */
export function isSafeLink(url: string, allowedPrefixes: readonly string[]): boolean {
  const u = url.replace(/[\t\n\r]/g, "");
  if (u.startsWith("#")) return true;
  if (u.startsWith("/")) return u[1] !== "/" && u[1] !== "\\";
  return allowedPrefixes.some((p) => p.length > 0 && u.startsWith(p));
}
