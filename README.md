# nse-ops

Five NSE data pipelines in one repository, sharing one workflow file, one
scheduler and one set of secrets. Each pipeline keeps its own code, its own
data folder, its own concurrency group and its own Telegram delivery — they
just live side by side instead of in five separate repos.

| pipeline | folder | fires (IST) | what it produces |
|---|---|---|---|
| price-movers | `projects/price-movers` | 16:00 daily | +5% movers CSV → Telegram |
| fno-automation | `projects/fno-automation` | 19:00 daily | EOD F&O buildup → Telegram |
| ivp-ivr-analysis | `projects/ivp-ivr-analysis` | 18:30, retried hourly | IVP/IVR matrix → Telegram |
| nse-rsi-divergence | `projects/nse-rsi-divergence` | 19:05, retried hourly | divergence signals → JSON snapshot |
| gift-nifty-oi | `projects/gift-nifty-oi` | 05:00 Tue–Sat | OI chart → Telegram |
| participant-oi | `projects/participant-oi` | 18:30–23:30, first success wins | participant positioning + chart → Telegram |

Scheduling lives outside GitHub: cron-job.org dispatches `batch.yml` at those
times (see `SETUP.md`), because GitHub's own scheduler can run hours late and
bunched. The `schedule:` block in `batch.yml` holds one late slot per pipeline as
a fallback only.

Every pipeline is still idempotent: each run checks whether today's output
already exists and exits quietly if it does. That is why the overlapping slots
are safe, and why a late run does no harm.

## Workflows

- **`batch.yml`** — the five scheduled pipelines. One job each, gated on
  `github.event.schedule` so a run always executes the pipeline whose slot
  fired, even if GitHub started it late.
- **`manual.yml`** — the one-off jobs: F&O backfill, IVP backfill, DB check,
  clear today's metrics, GIFT probe, holiday refresh, and a Telegram test note.
  Nothing here is scheduled.
- **`.github/actions/commit-push`** — the shared commit helper. It stages only
  the caller's paths, then pushes with a rebase-and-retry loop, because up to
  five pipelines now write to the same branch.

## Secrets

Set these once under Settings → Secrets and variables → Actions:

| secret | used by |
|---|---|
| `TELEGRAM_BOT_TOKEN` | all five |
| `TELEGRAM_CHAT_ID` | all five |
| `TELEGRAM_ERROR_CHAT_ID` | ivp-ivr-analysis |
| `TELEGRAM_TOKEN` | fno-automation (legacy fallback, optional) |

`PROFILE` is read as a repository **variable** by the RSI scan (`tight` or
`loose`).

## Running one pipeline by hand

Actions → `batch` → Run workflow → pick the pipeline. Leave it on `all` only if
you really want all five to run at once.

## What deliberately did not change

The scripts are untouched. Each job sets `working-directory` to its project
folder, so every relative path inside the code — `data/`, `output/`, `config/` —
resolves exactly as it did in the old repo.
