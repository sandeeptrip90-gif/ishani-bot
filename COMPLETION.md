# Ishani Bot — Implementation Status (honest, current)

Updated: 2026-11-21
Scope: the 8-section specification (personalized chatbot, group ownership, web group
management, per-user memory, unified `/learn`, lightweight tool use, safety, storage).

**Overall: all 8 sections have a working implementation.** Several capabilities have
deliberate limits described under "Known limits / not implemented" below.

---

## 1. Personalized AI chatbot — implemented

- `persona.json` is the source of truth for `master_prompt`, `keyword_responses`,
  `system_prompts`, `fallback`, `company_brief`, `prewritten_messages`.
- Base persona is never modified by any learning/lesson command (guard in
  `_save_persona_learning`; verified by tests).
- Ollama / llama.cpp style endpoints remain supported through the existing
  OpenAI-compatible provider config. No provider keys are stored in the repo.
- Existing moderation, welcome/left messages, scheduled messages, document delivery,
  broadcasts, and admin panel remain in place.
- Regressions verified: keyword responses and welcome messages byte-for-byte unchanged.

### Conversational skill enhancement — implemented

- Added seven communication-technique lines to `system_prompts.full_after_memory` only.
  That array is injected into **both** the compact (local/OpenAI-compatible) and full
  prompt paths, so every provider gets the same behavior without duplicating the lines.
- Techniques adapted from the `talk` and `love-companion` reference skills: natural
  texting (no assistant sign-offs, no needless formatting, mirror slang/code-switching),
  energy and length matching, reading subtext and mood shifts, resonate-before-asking,
  questions as a last resort (one max, never naked), softening on pushback, invisible
  use of saved memory, and humor/short-answer calibration.
- **Identity, name, age, background, `master_prompt`, company facts, keyword responses,
  prewritten messages, memory labels/controls, and all existing learned instructions are
  untouched.** `/learn` blocks are still appended last, so admin instructions continue to
  override this guidance. No Python source changes were needed.
- Verified by `verify_conversation_skill.py` plus the full regression suite.

## 2. Unified `/learn` — implemented

Single master-admin-only entry point, with a confirmation/correction loop:

- add, view/list, update existing, update last, remove matching, remove last, remove all
- allow / block link restrictions
- natural-language intents (Hinglish + English), e.g.
  `what have you learned?`, `forget last lesson`, `forget all`,
  `replace X with Y`, `no links please`, `allow links`
- `/learn` with no arguments prompts for the instruction; free-text replies are
  handled by `handle_admin_learning` and saved only after `yes`/`confirm`.
- Non-admins are completely ignored by the learning flow.
- Persona writes use atomic replace and a lock; no raw `persona.json` writes remain.

## 3. Per-user AI memory — implemented

- `conversations` in `data.json` is scoped as `private` or `group:<telegram_chat_id>`.
- Per-user facts/preferences/projects and recent history are stored and retrieved by
  user ID. Group history is never mixed with private history, and one user cannot read
  or alter another user's memory.
- Natural self-updates: "yaad rakho / remember that / correction / actually / I am ..."
  update only the speaking user's own record.
- Existing `chats/` layout retained; all writes are locked and atomic.

## 4. Multi-owner groups — implemented

- Master Owner (`ADMIN_ID`) and accepted Group Owner roles stored in `data.json`.
- `/assign <user|@username> [group_id]` creates a one-time, 7-day, hashed invitation;
  the token is delivered privately (never posted into the group).
- `/accept <token>` verifies recipient ID/username and binds ownership.
- `/registergroup` registers the current group; Telegram admin status is checked where
  possible. `/verifygroup <id>` is master-only for pending registrations.
- `/mygroups`, `/owners`, `/assigngroup`, `/unassigngroup`, `/grouppanel`, `/groupset`.
- Strict scoping: `dm.visible_group_ids()`, `dm.is_group_owner()` and
  `actor_may_authorize()` prevent owners from touching other groups or global settings.
- All ownership/assignment/verification actions write to `audit_log`.

## 5. Group Management webpage — superseded by section 9

The embedded HTML page was removed. `GET /groups`, `/settings` and `/` on the Python port
are now served by the Next.js Control Center described in section 9 through a same-port
proxy. The API and authentication behavior below is still in place.

- `GET /groups` — role-scoped dashboard (token entered in the page; never in the URL).
- `GET /api/groups` — stats (groups, owners, administrators, members), group table,
  delivery log. Master sees all; owners see only their groups.
- `GET /api/group?id=<id>` — group details, settings, group-specific delivery history.
- `POST /api/group/settings` — owner can change only allowed keys on their own group.
- `POST /api/broadcast` — selected groups or all authorized groups; refuses any
  out-of-scope group; per-group success/failure is verified and stored.
- `GET/POST /api/config` and `/api/test` are now master-token only.
- Auth: `/webtoken` issues a 30-day, hashed, role-scoped token; optional `WEB_TOKEN`
  env var acts as a master token. `hmac.compare_digest` used for comparison.
- Telegram group stats are refreshed from the live bot and cached for 5 minutes.
- `GET /health` (UptimeRobot) remains public.

## 6. Lightweight tool use (agent) — implemented

Ten constrained tools exposed both as OpenAI-style `tools` and a deterministic
natural-language fallback:

`list_groups_admin_status`, `broadcast_groups`, `set_group_welcome`,
`set_group_setting`, `delete_group_message`, `generate_python_script`,
`read_work_file`, `write_work_file`, `report_from_document`, `web_research`.

Safety properties:

- **No code execution tool exists.** Generated Python files are written to `generated/`
  for review and are never run by the bot.
- File tools are sandboxed to `generated/`; traversal, absolute paths, and hidden
  filenames are rejected; writes never overwrite silently.
- Web fetch blocks localhost, `.local`, private/loopback/link-local/reserved IPs.
- Broadcasts, setting changes, and message deletion require an inline **Approve/Deny**
  button. Only the requesting actor or the Master Owner can approve.
- Scope is re-checked at approval time (an owner cannot smuggle in another group ID).
- Actions are verified after execution and reported honestly; failures are not reported
  as success. All tool requests/decisions are audited.

### Free web search (part of the agent) — implemented

- `/search <query>` plus **natural-language triggers**: asking for latest/current info,
  news, research, prices, scores, weather, "search the web", or pasting a URL now routes
  through the same search core automatically — no special command needed.
- Provider is **DuckDuckGo's free HTML + lite endpoints** (no API key, no paid service).
  Results include title, short snippet, and a clickable source link; HTML is escaped.
- "Summarize/read/explain this page" fetches the top (or pasted) public page, strips
  scripts/styles, and uses the existing AI provider to produce 3–5 factual bullets
  **only from the supplied page text**. If the AI call fails, the bot says so and shows
  the raw result instead of inventing facts.
- Error handling: 12-second timeouts, two endpoint fallbacks, honest failure messages.
  Private/loopback/reserved URLs are rejected before any fetch.
- Rate limit: **8 searches per 60 seconds per user** (in-memory sliding window; resets
  on bot restart). A friendly wait message is returned instead of silently failing.
- Admin panel: new **🔍 Web Search** action and a **📋 All Commands** button listing every
  command with details (user, master, owner, dashboard). `/help` also includes `/search`.

## 7. Storage & safety — implemented

- `threading.RLock` plus atomic `os.replace` writes for `data.json`, chats, and persona.
- `.gitignore` excludes `.env`, `data.json`, `chats/`, `backup/`, `generated/`, `*.log`,
  `*.tmp`, `__pycache__/`, `.venv/`.
- No real API keys, private chat histories, or runtime data were added to the repo.
- No git commits were made; project files remain untracked as before.

## 8. Verification performed

- `python -m py_compile bot.py` — passes.
- `persona.json` and `data.json` parse as valid JSON.
- Full main-block startup smoke test (with polling disabled) — all handlers register.
- Nine automated suites pass: Stage B (`/learn`), Stage C (owners), Stage D (web API),
  Stage E (agent/tools), learning confirmation flow, previous implementation suite,
  plan-page cleanup suite, free-web-search suite (parsing, rendering, page reading, AI
  summarization, rate limiting, failure honesty, `/search`, agent integration, and
  admin-panel commands/buttons), and the conversation-skill suite (identity preservation,
  both prompt paths, no duplicate injection, learned-instruction precedence).
- Real `data.json` was not modified: no test groups, owners, tokens, logs, or pending
  approvals were written to it.

## 9. Ishani Control Center (Next.js frontend) — implemented

- Dedicated App Router frontend in `dashboard/` with the dark design tokens from the
  existing embedded page (`#07080f` background, `#12141f` cards, gradient accents).
  Pages: `/`, `/groups`, `/groups/[id]`, `/owners`, `/broadcasts`, `/ai-chats`, `/tasks`,
  `/settings`. Reusable components live under `dashboard/components/{layout,dashboard,
  groups,broadcasts,chat,tasks,shared}`.
- Same-origin `/api/*` calls are handled by Python. The internal Next.js server also has a
  runtime proxy at `dashboard/app/api/[...path]/route.ts` for manual/direct frontend use.
  `bot.py` starts the dashboard automatically: it installs/builds on first run if needed,
  launches `next start` on an internal `DASHBOARD_PORT` (default 3000), sets
  `API_BACKEND_URL` for the child, and terminates it on exit. Set `ISHANI_NO_DASHBOARD=1` to
  disable auto-start.
- No embedded HTML remains in `bot.py`. All non-API page and asset requests are proxied to
  Next.js through the single public `WEB_PORT`, so the dashboard and API share one port.
  `/api/*` and `/health` stay on the Python server.
- Token gate removed: the dashboard opens directly with master access and sends no auth
  header. `/webtoken` and `WEB_TOKEN` still work for API clients; when a token is supplied,
  Group Owners remain scoped to `session["group_ids"]` on every backend endpoint.
- Backend endpoints added/extended in `bot.py`: `GET /api/overview`,
  `/api/group/members`, `/api/owners`, `/api/schedule`, `/api/ai/history`, `/api/tasks`,
  `/api/lessons`, `/api/activity`; `POST /api/group/action`, `/api/group/remove`,
  `/api/owners/invite`, `/api/owners/verify`, `/api/schedule`, `/api/schedule/remove`,
  `/api/ai/chat`, `/api/lessons`. `/api/groups` and `/api/group` were enriched with real
  username, invite link, registration dates, admin/permission and alert fields;
  `/api/group/settings` gained an explicit welcome/goodbye/links/spam/AI-instruction key
  whitelist; `/api/broadcast` gained file_id/public-URL photo/video/document support.
- AI chat modes in the UI map to real backend modes (assistant, group_manager, research,
  auto_fix, script_generator, automation) with task records, execution logs, attachments
  (file names only), confirmation for sensitive actions, and links to task history.
- Verified: `npm install`, TypeScript typecheck, and `npm run build` pass; all nine Python
  regression suites still pass; backend compile, startup smoke and isolated HTTP smoke
  (master token, 401 without token, 403 for out-of-scope groups, empty-state payloads) pass.

---

## Known limits / not implemented (honest)

1. **No MongoDB.** All persistence is JSON by design for now; MongoDB remains future work.
2. **Web search is intentionally lightweight.** DuckDuckGo HTML/lite only (no API key,
   no paid provider). No JS rendering, no images/videos, no Google/Bing. Remote sites can
   block or rate-limit fetches. The 8/minute rate limit is in-memory and clears on restart.
   AI page summaries require a reachable provider; otherwise the bot returns the raw
   results and states that the summary is unavailable. URL safety and parsing were tested
   offline; live internet reachability depends on the host network.
3. **Excel/XLSX is not parsed directly.** The bot explains the limitation and can generate
   a script for the user to run (with `openpyxl`); it never executes that script.
4. **Native tool calling depends on the model.** Local models without native `tools`
   support fall back to deterministic phrase detection. Complex chained/ambiguous
   multi-step plans are not supported; unsupported requests are declined rather than faked.
5. **Group Owner actions require group context (or the web page).** `actor_may_authorize()`
   only authorizes a Group Owner inside one of their own groups; a private DM with the
   bot is not enough for broadcast/delete/permission actions. The authenticated
   `/groups` dashboard is the private-channel alternative. This is a deliberate
   security boundary, not an oversight.
6. **Broadcast "verification" means the Telegram send call succeeded.** There are no read
   receipts; failed sends are counted and shown with their error text.
7. **Report AI summaries need a reachable provider.** The report file, statistics, and
   source text are still saved and verified if the AI summary call fails.
8. **"Chelsea Live" company-info update remains unresolved.** A safe, evidence-only
   version was not approved earlier; unsupported claims (guaranteed returns, full loss
   protection, 6-level income, deleting fraud complaints, pretending to be human) were
   refused and remain refused.
9. **Telegram cannot list all non-admin members.** The dashboard shows real administrators
   (when the bot can read them) plus only users actually observed by the bot. It never
   fabricates member names, and says so in the Members tab.
10. **Pin/delete verification is partial.** Pin checks `get_chat().pinned_message` when
    available; a deleted message cannot be re-read, so delete is reported as unverifiable
    rather than guessed. Mute/unmute is a stored group setting, not a Telegram API call.
11. **Scheduled messages are queued, not delivered by the new endpoint.** They are stored in
    `data.json`; the existing scheduler job does not consume that key yet, and the API says
    so honestly. No send is claimed.
12. **Media broadcasts need a Telegram `file_id` or public URL.** Private/local URLs are
    rejected. Browser attachments in AI chat provide file names as context only; no file is
    uploaded from the browser and generated scripts are never executed.

---

## Quick operator reference

- Restart the bot after code/persona changes.
- Free web search: `/search latest news` or just ask naturally; paste a URL with
  "summarize" to read it. Limit 8/min/user. Admin: `/panel` → 🔍 Web Search / 📋 All Commands.
- Just run `python bot.py` — it starts the bot, the API and the Next.js dashboard together.
  Open `http://<host>:8080/`; the dashboard and API share the same port.
- No dashboard token needed. `/webtoken` and `WEB_TOKEN` remain available for API clients.
- Ports: single public `WEB_PORT` (default 8080); `DASHBOARD_PORT` (default 3000) is internal
  only and is auto-adjusted if set equal to `WEB_PORT`.
- Manual frontend work: `cd dashboard && npm run dev`; set `API_BACKEND_URL` if the bot is
  not on `http://127.0.0.1:8080`. Restart the bot after Python changes.
- All new keys in `data.json` (`owners`, `invitations`, `web_tokens`, `broadcast_log`,
  `pending_tools`, `audit_log`, `scheduled_messages`, `web_tasks`) are created lazily and
  are gitignored.
