/**
 * API contract definitions and TypeScript interfaces for TechRadar Brain API.
 * Spec: 02 §5.14, 05 §3, SEC-27, SEC-41, SEC-56, SEC-57.
 */

export interface Citation {
  source_id: string;
  source_title: string;
  source_url?: string;
  page_number?: number;
  timestamp_s?: number;
  excerpt?: string;
}

export interface AskRequest {
  question: string;
  verified_only?: boolean;
  chat_id?: number;
  document_ids?: string[];
}

export interface AskResponse {
  answer_id: number;
  status: "queued" | "pending" | "answered" | "not_found" | "needs_review" | string;
  answer?: string | null;
  citations?: Citation[];
  verified_only?: boolean;
  created_at?: string;
}

export interface StatusResponse {
  status: string;
  version: string;
  env: string;
  uptime_s?: number;
  loaded_models?: string[];
}

export interface ConfirmationTicketRequest {
  action: string;
  payload: Record<string, unknown>;
  ttl_s?: number;
  session_id?: string;
}

export interface ConfirmationTicketResponse {
  ticket_id: string;
  action: string;
  payload_hash: string;
  created_at: number;
  expires_at: number;
  signature: string;
  result?:
    | "ok"
    | "expired"
    | "used"
    | "wrong_session"
    | "tampered"
    | "cancelled"
    | "unknown"
    | string;
  message?: string | null;
}

export interface UploadResponse {
  filename: string;
  size_bytes: number;
  status: "uploaded" | "queued" | "rejected" | string;
  sha256?: string;
  path?: string;
  error?: string;
}

export interface PingResponse {
  pong: boolean;
}

export interface HealthzResponse {
  ok: boolean;
}

export interface TechRadarClientOptions {
  /**
   * Base URL of the TechRadar API service (e.g. "http://127.0.0.1:8000" or Tailscale URL).
   */
  baseUrl?: string;

  /**
   * Optional service secret token for X-Service-Token / Bearer authorization (SEC-27).
   */
  serviceToken?: string;

  /**
   * Optional owner login for X-TR-User / Tailscale-User-Login verification (SEC-41).
   */
  ownerLogin?: string;

  /**
   * Optional custom fetch implementation (useful in test or server environments).
   */
  fetchFn?: typeof fetch;
}
