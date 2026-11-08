/**
 * Typed client for TechRadar Brain API.
 * Spec: 02 §5.14, 05 §3, SEC-27, SEC-41, SEC-56, SEC-57.
 */

import type {
  AskRequest,
  AskResponse,
  ConfirmationTicketRequest,
  ConfirmationTicketResponse,
  HealthzResponse,
  PingResponse,
  StatusResponse,
  TechRadarClientOptions,
  UploadResponse,
} from "./types";

declare const process: { env?: Record<string, string | undefined> } | undefined;

export class TechRadarApiError extends Error {
  public readonly status: number;
  public readonly statusText: string;
  public readonly body: unknown;

  constructor(status: number, statusText: string, body: unknown) {
    const message =
      typeof body === "string"
        ? body
        : typeof body === "object" && body !== null && "detail" in body
          ? String((body as { detail: unknown }).detail)
          : JSON.stringify(body);
    super(`API error ${status} (${statusText}): ${message}`);
    this.name = "TechRadarApiError";
    this.status = status;
    this.statusText = statusText;
    this.body = body;
  }
}

export class TechRadarClient {
  private readonly baseUrl: string;
  private readonly serviceToken?: string;
  private readonly ownerLogin?: string;
  private readonly fetchFn: typeof fetch;

  constructor(options: TechRadarClientOptions = {}) {
    const rawUrl =
      options.baseUrl ||
      (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) ||
      (typeof process !== "undefined" && process.env?.TECHRADAR_API_URL) ||
      "http://127.0.0.1:8000";

    // Enforce valid URL structure and strip trailing slashes
    try {
      const parsed = new URL(rawUrl);
      this.baseUrl = parsed.origin + (parsed.pathname === "/" ? "" : parsed.pathname).replace(/\/+$/, "");
    } catch {
      throw new Error(`Invalid TechRadar API base URL: ${rawUrl}`);
    }

    this.serviceToken = options.serviceToken;
    this.ownerLogin = options.ownerLogin;

    if (options.fetchFn) {
      this.fetchFn = options.fetchFn;
    } else if (typeof fetch !== "undefined") {
      this.fetchFn = fetch.bind(globalThis);
    } else {
      throw new Error("No fetch implementation available. Provide fetchFn in TechRadarClientOptions.");
    }
  }

  /**
   * Resolve default request headers with optional bearer token and owner identity (SEC-27, SEC-41).
   */
  private buildHeaders(customHeaders: Record<string, string> = {}): Record<string, string> {
    const headers: Record<string, string> = { ...customHeaders };

    if (this.serviceToken) {
      headers["X-Service-Token"] = this.serviceToken;
      headers["Authorization"] = `Bearer ${this.serviceToken}`;
    }

    if (this.ownerLogin) {
      headers["X-TR-User"] = this.ownerLogin;
      headers["Tailscale-User-Login"] = this.ownerLogin;
    }

    return headers;
  }

  /**
   * Internal typed HTTP request helper.
   */
  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const cleanPath = path.startsWith("/") ? path : `/${path}`;
    const url = `${this.baseUrl}${cleanPath}`;

    const headers = this.buildHeaders(
      (init.headers as Record<string, string>) || {}
    );

    const response = await this.fetchFn(url, {
      ...init,
      headers,
    });

    if (!response.ok) {
      let errorBody: unknown;
      try {
        errorBody = await response.json();
      } catch {
        try {
          errorBody = await response.text();
        } catch {
          errorBody = response.statusText;
        }
      }
      throw new TechRadarApiError(response.status, response.statusText, errorBody);
    }

    return (await response.json()) as T;
  }

  /**
   * Check unauthenticated health endpoint (/healthz).
   */
  public async healthz(): Promise<HealthzResponse> {
    return this.request<HealthzResponse>("/healthz", {
      method: "GET",
    });
  }

  /**
   * Ping API service (/v1/ping).
   */
  public async ping(): Promise<PingResponse> {
    return this.request<PingResponse>("/v1/ping", {
      method: "GET",
    });
  }

  /**
   * Retrieve API service status and loaded model info (/v1/status).
   */
  public async getStatus(): Promise<StatusResponse> {
    return this.request<StatusResponse>("/v1/status", {
      method: "GET",
    });
  }

  /**
   * Submit a question to the Ask pipeline (/v1/ask).
   */
  public async ask(req: AskRequest): Promise<AskResponse> {
    return this.request<AskResponse>("/v1/ask", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(req),
    });
  }

  /**
   * Request creation or confirmation of a one-time action ticket (/v1/tickets) (SEC-56).
   */
  public async createTicket(
    req: ConfirmationTicketRequest
  ): Promise<ConfirmationTicketResponse> {
    const extraHeaders: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (req.session_id) {
      extraHeaders["X-TR-Session"] = req.session_id;
    }

    return this.request<ConfirmationTicketResponse>("/v1/tickets", {
      method: "POST",
      headers: extraHeaders,
      body: JSON.stringify(req),
    });
  }

  /**
   * Upload library document via multipart form data (/v1/upload) (SEC-57, D48).
   * Note: Does not set Content-Type header so fetch can generate multipart boundary.
   */
  public async upload(formData: FormData): Promise<UploadResponse> {
    return this.request<UploadResponse>("/v1/upload", {
      method: "POST",
      body: formData,
    });
  }
}
