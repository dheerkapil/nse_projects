# Setup — getting this into GitHub

Everything here is done once. The tree you unzipped is the finished project;
nothing needs editing before the first push.

---

## 1. Create the repository

Create an empty repo named **`nse-ops`** under your account (GitHub mobile app →
Profile → Repositories → create, or the web). **Make it public.**

Public matters for one reason: standard GitHub-hosted runners are free and
unlimited in public repositories. In a private repo you get 2,000 minutes a month
on the Free plan, and this project will spend roughly that in a month of normal
operation. There are no credentials in the tree — every token is read from
Actions secrets — so public costs you nothing security-wise.

Don't initialise it with a README, .gitignore or licence; you want it empty.

## 2. Push the tree

From a laptop, in the unzipped folder:

```bash
git init
git add -A
git commit -m "Consolidate five NSE pipelines"
git branch -M main
git remote add origin https://github.com/dheerkapil/nse-ops.git
git push -u origin main
```

If you would rather keep the commit history of the five original repos, do this
instead of `git init` — it grafts each repo in as a subtree with its history
intact. It must be the first thing you do, before any of your own commits:

```bash
git clone https://github.com/dheerkapil/nse-ops.git && cd nse-ops
for r in price-movers fno-automation ivp-ivr-analysis nse-rsi-divergence gift-nifty-oi; do
  git subtree add --prefix "projects/$r" "https://github.com/dheerkapil/$r.git" main
done
# then copy in .github/, .gitignore and README.md from the zip, commit, push
```

The plain push is simpler and loses nothing you actually use: the data files
(CSVs, `data/daily/*.json`, `data/history/*.csv.gz`) come across in the tree. Only
the commit log stays behind, and it stays in the archived repos.

## 3. Add the secrets

Settings → Secrets and variables → Actions:

| name | type | value |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | secret | your bot token |
| `TELEGRAM_CHAT_ID` | secret | your chat id |
| `TELEGRAM_ERROR_CHAT_ID` | secret | same as above, or a separate chat |
| `TELEGRAM_TOKEN` | secret | optional, legacy fallback for F&O |

Then the **Variables** tab: `PROFILE` = `tight` (or `loose`) for the RSI scan.

## 4. Test before you trust it

Actions → **batch** → Run workflow → pick one pipeline at a time, starting with
`gift-nifty-oi` (cheapest, no market dependency). Then `price-movers`. Then the
three that need the NSE bhavcopy.

Two things will look odd on the first run and are both expected:

- **`nse-rsi-divergence` will take much longer than usual.** Caches are per-repo,
  so the new repo starts with no cached price DB and the job runs the ~220-day
  backfill once. Later runs are fast.
- **`ivp-ivr-analysis` rebuilds its database from `data/daily/*.json`** at the
  start of every run, so the first run takes a couple of minutes. That is the
  existing design, unchanged.

## 5. Point the external cron at the new workflow

Your `gift-nifty-oi` (and `ivp-ivr-analysis`, if you set it up) are dispatched by
cron-job.org with a fine-grained PAT. Those calls must now target `batch.yml`
**and pass the pipeline name** — otherwise a dispatch runs all five pipelines at
once.

Endpoint:

```
POST https://api.github.com/repos/dheerkapil/nse-ops/actions/workflows/batch.yml/dispatches
```

Body:

```json
{"ref":"main","inputs":{"pipeline":"gift-nifty-oi"}}
```

Use `"pipeline":"ivp-ivr-analysis"` for the other one. The PAT needs
`Actions: read and write` on `nse-ops`; the old PAT was scoped to the old repo and
will not work here. This is the single point of failure you already flagged in
your own README — if it expires, nothing dispatched by cron runs.

## 6. Repoint the RSI dashboard

`projects/nse-rsi-divergence` still contains `render.yaml` and `Procfile`. The
Render service that serves that dashboard builds from the repo root, so it will
break unless you set:

- **Root directory:** `projects/nse-rsi-divergence`
- **Build:** `pip install -r requirements.txt`
- **Start:** `gunicorn --chdir web app:app --bind 0.0.0.0:$PORT`

Nothing in GitHub will warn you if you forget — the dashboard just serves stale
signals.

## 7. Retire the old repos — in this order

Do not leave both sets running: every pipeline is idempotent *within* its own
repo, but the old repo and the new one each have their own state, so you would get
two Telegram messages per day.

1. In each of the five old repos: Actions → the workflow → ⋯ → **Disable
   workflow**. That stops the cron without deleting anything.
2. Run the new `batch.yml` manually once per pipeline and confirm the message
   arrives.
3. Only then archive the old repos (Settings → Danger Zone → Archive). Archive
   rather than delete — you keep the history and can restore in one click if
   something was missed.

## What changed versus the five separate repos

- **`ivp-ivr-analysis` no longer force-pushes an orphan commit.** That trick
  rewrote the entire branch on every run and would have deleted the other four
  projects. It now makes an ordinary scoped commit. The repo-growth problem it
  was solving is handled by `.gitignore` instead: the rebuilt `iv_history.db`
  (13 MB) and the per-day workbook (~670 KB) are no longer committed, and
  `data/daily/*.json` remains the record.
- **Each commit is path-scoped.** `git add` only touches the calling pipeline's
  folder, so one job can never commit another's half-written data.
- **Pushes retry with a rebase.** Five writers on one branch means occasional
  races; the shared action retries up to five times before failing.
- **RSI cache key renamed** to `rsi-price-db-v3-`. Caches are now shared across
  five pipelines in one repo, so a namespaced key keeps it from being evicted by
  someone else's cache.
- **Concurrency is per pipeline, not per repo.** A single group would let a
  45-minute F&O run block the 16:00 price-movers slot — the exact delay you set
  out to remove.
- **Failure notices are per job**, so a red run tells you which pipeline broke
  instead of just that `batch` failed.

## If a push fails with "could not push after 5 attempts"

Two pipelines finished within seconds of each other and kept stealing the branch.
The run is red but the data is intact in that job's workspace — just re-run the
job. If it happens routinely, stagger the overlapping slots by five minutes.
