# External trigger (reliable scheduling)

## Why

GitHub's `schedule` trigger is best-effort: it runs from a shared queue and, on
this repository, has been firing **anywhere from ~35 minutes to ~10 hours late**
(measured against the cron slot). The run is created and started within seconds
of each other, so the delay is entirely GitHub's scheduler — nothing in this
repo causes it, and nothing in the workflow file can control it.

`workflow_dispatch`, by contrast, starts **immediately**. So we trigger the
workflow from an external timer and stop depending on `schedule` for timing.

The workflow is idempotent, so this is safe: whichever trigger fires first after
the day's bhavcopy is available sends the one report; every other trigger that
day does nothing.

> The in-workflow `schedule` ladder is kept as a **fallback** — if the external
> timer is down, you still get a report (just late).

## What the external timer needs to do

Send an HTTP POST to GitHub's workflow-dispatch endpoint, once per slot:

```
POST https://api.github.com/repos/dheerkapil/ivp-ivr-analysis/actions/workflows/daily_update.yml/dispatches
Accept: application/vnd.github+json
Authorization: Bearer <FINE_GRAINED_PAT>
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json

{"ref":"main"}
```

A `204 No Content` response means it was accepted. (A `401`/`403` means the
token is wrong or lacks permission; a `404` usually means the token can't see
the repo.)

## Step 1 — create the token

1. Open https://github.com/settings/personal-access-tokens/new (a **fine-grained**
   token, not a classic one).
2. Token name: `ivp-ivr-dispatch`.
3. Expiration: pick a date and set yourself a reminder to renew — when it
   expires, the external trigger silently stops working.
4. Repository access: **Only select repositories** → `ivp-ivr-analysis`.
5. Repository permissions: set **Actions → Read and write**. That is the only
   permission required.
6. Generate and copy the token (`github_pat_…`). Treat it like a password.

The token can only trigger workflows on this one repository, so the blast radius
is small — and you can revoke it at any time.

## Step 2 — create the cron job

Any scheduler that can make an HTTPS POST on a schedule works (cron-job.org,
EasyCron, a small cron on a VPS, Cloudflare Workers, …). With
[cron-job.org](https://cron-job.org) (free):

1. Create an account and a new cron job.
2. **Title**: `IVP/IVR dispatch`.
3. **URL**: `https://api.github.com/repos/dheerkapil/ivp-ivr-analysis/actions/workflows/daily_update.yml/dispatches`
4. **Schedule**: every 30 minutes between 18:00 and 23:30 IST. In expert/cron
   mode: `0,30 18-23 * * 1-5`, **timezone `Asia/Kolkata`**.
5. **Request method**: `POST`.
6. **Request body**: `{"ref":"main"}`.
7. **Headers**:
   - `Accept: application/vnd.github+json`
   - `Authorization: Bearer <FINE_GRAINED_PAT>`
   - `X-GitHub-Api-Version: 2022-11-28`
   - `Content-Type: application/json`
8. Save, then use the service's **Test run** button — you should see HTTP `204`,
   and a new run appear in the repo's Actions tab within seconds.

### Optional second job — the end-of-window alert

The ladder above ends at 23:30 IST. Add one more job so the "no data by
midnight" alert can fire:

- **Schedule**: `0 0 * * 2-6`, timezone `Asia/Kolkata` (00:00 IST, Tue–Sat —
  i.e. just after each trading day's window closes). Same URL/headers/body.

## Step 3 — verify

Trigger a run manually at any time with the helper script:

```bash
GH_TOKEN=github_pat_xxx bash scripts/dispatch.sh
```

It prints the HTTP status. Then check the Actions tab: the run should appear and
start within a couple of seconds.

## Things to know

- **Keep the token out of the repo.** It lives only in the external service (and
  your shell when testing). `scripts/dispatch.sh` reads it from the environment;
  never paste it into a file that gets committed.
- **The workflow is idempotent**, so it's fine if the external timer and the
  fallback `schedule` both fire — you still get one report.
- **If the external service goes quiet** (expired token, service outage), the
  fallback `schedule` ladder still delivers — just at GitHub's unpredictable
  time. Worth a glance at the Actions tab every week or two.
