# Ishani Control Center (Next.js)

Separate App Router frontend for the existing Python Telegram bot. All Telegram operations,
authentication, role scoping and JSON persistence remain in `bot.py`; this app only renders
data and calls authenticated endpoints.

## Run locally

**Simplest: run only the bot.** From the project root:

```bash
python bot.py
```

`bot.py` installs dependencies/builds on first run if needed, starts `next start` on an
internal port, and serves the dashboard **directly on the bot port**. Pages and Next.js
assets are proxied through `WEB_PORT`; `/api/*` and `/health` are answered by Python.
Open `http://127.0.0.1:8080` — no second port is needed.

Useful environment variables:

- `WEB_PORT` — single public port for dashboard + API (default `8080`)
- `DASHBOARD_PORT` — internal Next.js port (default `3000`; ignored if it equals `WEB_PORT`)
- `ISHANI_NO_DASHBOARD=1` — disable auto-start (useful for manual frontend work)

Manual frontend development:

```bash
cd dashboard
npm install
npm run dev            # http://127.0.0.1:3000
API_BACKEND_URL=http://127.0.0.1:8099 npm run dev   # bot on another port
```

Manual production build:

```bash
npm run build
npm start
```

`app/api/[...path]/route.ts` proxies same-origin `/api/*` requests at runtime to
`API_BACKEND_URL` (default `http://127.0.0.1:8080`). In the normal `python bot.py` setup the
browser stays on `WEB_PORT` and Python answers `/api` directly; the Next.js proxy is used for
manual frontend development or direct access to the internal server. CORS headers are still
available if you point the frontend at a different origin.

## Authentication

No dashboard token is required — open `http://127.0.0.1:8080` and the Control Center loads
directly with master access. The lock screen and token field were removed.

For API clients that still pass `Authorization: Bearer <token>`, `/webtoken` and `WEB_TOKEN`
remain supported and owner tokens keep their group scope. Requests without a token are
treated as the master owner.

## Pages

| Route | Purpose |
| --- | --- |
| `/` | Overview: groups, members, admins, owners, active/inactive state, bot status, alerts, activity |
| `/groups` | Searchable/sortable groups table, selection for broadcasts, invite copy, remove (master) |
| `/groups/[id]` | Tabs: Overview, Administrators, Members, Permissions, Moderation, Settings, Activity |
| `/owners` | Master-only invitations, verification, owner list and invitation list |
| `/broadcasts` | Text/photo/video/document broadcasts to selected or all authorized groups |
| `/ai-chats` | Ishani chat with six modes, confirmations, attachments, task IDs |
| `/tasks` | Task status, execution logs and outcomes (auto-refresh) |
| `/settings` | AI provider/model, global lessons, scheduled messages, history links |

## API endpoints used

GET: `/api/overview`, `/api/groups`, `/api/group`, `/api/group/members`, `/api/owners`,
`/api/schedule`, `/api/ai/history`, `/api/tasks`, `/api/lessons`, `/api/activity`,
`/api/config`.

POST: `/api/group/action`, `/api/group/remove`, `/api/group/settings`, `/api/owners/invite`,
`/api/owners/verify`, `/api/schedule`, `/api/schedule/remove`, `/api/broadcast`,
`/api/ai/chat`, `/api/lessons`, `/api/config`, `/api/test`.

## Honest limitations

- Telegram's Bot API cannot enumerate every non-admin member. Only real administrators and
  users the bot has actually observed are shown; unavailable data is labelled, never faked.
- Media broadcasts require a Telegram `file_id` or a validated public URL. Chat attachments
  send file names as context only — nothing is uploaded from the browser.
- Scheduled messages are queued in `data.json` and explicitly reported as not yet sent;
  the existing scheduler does not consume that key.
- Pin verification depends on Telegram exposing `pinned_message`; deleted messages cannot be
  verified. Mute/unmute is a stored group setting.
- `auto_fix` is read-only diagnostics. Fixes and non-whitelisted automation require
  confirmation and are never applied automatically.
- Generated scripts are written under `generated/` and are never executed.

## Verification

```bash
npm run typecheck
npm run build
```

The npm scripts call the local binaries via `node ./node_modules/...` so they also work in
directories whose path contains `&`.
