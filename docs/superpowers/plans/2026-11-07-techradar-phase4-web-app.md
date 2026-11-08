# TechRadar Brain Phase 4: Web App v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A professional Next.js web app (Today, Ask, Library with file uploads, Practice, Security, Settings, read-only Models), reachable only from my devices through Tailscale, with host and cross-site request checks and one-time confirmation tickets for every confirm step. It ends with `make gate-4`.

**Architecture:**
- **API:** FastAPI (`api`) is model-free and talks JSON only. It queues `ask` jobs for the worker and serves data from Postgres.
- **Web:** Next.js (`web`) is the backend-for-frontend.
  - Its proxy checks the Tailscale identity header and sets a strict CSP with a nonce.
  - Server-only code calls the API with a service token.
  - It turns answers into the AI SDK UI message stream.
- **Network:** the browser never reaches the API. `web` is published on `127.0.0.1:3000` from a no-egress `edge` network, and the host's Tailscale Serve provides HTTPS.
- **Added 2026-11-08:** the proxy also refuses unknown `Host` headers and cross-site requests (SEC-51, SEC-54). Confirm steps use one-time tickets stored in `pending_actions` (SEC-56, D43). The Security screen reads the host alerter's log read-only. Files uploaded on the Library screen go into `data/library-uploads` and through the Intake Gateway, like files from the Library folder (D48).

**Tech Stack:** FastAPI 0.162, Next.js 16, React, TypeScript, Tailwind CSS v4, shadcn/ui, Vercel AI SDK 7, AI Elements, Streamdown (+ `@streamdown/math`, `@streamdown/mermaid`), Motion, next-themes, sonner, cmdk, TanStack Query, openapi-typescript, Zod, Vitest, Playwright, axe, OWASP ZAP, pnpm 11.

**Spec:** [02](../../../02_Tech_Stack_and_Security.md) §5.14 · [05](../../../05_Architecture.md) §3, §4, SEC-27–SEC-29, SEC-51, SEC-54, SEC-56, SEC-57 · [06](../../../06_Improvements.md) E1, E4, E6, F2, F9 · [overview](2026-11-07-techradar-00-overview.md) D20, D21, D43, D48, D49 · phase 2b (`answers`, `ask_job`), phase 2c (library), phase 3 (`briefings`, practice tables) and phase 1 Task 14 (alert log)

## Global Constraints

- The overview's Global Constraints 1–16 apply.
- **Identity:** every page and route requires `Tailscale-User-Login` to equal `OWNER_LOGIN`; otherwise 403 (SEC-27).
- **API access:** every `/v1/*` API route requires `X-Service-Token` (constant-time compare) and `X-TR-User` equal to `TR_OWNER_LOGIN`. In production `/docs`, `/redoc` and `/openapi.json` are disabled.
- **Content Security Policy, exactly:**

  `default-src 'self'; script-src 'self' 'nonce-<n>' 'strict-dynamic'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; media-src 'self' blob:; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'`
- **Other headers:** `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, `Permissions-Policy: microphone=(self), camera=(), geolocation=(), payment=(), usb=()`, `Cross-Origin-Opener-Policy: same-origin`, `Strict-Transport-Security: max-age=31536000`.
- **Answer rendering:**
  - Streamdown only, with `allowedLinkPrefixes={[]}`, `allowedImagePrefixes={[]}` and no raw HTML (SEC-28).
  - Sources are shown from citation data, never as links inside the answer text.
- **pnpm 11 (SEC-29):** `minimumReleaseAge: 1440`, `blockExoticSubdeps: true`, an explicit `allowBuilds`, and a committed lockfile.
- **Request limits:** API request bodies up to 64 KB; questions up to 500 characters.
- **Secrets:** the service token reaches the web container only as the Docker secret `api_service_token`, read on the server side.
- **Hosts and cross-site requests (SEC-51, SEC-54):** unknown `Host` gives 400. Every non-`GET` request to `/api/*` needs `Origin` equal to `PUBLIC_ORIGIN` and `x-tr-request: 1`. `GET` never changes data.
- **Confirm steps (SEC-56):** a ticket valid for one exact action, once, for 60 s, in the same session.

## Review Focus

1. **A malicious answer** (image, link, HTML or `javascript:` link) renders as plain text and triggers no outside request. Task 7 `malicious answer renders inert`.
2. **Opening the app from the LAN address**, or without Tailscale, is refused. Task 6 owner check, plus Task 7 `no identity header gives 403`.
3. **A slow ask** (the model takes 60 s) shows progress and doesn't time out before 120 s. Task 4 `pollAnswer waits up to 120 s`.
4. **Using it on a phone** (375 px wide) causes no horizontal scrolling, and the controls stay usable. Task 5 `phone layout has no horizontal scroll`.
5. **A new `/v1` route added later without auth** is caught automatically. Task 1 `test_every_v1_route_requires_auth`.

Also pinned on 2026-11-08:
- **A page on another site posting to the app** while I'm signed in is refused. Task 6b `cross-site POST refused`.
- **Confirming a stale or replayed release** does nothing. Task 2b `test_ticket_expires`, `test_ticket_runs_once`.
- **An alert summary that contains HTML** shows as text. Task 5b `alert summaries render as text`.
- **An uploaded file named `../../etc/passwd.pdf`** stays inside the uploads folder. Task 6c `test_upload_name_cannot_escape`.

---

### Task 1: API service with service-token and owner checks

**SEC:** SEC-27, SEC-41

**Files:**
- Create: `src/techradar/api/__init__.py`, `src/techradar/api/main.py`, `src/techradar/api/deps.py`
- Modify: `src/techradar/settings.py` (add `owner_login: str`, env `TR_OWNER_LOGIN`), `pyproject.toml` (extra `api = ["fastapi>=0.162", "uvicorn[standard]"]`)
- Test: `tests/api/test_auth.py`

**Interfaces:**
- Produces:
  - `MAX_BODY = 65_536`
  - `def create_app(settings: Settings) -> FastAPI`:
    - Docs are off in production.
    - Middleware: `TrustedHostMiddleware(allowed_hosts=["api", "localhost"])` (SEC-51), plus a body-size limit (413 over `MAX_BODY`).
    - `GET /healthz` returns `{"ok": true}` without auth.
  - `async def require_caller(x_service_token: str | None = Header(None), x_tr_user: str | None = Header(None)) -> str`:
    - A missing or bad token gives 401; a missing or wrong user gives 403.
    - The headers are optional, so a missing one gives 401 or 403 instead of FastAPI's 422.
    - Uses `secrets.compare_digest` against `read_secret("api_service_token")`.
  - `/v1` router: `APIRouter(prefix="/v1", dependencies=[Depends(require_caller)])`, with `GET /v1/ping` returning `{"pong": true}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_missing_or_wrong_token_401(client):
    assert client.get("/v1/ping").status_code == 401
    assert client.get("/v1/ping", headers={"X-Service-Token": "bad", "X-TR-User": OWNER}).status_code == 401

def test_wrong_user_403(client):
    assert client.get("/v1/ping", headers={"X-Service-Token": TOKEN, "X-TR-User": "someone@else"}).status_code == 403

def test_ok_with_both(client):
    assert client.get("/v1/ping", headers=AUTH).json() == {"pong": True}

def test_docs_hidden_in_prod(prod_client):
    assert prod_client.get("/docs").status_code == 404 and prod_client.get("/openapi.json").status_code == 404

def test_body_too_large_413(client):
    assert client.post("/v1/ping", headers=AUTH, content=b"x" * 70_000).status_code == 413

def test_foreign_host_rejected(client):
    assert client.get("/healthz", headers={"Host": "evil.example"}).status_code == 400

def test_every_v1_route_requires_auth(client):
    for r in client.app.routes:
        if getattr(r, "path", "").startswith("/v1"):
            for m in r.methods - {"HEAD", "OPTIONS"}:
                assert client.request(m, r.path.replace("{", "").replace("}", "")).status_code in (401, 422), r.path
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/api/test_auth.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `main.py` and `deps.py`**

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/api/test_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/api src/techradar/settings.py pyproject.toml tests/api && git commit -m "security(api): model-free API with service token and owner checks"
```

### Task 2: API routes and the OpenAPI export

**SEC:** SEC-18, SEC-27, SEC-41

**Files:**
- Create: `src/techradar/api/schemas.py`, `src/techradar/api/routes/{today,ask,practice,quiz,settings,models}.py`, `src/techradar/db/migrations/versions/0006_web.py`, `scripts/export_openapi.py`
- Modify:
  - `src/techradar/worker/tasks.py`: `ask_job(question: str, chat_id: int | None = None, answer_id: int | None = None)` updates a pending row when `answer_id` is given
  - `src/techradar/briefing/compose.py`: stores items in `briefings.items`
  - `briefing_job`: reads `user_settings`
- Test: `tests/api/test_routes.py` (marker `db`)

**Interfaces:**
- Consumes: `answers`, `briefings`, `mcqs`, `flashcards`, `record_answer`, `review_card`, `due_cards`; Ollama `/api/ps`.
- Produces:
  - **Migration `0006_web`:** table `user_settings` (`key` text primary key, `value` jsonb, `updated_at`); column `briefings.items` jsonb.
  - **Routes** (all under `/v1`):
    - `GET /today` returns `TodayResponse(date, items: list[TodayItem], plan_lines: list[str])`, where `TodayItem` is `(cluster_id, title, section, exam_tags, verified_headline, four_questions, note_path)`.
    - `POST /ask` takes `AskRequest(question: str (1–500), verified_only: bool = False)` and returns `{"answer_id": int}`. It creates an `answers` row with status `pending` and defers `ask` by name.
    - `GET /answers/{id}` returns `AnswerStatus(status: Literal["pending","answered","not_found","needs_review"], answer: Answer | None)`.
    - `POST /answers/{id}/save` returns 202 and defers `save_answer`.
    - `GET /practice/cards/due` returns `list[CardOut(id, front)]`.
    - `GET /practice/cards/{id}/back` returns `{"back": str}`.
    - `POST /practice/cards/{id}/rate` takes `{"rating": 1-4}` and returns `{"next_due": datetime}`.
    - `GET /quiz/today` returns `list[QuizQuestion(mcq_id, question, options)]`, with keys never included.
    - `POST /quiz/{mcq_id}/answer` takes `{"chosen": 0-3}` and returns `AnswerOutcome`.
    - `GET /models/status` returns `ModelsStatus(roles: dict[str, str], loaded: list[LoadedModel(name, size_bytes, size_vram_bytes)], ram_total_bytes, ram_available_bytes)`, from `roles.yaml`, `/api/ps` and `/proc/meminfo`.
    - `GET` and `PUT /settings` use `UserSettings(briefing_time: str (^[0-2][0-9]:[0-5][0-9]$), sections: list[Section], verified_only_default: bool)`.
  - **OpenAPI export:** `scripts/export_openapi.py` writes `apps/web/openapi.json` from `create_app` in dev mode.

- [ ] **Step 1: Write the failing tests (TestClient, real dev Postgres, fakes for Procrastinate defer)**

```python
@pytest.mark.db
def test_ask_creates_pending_and_defers(client, fake_defer):
    r = client.post("/v1/ask", headers=AUTH, json={"question": "What did RBI decide?"})
    assert r.status_code == 200 and fake_defer.calls == [("ask", {"question": "What did RBI decide?", "answer_id": r.json()["answer_id"]})]

@pytest.mark.db
def test_ask_rejects_long_question(client):
    assert client.post("/v1/ask", headers=AUTH, json={"question": "x" * 501}).status_code == 422

@pytest.mark.db
def test_quiz_today_never_includes_keys(client, seeded_mcqs):
    assert all("answer_index" not in q for q in client.get("/v1/quiz/today", headers=AUTH).json())

@pytest.mark.db
def test_settings_validation(client):
    assert client.put("/v1/settings", headers=AUTH, json={"briefing_time": "25:99", "sections": [], "verified_only_default": False}).status_code == 422

@pytest.mark.db
def test_models_status_shape(client, fake_ollama_ps): ...   # roles has "worker", loaded lists names with size_vram_bytes
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -m db tests/api/test_routes.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the routes, migration and job changes, then export OpenAPI**

- [ ] **Step 4: Run the tests and the export**

Run: `docker compose run --rm migrate && uv run pytest -m db tests/api -v && uv run python scripts/export_openapi.py`
Expected: PASS; `apps/web/openapi.json` written.

- [ ] **Step 5: Commit**

```bash
git add src/techradar scripts apps/web/openapi.json tests/api && git commit -m "feat(api): today, ask, practice, quiz, settings and models routes"
```

### Task 2b: Confirmation tickets

**SEC:** SEC-56 (D43)

**Files:**
- Create: `src/techradar/tickets.py`, `src/techradar/api/routes/tickets.py`
- Modify: `src/techradar/db/migrations/versions/0006_web.py` (add `pending_actions`), `src/techradar/bot/callbacks.py` (add `tk`; phase 2c's `qrel_ok` two-step becomes a ticket), `src/techradar/library/quarantine.py`
- Test: `tests/test_tickets.py` (marker `db`), `tests/api/test_tickets_route.py` (marker `db`)

**Interfaces:**
- Produces:
  - **`pending_actions` table:**
    - `id` bigint identity, `token` char(32) unique (`secrets.token_hex(16)`)
    - `session_id` text, `channel` (`web`, `telegram`, `voice`)
    - `action` text, `args` jsonb, `args_hash` char(64), `summary` varchar(300)
    - `created_at`, `expires_at`, `used_at` null, `cancelled_at` null
  - `Channel = Literal["web","telegram","voice"]`; `TTL_S = {"web": 60, "telegram": 60, "voice": 10}`
  - **Session IDs:**
    - web: `web:<X-TR-Session>`, a random ID per browser tab that the client sends as a header
    - Telegram: `tg:<chat_id>`
    - voice: `voice:<jarvis_session_id>` (phase 12)
  - `def args_hash(action: str, args: Mapping[str, Any]) -> str`: SHA-256 of `json.dumps({"action": action, "args": args}, sort_keys=True, separators=(",", ":"))`
  - `class Ticket(BaseModel)`: `id: int`, `token: str`, `summary: str`, `expires_at: datetime`
  - `async def create_ticket(session, *, session_id: str, channel: Channel, action: str, args: Mapping[str, Any], summary: str, now: datetime, starts_at: datetime | None = None) -> Ticket`:
    - cancels any other open ticket of the same session first (one per session)
    - sets `expires_at = (starts_at or now) + TTL_S[channel]`
  - `async def open_window(session, ticket_id: int, at: datetime) -> None`: sets `expires_at = at + TTL_S[channel]`. Phase 12 calls it when Jarvis finishes speaking.
  - `ConfirmResult = Literal["ok","expired","used","wrong_session","tampered","cancelled","unknown"]`
  - `async def confirm_ticket(session, *, token: str, session_id: str, action: str, args: Mapping[str, Any], now: datetime) -> ConfirmResult`:
    - **One statement:** `UPDATE pending_actions SET used_at = :now WHERE token = :t AND used_at IS NULL AND cancelled_at IS NULL AND expires_at > :now AND session_id = :s AND args_hash = :h RETURNING id`.
    - **When no row comes back:** one `SELECT` names the reason.
  - `ACTIONS: dict[str, Callable[[AsyncSession, Mapping[str, Any]], Awaitable[str]]]`: the registry of confirmable actions. This phase registers `quarantine.release` and `quarantine.delete`; phases 10, 11 and 12 add theirs.
  - `async def run_confirmed(session, token: str, session_id: str, now: datetime) -> tuple[ConfirmResult, str | None]`: looks up the stored action and args, which never come from the client, confirms them and runs the registered action once.
  - **Route:** `POST /v1/tickets/confirm` takes `{"token": str}` with header `X-TR-Session`, and returns `{"result": ConfirmResult, "message": str | None}`.
  - **Telegram:**
    - `qrel:<id>` creates a ticket and replies with the phase 2c text and the button `Yes, release` (`tk:<ticket_id>`)
    - `tk:<ticket_id>` calls `run_confirmed` with session `tg:<chat_id>`
    - an expired ticket replies `That confirmation expired. Try again.`

- [ ] **Step 1: Write the failing tests**

```python
pytestmark = pytest.mark.db

async def test_ticket_runs_once(session):
    t = await create_ticket(session, session_id="web:a", channel="web", action="quarantine.delete", args={"id": 1}, summary="Delete x", now=NOW)
    assert await confirm_ticket(session, token=t.token, session_id="web:a", action="quarantine.delete", args={"id": 1}, now=NOW) == "ok"
    assert await confirm_ticket(session, token=t.token, session_id="web:a", action="quarantine.delete", args={"id": 1}, now=NOW) == "used"

async def test_ticket_expires(session):
    t = await create_ticket(session, session_id="web:a", channel="web", action="a", args={}, summary="s", now=NOW)
    assert await confirm_ticket(session, token=t.token, session_id="web:a", action="a", args={}, now=NOW + timedelta(seconds=61)) == "expired"

async def test_ticket_other_session_refused(session):
    t = await create_ticket(session, session_id="web:a", channel="web", action="a", args={}, summary="s", now=NOW)
    assert await confirm_ticket(session, token=t.token, session_id="web:b", action="a", args={}, now=NOW) == "wrong_session"

async def test_ticket_tampered_args_refused(session):
    t = await create_ticket(session, session_id="web:a", channel="web", action="a", args={"minutes": 60}, summary="s", now=NOW)
    assert await confirm_ticket(session, token=t.token, session_id="web:a", action="a", args={"minutes": 600}, now=NOW) == "tampered"

async def test_new_ticket_cancels_old(session):
    t1 = await create_ticket(session, session_id="web:a", channel="web", action="a", args={}, summary="1", now=NOW)
    await create_ticket(session, session_id="web:a", channel="web", action="b", args={}, summary="2", now=NOW)
    assert await confirm_ticket(session, token=t1.token, session_id="web:a", action="a", args={}, now=NOW) == "cancelled"

async def test_voice_window_starts_when_opened(session):
    t = await create_ticket(session, session_id="voice:1", channel="voice", action="a", args={}, summary="s", now=NOW, starts_at=NOW + timedelta(seconds=30))
    await open_window(session, t.id, at=NOW + timedelta(seconds=8))
    assert await confirm_ticket(session, token=t.token, session_id="voice:1", action="a", args={}, now=NOW + timedelta(seconds=17)) == "ok"
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -m db tests/test_tickets.py tests/api/test_tickets_route.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the module, the table, the route and the Telegram callbacks**

- [ ] **Step 4: Migrate and run the tests**

Run: `docker compose run --rm migrate && uv run pytest -m db tests/test_tickets.py tests/api tests/library -v`
Expected: PASS (the phase 2c quarantine tests now go through tickets)

- [ ] **Step 5: Commit**

```bash
git add src/techradar tests && git commit -m "security(tickets): one-time confirmation tickets for every confirm step"
```

### Task 3: Next.js scaffold, supply-chain settings, security headers and identity

**SEC:** SEC-27, SEC-28, SEC-29

**Files:**
- Create: `apps/web/package.json`, `apps/web/pnpm-workspace.yaml`, `apps/web/pnpm-lock.yaml`, `apps/web/tsconfig.json` (strict), `apps/web/next.config.ts`, `apps/web/src/proxy.ts` (`middleware.ts` if the Next.js version still uses that name), `apps/web/src/lib/security.ts`, `apps/web/components.json`, `apps/web/src/app/globals.css` (Tailwind v4 tokens), `apps/web/eslint.config.mjs`, `apps/web/vitest.config.ts`
- Test: `apps/web/src/lib/security.test.ts`

**Interfaces:**
- Produces:
  - `export function buildCsp(nonce: string): string`: the exact CSP from Global Constraints
  - `export function securityHeaders(nonce: string): Record<string, string>`: all headers from Global Constraints
  - `export function isOwner(headers: Headers, ownerLogin: string): boolean`: compares `tailscale-user-login`, case-insensitively, after trimming
  - **Proxy:**
    1. Creates a nonce (`crypto.randomUUID()` → base64).
    2. Returns 403 `Forbidden` unless `isOwner`.
    3. Sets the security headers and forwards the nonce through the `x-nonce` request header.
  - **`pnpm-workspace.yaml`:** `minimumReleaseAge: 1440`, `blockExoticSubdeps: true`, and `allowBuilds:` listing only packages that need build scripts (start empty; add one only with a reason in a comment).
  - **Fonts:** Geist from the `geist` npm package (no runtime font downloads).

- [ ] **Step 1: Write the failing tests**

```ts
test("csp has required directives and nonce", () => {
  const c = buildCsp("abc");
  expect(c).toContain("'nonce-abc'"); expect(c).toContain("img-src 'self' data: blob:");
  expect(c).toContain("frame-ancestors 'none'"); expect(c).toContain("object-src 'none'");
});
test("isOwner", () => {
  expect(isOwner(new Headers({ "tailscale-user-login": "Me@Example.com " }), "me@example.com")).toBe(true);
  expect(isOwner(new Headers({ "tailscale-user-login": "x@y.z" }), "me@example.com")).toBe(false);
  expect(isOwner(new Headers(), "me@example.com")).toBe(false);
});
test("headers include permissions and referrer policy", () => {
  const h = securityHeaders("n");
  expect(h["Permissions-Policy"]).toBe("microphone=(self), camera=(), geolocation=(), payment=(), usb=()");
  expect(h["Referrer-Policy"]).toBe("no-referrer");
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd apps/web && pnpm install && pnpm vitest run src/lib/security.test.ts`
Expected: FAIL

- [ ] **Step 3: Scaffold the app and implement `security.ts` and the proxy**

- [ ] **Step 4: Run the tests, lint and build**

Run: `cd apps/web && pnpm vitest run && pnpm lint && pnpm build`
Expected: PASS; build succeeds.

- [ ] **Step 5: Commit**

```bash
git add apps/web && git commit -m "security(web): Next.js scaffold, CSP with nonce, owner identity check"
```

### Task 4: Server-only API client, generated types and answer streaming

**SEC:** SEC-10, SEC-27, SEC-28

**Files:**
- Create: `apps/web/src/lib/api.ts`, `apps/web/src/lib/api-types.ts` (generated), `apps/web/src/lib/stream.ts`, `apps/web/src/app/api/chat/route.ts`, `apps/web/src/app/api/answers/[id]/save/route.ts`, `apps/web/src/app/api/{practice,quiz,settings}/…/route.ts`
- Test: `apps/web/src/lib/stream.test.ts`, `apps/web/src/lib/api.test.ts`

**Interfaces:**
- Produces:
  - **`api.ts`** (`import "server-only"`):
    - `apiFetch<T>(path: string, init: RequestInit & { user: string }): Promise<T>` adds `X-Service-Token` (read once from `/run/secrets/api_service_token`) and `X-TR-User`.
    - It uses a 10 s timeout per call and only accepts paths that start with `/v1/`.
  - **Types:** `pnpm gen:api` runs `openapi-typescript openapi.json -o src/lib/api-types.ts`.
  - **Polling:** `export async function pollAnswer(id: number, fetcher, { intervalMs = 1000, timeoutMs = 120_000 }): Promise<AnswerStatus>`
  - **Streaming helpers:**
    - `export function chunkText(s: string, size = 24): string[]`
    - `export function answerToParts(a: Answer): UIPart[]` returns:
      - one `data-status` part
      - text parts from `chunkText(a.text)`
      - one `source-document` part per citation, with `title` and `filename = doc_path` (never URLs)
      - a `data-meta` part `{ status, usedUnverified, answerId }`
  - **`POST /api/chat`:**
    1. Validates `{ messages }` with Zod; the last user text must be 1–500 characters.
    2. Calls `POST /v1/ask`, then `pollAnswer`.
    3. Streams with `createUIMessageStream` / `createUIMessageStreamResponse`, sending `data-status` events `searching` and `writing` while polling.
  - **Other route handlers:** thin, Zod-validated proxies to the matching `/v1` routes.

- [ ] **Step 1: Write the failing tests**

```ts
test("chunkText splits evenly", () => expect(chunkText("abcdef", 2)).toEqual(["ab", "cd", "ef"]));
test("answerToParts never emits urls", () => {
  const parts = answerToParts(ANSWER_WITH_CITATIONS);
  expect(JSON.stringify(parts)).not.toMatch(/https?:\/\//);
  expect(parts.filter(p => p.type === "source-document")).toHaveLength(2);
});
test("pollAnswer waits up to 120 s", async () => {
  vi.useFakeTimers(); const p = pollAnswer(1, fakeFetcherPendingThen("answered", 60_000));
  await vi.advanceTimersByTimeAsync(61_000); await expect(p).resolves.toMatchObject({ status: "answered" });
});
test("apiFetch refuses non-v1 paths", async () => {
  await expect(apiFetch("/healthz", { user: "me" })).rejects.toThrow("path");
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd apps/web && pnpm vitest run src/lib`
Expected: FAIL

- [ ] **Step 3: Implement the modules and route handlers; generate the types**

- [ ] **Step 4: Run the tests and the build**

Run: `cd apps/web && pnpm gen:api && pnpm vitest run && pnpm build`
Expected: PASS. The build fails if any client component imports `@/lib/api` (enforced by `server-only`).

- [ ] **Step 5: Commit**

```bash
git add apps/web && git commit -m "feat(web): server-only API client and streamed answers"
```

### Task 5: Screens and design system

**SEC:** SEC-28

**Files:**
- Create: `apps/web/src/app/(app)/layout.tsx`, `apps/web/src/app/(app)/{today,ask,practice,settings,models}/page.tsx`, `apps/web/src/components/answer/AnswerView.tsx`, `apps/web/src/components/today/StoryCard.tsx`, `apps/web/src/components/practice/{Flashcard,QuizCard}.tsx`, `apps/web/src/components/models/ModelsTable.tsx`, `apps/web/src/components/shell/{AppShell,CommandMenu,ThemeToggle}.tsx`, `apps/web/src/app/manifest.ts`, `tests/web_mock.py`, `apps/web/playwright.config.ts`, `apps/web/tests/screens.spec.ts`
- Test: `apps/web/tests/screens.spec.ts`

**Interfaces:**
- Consumes: the route handlers from Task 4.
- Produces:
  - **`AnswerView`:** renders `<Streamdown allowedLinkPrefixes={[]} allowedImagePrefixes={[]} plugins={[math, mermaid]}>` with the text. Below it:
    - source chips (title › heading, `verified`/`unverified` badge)
    - a `⚠️ Uses unverified notes` banner when that applies
    - actions: Copy, Save to vault, Ask follow-up
  - **Today:** story cards by section in `SECTION_ORDER`; each card has "Why", "For me", exam tags and a "Go deeper" button that opens Ask pre-filled with `Explain more about <title>`.
  - **Practice:**
    - Flashcards: Space shows the back, keys 1–4 rate.
    - Quiz: keys A–D answer; a timer shows per question.
  - **Settings:** briefing time, sections, verified-only default.
  - **Models:** a read-only table (job → model, loaded, GPU memory per model, RAM).
  - **Shell:** `AppShell` (sidebar on desktop, bottom tabs on phone), `CommandMenu` (⌘K / Ctrl+K), `ThemeToggle` (next-themes). Every page has skeletons and empty and error states. Motion respects `prefers-reduced-motion`.
  - **Test API:** `tests/web_mock.py` runs the real `create_app` with dependency overrides that return fixture data. Playwright's `webServer` starts it on port 8001 and runs `next start` with `API_BASE_URL=http://127.0.0.1:8001`, the test token and `OWNER_LOGIN=test@example.com`. The identity header is added in `playwright.config.ts` `extraHTTPHeaders`.

- [ ] **Step 1: Write the failing Playwright tests**

```ts
test("today shows cards with badges", async ({ page }) => {
  await page.goto("/today"); await expect(page.getByText("LangGraph 1.3 released")).toBeVisible();
  await expect(page.getByLabel("verified").first()).toBeVisible();
});
test("ask streams an answer with sources", async ({ page }) => {
  await page.goto("/ask"); await page.getByRole("textbox").fill("What did RBI decide?"); await page.keyboard.press("Enter");
  await expect(page.getByText("[C1]")).toBeVisible(); await expect(page.getByText("RBI policy › Rates")).toBeVisible();
});
test("practice keyboard rating", async ({ page }) => {
  await page.goto("/practice"); await page.keyboard.press("Space"); await page.keyboard.press("3");
  await expect(page.getByText(/next review/i)).toBeVisible();
});
test("phone layout has no horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  for (const p of ["/today", "/ask", "/practice", "/settings", "/models"]) {
    await page.goto(p); expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd apps/web && pnpm playwright test tests/screens.spec.ts`
Expected: FAIL

- [ ] **Step 3: Build the screens with shadcn/ui, AI Elements and Streamdown**

- [ ] **Step 4: Run the tests**

Run: `cd apps/web && pnpm playwright test tests/screens.spec.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/web tests/web_mock.py && git commit -m "feat(web): Today, Ask, Practice, Settings and Models screens"
```

### Task 5b: Library, Quarantine and Security screens

**SEC:** SEC-27, SEC-28, SEC-56, SEC-66

**Files:**
- Create:
  - `src/techradar/api/routes/library.py`, `src/techradar/api/routes/quarantine.py`, `src/techradar/api/routes/security.py`
  - `apps/web/src/app/(app)/library/page.tsx`, `apps/web/src/app/(app)/security/page.tsx`
  - `apps/web/src/components/library/{BookList,ChapterList}.tsx`, `apps/web/src/components/security/{AlertList,QuarantineList,Heartbeat}.tsx`, `apps/web/src/components/shell/ConfirmDialog.tsx`
  - `apps/web/tests/library-security.spec.ts`
- Modify:
  - `src/techradar/api/routes/ask.py`: `AskRequest` gains `doc_id: int | None = None`
  - `compose.yaml`: the `api` mounts `/var/lib/techradar-alerter` read-only at `/alerts`
  - `apps/web/src/components/shell/AppShell.tsx`: Library and Security in the navigation
  - `tests/web_mock.py`
- Test: `tests/api/test_library_security_routes.py` (marker `db`), `apps/web/tests/library-security.spec.ts`

**Interfaces:**
- Consumes: `library_docs`, `library_chapters`, `quarantine_items` (phases 2 and 2c); `create_ticket`, `run_confirmed` (Task 2b); `AlertLog` lines (phase 1 Task 14).
- Produces:
  - **Routes** (all under `/v1`):

    | Route | Request and response |
    |---|---|
    | `GET /library/docs` | `list[DocOut(id, title, kind, status, n_chapters, trust, ready_at)]` |
    | `GET /library/docs/{id}/chapters` | `list[ChapterOut(id, ordinal, title, pages, read, has_summary)]` |
    | `POST /library/chapters/{id}/read` | 202; defers `make_chapter_cards_job` (my click, so no ticket) |
    | `GET /quarantine` | `list[QuarantineOut(id, name, origin, reasons, expires_at)]` |
    | `POST /quarantine/{id}/release`, `POST /quarantine/{id}/delete` | `{"ticket": Ticket}` |
    | `GET /security/alerts?days=7` | `list[AlertOut(level, source, rule, service, summary, at)]`, read from `/alerts/alerts.jsonl` (the last 7 days, at most 500, newest first) |
    | `GET /security/heartbeat` | `{"last_sent": datetime \| None, "critical_24h": int, "warnings_24h": int}` |

  - **Library screen:**
    - books with status badges (`ready`, `processing`, `awaiting transcription`, `quarantined`)
    - each book's chapters, with "Mark as read"
    - "Ask this book", which opens Ask with `doc_id` set
  - **Security screen:**
    - tabs: Alerts (plain text, newest first), Quarantine (Release and Delete through `ConfirmDialog`) and Heartbeat
    - the heartbeat shows the time of the last heartbeat in red when it's over 26 hours old
  - **`ConfirmDialog`:**
    - shows the ticket's summary with a countdown from `expires_at`
    - Confirm posts to `/api/tickets/confirm`
    - when it expires: `This confirmation expired. Try again.`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.db
def test_alerts_route_reads_log_plain(client, alert_log_with_html_summary):
    a = client.get("/v1/security/alerts", headers=AUTH).json()[0]
    assert a["summary"] == "<img src=x> seen"          # returned as data; the web renders it as text

@pytest.mark.db
def test_release_returns_ticket_not_action(client, quarantined_item):
    r = client.post(f"/v1/quarantine/{quarantined_item.id}/release", headers=AUTH)
    assert "token" in r.json()["ticket"] and quarantined_item_still_held()
```

```ts
test("library lists books and chapters", async ({ page }) => {
  await page.goto("/library"); await page.getByText("Indian Economy").click();
  await expect(page.getByRole("button", { name: "Mark as read" }).first()).toBeVisible();
});
test("quarantine release needs a confirmation that expires", async ({ page }) => {
  await page.clock.install(); await page.goto("/security?tab=quarantine");
  await page.getByRole("button", { name: "Release" }).first().click();
  await expect(page.getByText(/Confirm within \d+ s/)).toBeVisible();
  await page.clock.fastForward(61_000); await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("This confirmation expired. Try again.")).toBeVisible();
});
test("alert summaries render as text", async ({ page }) => {
  await page.goto("/security"); expect(await page.locator("img[src='x']").count()).toBe(0);
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -m db tests/api/test_library_security_routes.py -v && cd apps/web && pnpm playwright test tests/library-security.spec.ts`
Expected: FAIL

- [ ] **Step 3: Implement the routes, the screens and the dialog; regenerate the OpenAPI types**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/api apps/web compose.yaml tests && git commit -m "feat(web): Library, Quarantine and Security screens with confirmation tickets"
```

### Task 6: Containers, the no-egress `edge` network, Tailscale Serve and on-demand Langfuse

**SEC:** SEC-02, SEC-07, SEC-08, SEC-27

**Files:**
- Create: `apps/web/Dockerfile`, `infra/langfuse/compose.yaml`
- Modify:
  - `infra/docker/Dockerfile`: add the `api` target (`--extra api --extra queue`)
  - `compose.yaml`: add `api`, `web`, and networks `web_internal` (internal), `edge` and `obs` (internal; `worker` joins it for traces)
  - `infra/falco/expected_programs.yaml`: `api: [python, uvicorn]`, `web: [node]` and Langfuse's services (below) (`api` is already in `internal_only`; rerun the generator)
  - `tests/security/test_compose_policy.py`: `edge` rules, and the same policy checks for `infra/langfuse/compose.yaml`
  - `src/techradar/settings.py`: `langfuse_enabled: bool = False`
  - `infra/host/RUNBOOK.md`: the Tailscale Serve command
- Test: `tests/security/test_compose_policy.py`

**Interfaces:**
- Produces:
  - **`edge` network:** `driver: bridge`, `driver_opts: {"com.docker.network.bridge.enable_ip_masquerade": "false"}`. Only `web` may join it.
  - **`api` service:**
    - Networks: `db`, `llm`, `web_internal`
    - Secrets: `tr_app_password`, `tr_ro_password`, `api_service_token`
    - Command: `uvicorn techradar.api.main:app --host 0.0.0.0 --port 8000 --proxy-headers=false`
    - No published port
  - **`web` service:**
    - Image: `node:<LTS>-slim` (exact), Next.js standalone output, user `1000:1000`
    - Networks: `web_internal`, `edge`; port `"127.0.0.1:3000:3000"`
    - Secret `api_service_token`; env `OWNER_LOGIN`, `API_BASE_URL=http://api:8000`
    - `read_only: true`, with `tmpfs` for `/tmp` and `/app/.next/cache`
  - **Langfuse (on demand, D49):**
    - `infra/langfuse/compose.yaml` is a separate Compose project named `techradar-langfuse`, so its containers match Falco's `tr_app_container`. Its images are pinned by digest, and `TELEMETRY_ENABLED=false`.
    - **Networks:** every Langfuse service is on `obs` (`internal: true`; defined in `compose.yaml` and joined as `external`). Only its web container is also on `obs_edge`, a bridge with masquerade off, for the port `"127.0.0.1:3001:3000"`. Nothing in it can reach the internet.
    - **Watched like the rest:** its services and programs are in `expected_programs.yaml` (check each with `docker top` on first start). `test_compose_policy.py` loads this file too, and `compose_exceptions.yaml` lists any of its images that must start as root, with a reason.
    - **Traces:** `worker` sends traces over `obs` only when `TR_LANGFUSE_ENABLED=true`. They hold prompts and content, so they stay on the server.
    - **Start:** only with `docker compose -f infra/langfuse/compose.yaml up -d`.
  - **Tailscale Serve (owner):** `tailscale serve --bg --https=443 http://127.0.0.1:3000`.

- [ ] **Step 1: Write the failing policy tests**

```python
def test_edge_network_has_no_masquerade():
    assert COMPOSE["networks"]["edge"]["driver_opts"]["com.docker.network.bridge.enable_ip_masquerade"] == "false"

def test_only_web_on_edge():
    assert [n for n, s in SERVICES if "edge" in s.get("networks", [])] == ["web"]

def test_langfuse_project_has_no_internet():
    lf = yaml.safe_load(Path("infra/langfuse/compose.yaml").read_text())
    assert lf["name"] == "techradar-langfuse" and lf["networks"]["obs"]["external"] is True
    assert lf["networks"]["obs_edge"]["driver_opts"]["com.docker.network.bridge.enable_ip_masquerade"] == "false"
    assert all(set(s.get("networks", [])) <= {"obs", "obs_edge"} for s in lf["services"].values())
```

Update `test_only_allowed_services_on_internet_networks` to treat `edge` as not-internet only while its masquerade is off.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/security/test_compose_policy.py -v`
Expected: FAIL

- [ ] **Step 3: Write the Dockerfiles, Compose changes and Langfuse project**

- [ ] **Step 4: Verify on the server**

Run: `uv run pytest tests/security/test_compose_policy.py -v && docker compose up -d --build api web && curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/today && docker compose exec web node -e "fetch('https://example.com').then(()=>process.exit(0)).catch(()=>process.exit(1))"; echo "egress exit $?"`
Expected: policy passes; `403` (no identity header); `egress exit 1`.

Owner check: `https://<server>.<tailnet>.ts.net/today` loads on the Mac and phone; `http://<server-LAN-IP>:3000` is refused.

- [ ] **Step 5: Commit**

```bash
git add apps/web/Dockerfile infra compose.yaml tests/security src/techradar/settings.py && git commit -m "feat(deploy): api and web containers behind Tailscale Serve"
```

### Task 6b: Cross-site request and host hardening

**SEC:** SEC-51, SEC-54

**Files:**
- Modify:
  - `apps/web/src/lib/security.ts`: add `isAllowedHost` and `csrfOk`
  - `apps/web/src/proxy.ts`
  - `apps/web/next.config.ts`: Server Actions' `allowedOrigins`
  - `apps/web/src/lib/client-fetch.ts`: every browser-side request sends `x-tr-request: 1` and `x-tr-session`
  - `compose.yaml`: `web` env `PUBLIC_ORIGIN` and `ALLOWED_HOSTS`
- Test: `apps/web/src/lib/security.test.ts` (add tests), `apps/web/tests/security.spec.ts` (add tests), `tests/api/test_get_routes.py` (marker `db`)

**Interfaces:**
- Produces:
  - **Env:**
    - `PUBLIC_ORIGIN=https://<server>.<tailnet>.ts.net`
    - `ALLOWED_HOSTS=<server>.<tailnet>.ts.net,127.0.0.1:3000,localhost:3000`
  - `export function isAllowedHost(host: string | null, allowed: string[]): boolean`: an exact match, case-insensitive
  - `export function csrfOk(method: string, headers: Headers, publicOrigin: string): boolean`:
    - `GET`, `HEAD` and `OPTIONS` are always allowed
    - any other method needs `origin` equal to `publicOrigin` (or, with no `origin`, a `referer` starting with `publicOrigin + "/"`) **and** `x-tr-request` equal to `1`
  - **Proxy order:**
    1. host check: 400 `Bad host`
    2. owner check (Task 3): 403
    3. `csrfOk` for `/api/*`: 403 `Forbidden`
  - **`next.config.ts`:** `experimental.serverActions.allowedOrigins = [new URL(PUBLIC_ORIGIN).host]`
  - **Cookies:** the app sets none. If one is ever added, it must be `__Host-…; SameSite=Strict; HttpOnly; Secure`, and the Playwright suite fails on any other `Set-Cookie`.
  - **API:** `test_get_routes_change_nothing` calls every `GET /v1/*` route with fixtures, and asserts that the row counts of all tables are unchanged.

- [ ] **Step 1: Write the failing tests**

```ts
test("host allowlist", () => {
  expect(isAllowedHost("box.tail1234.ts.net", ["box.tail1234.ts.net"])).toBe(true);
  expect(isAllowedHost("evil.example", ["box.tail1234.ts.net"])).toBe(false);
});
test("csrf rules", () => {
  const o = "https://box.tail1234.ts.net";
  expect(csrfOk("POST", new Headers({ origin: o, "x-tr-request": "1" }), o)).toBe(true);
  expect(csrfOk("POST", new Headers({ origin: "https://evil.example", "x-tr-request": "1" }), o)).toBe(false);
  expect(csrfOk("POST", new Headers({ origin: o }), o)).toBe(false);
  expect(csrfOk("GET", new Headers(), o)).toBe(true);
});
```

```ts
// security.spec.ts additions
test("cross-site POST refused", async ({ request }) => {
  const r = await request.post("/api/chat", { headers: { origin: "https://evil.example", "x-tr-request": "1" }, data: { question: "x" } });
  expect(r.status()).toBe(403);
});
test("no set-cookie except __Host- strict", async ({ page }) => {
  const bad: string[] = []; page.on("response", r => { const c = r.headers()["set-cookie"]; if (c && !/^__Host-.*SameSite=Strict.*HttpOnly.*Secure/i.test(c)) bad.push(c); });
  for (const p of ["/today", "/ask", "/library", "/security"]) await page.goto(p);
  expect(bad).toEqual([]);
});
```

```python
@pytest.mark.db
def test_get_routes_change_nothing(client, seeded_everything, row_counts):
    before = row_counts()
    for path in get_routes(client.app):
        client.get(fill_params(path), headers=AUTH)
    assert row_counts() == before
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd apps/web && pnpm vitest run src/lib/security.test.ts && pnpm playwright test tests/security.spec.ts && cd ../.. && uv run pytest -m db tests/api/test_get_routes.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the checks, the proxy order, the client header and the config**

- [ ] **Step 4: Run the tests, then the foreign-host probe on the server**

Run: same as Step 2, then `curl -s -o /dev/null -w '%{http_code}' -H 'Host: evil.example' http://127.0.0.1:3000/today`.
Expected: PASS; the probe prints `400`.

- [ ] **Step 5: Commit**

```bash
git add apps/web compose.yaml tests && git commit -m "security(web): host allowlist, origin and custom-header checks"
```

### Task 6c: Uploads from the Library screen

**SEC:** SEC-27, SEC-43, SEC-51, SEC-54, SEC-57 (D48)

**Files:**
- Create: `src/techradar/api/routes/uploads.py`, `src/techradar/library/uploads.py`, `apps/web/src/app/api/library/upload/route.ts`, `apps/web/src/components/library/AddFileButton.tsx`, `apps/web/tests/upload.spec.ts`
- Modify:
  - `src/techradar/db/migrations/versions/0006_web.py`: `library_docs.origin` also allows `upload`
  - `src/techradar/library/inbox.py`: `plan_library_intake` and `classify` accept the origin `upload`, which uses the `library` limits; the uploads folder uses `settle_s=0`, because files arrive there by rename
  - `src/techradar/rag/indexer.py`: `index_sync` also passes `(library_uploads_dir, "upload")` to `plan_library_intake`
  - `src/techradar/settings.py`: the fields below
  - `compose.yaml`: `api` and `worker` mount `./data/library-uploads` read-write
  - `apps/web/src/components/library/BookList.tsx`: shows the Add file button
- Test: `tests/api/test_uploads.py` (marker `db`), `tests/library/test_inbox.py` (add tests), `apps/web/tests/upload.spec.ts`

**Interfaces:**
- Consumes: `isAllowedHost`, `csrfOk` (Task 6b); the service-token and owner checks (Task 1); `plan_library_intake`, `classify` (phase 2c Task 2); the `library` sizes in `limits.yaml` (phase 2c Task 1).
- Produces:
  - **Settings:** `library_uploads_dir = "/data/library-uploads"`, `upload_dir_max_bytes = 5_000_000_000`, `uploads_per_hour = 20`
  - `UPLOAD_EXTENSIONS: dict[str, LibraryKind]`: `.pdf` → pdf; `.docx` → docx; `.epub` → epub; `.mp4`, `.mkv`, `.webm`, `.mov` → video; `.mp3`, `.m4a`, `.wav`, `.ogg` → audio
  - `def safe_upload_name(name: str, now: datetime) -> tuple[str, str]`: returns the stem and the extension.
    - It NFKC-normalises the name and keeps only letters, digits, spaces, `-`, `_` and `.`, so path separators disappear.
    - It strips leading dots and cuts the stem to 120 characters.
    - An empty stem becomes `upload-<YYYYMMDD-HHMMSS>`.
    - An extension that isn't in `UPLOAD_EXTENSIONS` raises `UnsupportedUpload`.
  - **`POST /v1/library/upload`** (API):
    - **Request:** the raw file bytes (never multipart), and the header `X-TR-Filename` holding the file name as percent-encoded UTF-8, at most 255 bytes.
    - **Saving:** it streams the body to `<library_uploads_dir>/<random>.tmp`, then renames it to `<stem>.<ext>`, adding ` (2)`, ` (3)` and so on if the name is taken.
    - **Refusals** (any partial file is removed):

      | Status | Detail |
      |---|---|
      | 415 | `unsupported file type <ext>` |
      | 413 | `too large (<n> MB, limit <m> MB)`, checked against the `library` limit while streaming |
      | 507 | `upload folder full` when the folder would pass `upload_dir_max_bytes` |
      | 429 | `too many uploads; try again later` after `uploads_per_hour` uploads in the last hour |

    - **It never opens or parses the file.** The Intake Gateway checks it, with origin `upload`.
    - **On success:** 201 `{"name": "<stem>.<ext>"}`, and it defers `index_sync` at once (it's idempotent).
  - **`POST /api/library/upload`** (Next.js route handler):
    - checks `isAllowedHost` and `csrfOk`
    - refuses a `Content-Length` over 4 GB (the largest limit) with 413
    - streams the body to the API with the service token (`fetch(url, { body: req.body, duplex: "half" })`)
  - **`AddFileButton`:** a file picker labelled `Add file`, limited to the extensions above. It uploads one file at a time with a progress bar, then shows either `Added <name>. It's being checked; it will appear in your library when it passes.` or the API's reason.
  - **Intake:** files from the uploads folder become `library_docs` with `origin="upload"` and `trust="my_own"`. An antivirus hit quarantines them, because they're files I sent (D34).

- [ ] **Step 1: Write the failing tests**

```python
pytestmark = pytest.mark.db

def test_upload_lands_in_uploads_folder(api_client, uploads_dir):
    r = api_client.post("/v1/library/upload", headers={**AUTH, "X-TR-Filename": quote("Indian Economy.pdf")}, content=b"%PDF-1.7 test")
    assert r.status_code == 201 and (uploads_dir / "Indian Economy.pdf").read_bytes().startswith(b"%PDF")

def test_upload_refuses_unknown_type(api_client, uploads_dir):
    r = api_client.post("/v1/library/upload", headers={**AUTH, "X-TR-Filename": "tool.exe"}, content=b"MZ")
    assert r.status_code == 415 and r.json()["detail"] == "unsupported file type .exe" and list(uploads_dir.iterdir()) == []

def test_upload_too_large_leaves_nothing(api_client, uploads_dir, small_limits): ...   # 413, and the folder stays empty

def test_upload_name_cannot_escape(api_client, uploads_dir):
    r = api_client.post("/v1/library/upload", headers={**AUTH, "X-TR-Filename": quote("../../etc/passwd.pdf")}, content=b"%PDF")
    assert r.status_code == 201 and [p.name for p in uploads_dir.iterdir()] == ["etcpasswd.pdf"]

def test_twenty_first_upload_in_an_hour_refused(api_client, twenty_recent_uploads): ...   # 429

async def test_uploaded_file_goes_through_the_gateway(session, uploads_with_pdf, library_dir):
    [doc_id] = await plan_library_intake(session, [(uploads_with_pdf, "upload")], library_dir, NOW, LIMITS)
    assert (await doc_row(session, doc_id)).origin == "upload"       # plan_doc then sends it to the parser sandbox
```

```ts
test("add file uploads and explains the check", async ({ page }) => {
  await page.route("**/api/library/upload", r => r.fulfill({ status: 201, json: { name: "Indian Economy.pdf" } }));
  await page.goto("/library"); await page.getByLabel("Add file").setInputFiles(fixture("book.pdf"));
  await expect(page.getByText("Added Indian Economy.pdf. It's being checked; it will appear in your library when it passes.")).toBeVisible();
});
test("upload without the cross-site header is refused", async ({ request }) => {
  expect((await request.post("/api/library/upload", { data: "x" })).status()).toBe(403);
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -m db tests/api/test_uploads.py tests/library/test_inbox.py -v && cd apps/web && pnpm playwright test tests/upload.spec.ts`
Expected: FAIL

- [ ] **Step 3: Implement the API route, the name check, the intake change, the Next.js route, the button and the mounts**

- [ ] **Step 4: Run the tests and the policy check**

Run: same as Step 2, then `uv run pytest tests/security/test_compose_policy.py -q`.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar apps/web compose.yaml tests && git commit -m "feat(web): file uploads from the Library screen, checked by the Intake Gateway"
```

### Task 7: Web security suite and gate 4

**SEC:** SEC-27, SEC-28, SEC-29

**Files:**
- Create: `apps/web/tests/security.spec.ts`, `apps/web/tests/a11y.spec.ts`, `scripts/check_bundle_secrets.sh`, `scripts/check_pnpm_settings.sh`, `security/zap/zap-baseline.conf`
- Modify: `compose.yaml` (add `zap`: profile `test`, image `zaproxy/zap-stable:<exact>`, network `web_internal` only, baseline hardening), `Makefile` (add `gate-4`)
- Test: the two spec files

**Interfaces:**
- Produces:
  - **Mock answer:** `tests/web_mock.py` gains a "malicious answer" fixture whose text contains `![x](https://evil.example/p.png)`, `<img src=x onerror=alert(1)>` and `[click](javascript:alert(1))`.
  - **`check_bundle_secrets.sh`:** fails if `apps/web/.next/static` contains the token value or `x-service-token` (case-insensitive).
  - **`check_pnpm_settings.sh`:** fails unless `minimumReleaseAge` is at least 1440, `blockExoticSubdeps: true` is set, and `pnpm-lock.yaml` exists.
  - **ZAP baseline:** runs against `http://web:3000` with a replacer rule that adds `Tailscale-User-Login: <owner>`. High and Medium findings are configured as FAIL.
  - **`make gate-4`:**
    1. `gate-3`
    2. `pytest tests/api` (and `-m db`)
    3. `pnpm vitest run`, `pnpm playwright test`
    4. `check_bundle_secrets.sh`, `check_pnpm_settings.sh`
    5. ZAP baseline
    6. The policy test
    7. `pytest -m db tests/test_tickets.py tests/api/test_get_routes.py`
    8. The foreign-host probe: `curl -s -o /dev/null -w '%{http_code}' -H 'Host: evil.example' http://127.0.0.1:3000/today` must print `400`
    9. Print the signing reminder.

- [ ] **Step 1: Write the failing tests**

```ts
test("csp and headers present", async ({ page }) => {
  const r = await page.goto("/today"); const h = r!.headers();
  expect(h["content-security-policy"]).toContain("frame-ancestors 'none'"); expect(h["x-content-type-options"]).toBe("nosniff");
});
test("malicious answer renders inert", async ({ page }) => {
  const outside: string[] = []; page.on("request", r => { if (!r.url().startsWith("http://127.0.0.1:3000")) outside.push(r.url()); });
  await askMalicious(page);
  expect(await page.locator("img[src*='evil'], [onerror], a[href^='javascript:']").count()).toBe(0);
  expect(outside).toEqual([]);
});
test("no identity header gives 403", async ({ browser }) => {
  const ctx = await browser.newContext({ extraHTTPHeaders: {} }); const p = await ctx.newPage();
  expect((await p.goto("/today"))!.status()).toBe(403);
});
test("browser cannot reach the API", async ({ page }) => {
  await page.goto("/today");
  expect(await page.evaluate(() => fetch("http://api:8000/healthz").then(() => "ok").catch(() => "blocked"))).toBe("blocked");
});
// a11y.spec.ts: for each screen, AxeBuilder results have no "serious" or "critical" violations
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd apps/web && pnpm playwright test tests/security.spec.ts tests/a11y.spec.ts`
Expected: FAIL

- [ ] **Step 3: Implement the fixtures, scripts, ZAP config and Makefile target; fix any findings**

- [ ] **Step 4: Run the gate on the server**

Run: `make gate-4`
Expected: every step passes; ZAP reports no High or Medium findings.

- [ ] **Step 5: Commit and sign**

```bash
git add apps/web/tests scripts security/zap compose.yaml Makefile docs/security/gates.md tests/web_mock.py && git commit -m "security(web): web security suite, ZAP baseline, gate 4 passed"
```
