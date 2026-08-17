# 311 Civic Pulse

What Torontonians report, and how the city responds.

A civic data dashboard built on the City of Toronto's open
[311 Service Requests](https://open.toronto.ca/dataset/311-service-requests-customer-initiated/)
dataset: 90 days of requests across all 26 wards, with completion rates, open
backlogs, per-ward and per-category trends, a live-ish ticker of recent
requests, and plain-language AI briefs generated nightly from the numbers.

**Live:** [toronto311-jigar.netlify.app](https://toronto311-jigar.netlify.app)

## How it works

```
City of Toronto Open Data (yearly CSV zips)
        |
        v
pipeline.py  ------------>  data/out/civic-pulse.json   (one bundle, ~220 KB)
        |                        |
        +-- DeepSeek API         +-- site/src fetches it at runtime
            (nightly AI briefs:      (React + Vite static app, SVG charts,
             city + 26 wards +       no chart libraries)
             top categories)
        |
        v
cp JSON -> site/dist/data/  ->  Netlify deploy (toronto311-jigar.netlify.app)
```

- `pipeline.py` — stdlib-only. Downloads the current + previous year zips,
  parses them (latin-1 CSVs, ~840k rows), computes 90-day aggregates for the
  city, every ward, and the top 16 request categories, and writes one JSON
  bundle. Then generates plain-language briefs with the DeepSeek chat API —
  one brief for the city, one per ward, one per top category. The API key is
  read server-side from `~/dev/deepseek-harness/.env` and never committed.
- `site/` — React 18 + Vite static app. Hand-rolled SVG sparklines and bars,
  zero chart dependencies. Fetches `data/civic-pulse.json` at runtime.
- Nightly refresh — fully standalone, no agent required. A systemd user timer
  (`toronto311-refresh.timer`, 05:00 America/Toronto, `Persistent=true`) runs
  `refresh.sh`: pipeline -> new JSON copied into `site/dist/` -> Netlify
  redeploy. Logs go to `logs/refresh.log` (also visible via
  `journalctl --user -u toronto311-refresh`). The AI briefs are regenerated
  every night so the summary always matches the numbers on the page.
- Failure alerts: `notify.sh` posts a message to a Discord webhook if
  `WEBHOOK_URL` is present in `.env.discord` (gitignored; optional). Without
  it, failures are visible in the log and journald only.

## A note on the AI briefs

The briefs are generated from the aggregate statistics only — the LLM sees
counts, rates, and dates, never individual requests or locations. Briefs
contain no information beyond what is already on the page as numbers. The
prompt rules: facts only, no speculation, no bullet points, keep numbers exact.

## Local development

```bash
python3 pipeline.py            # needs network; key optional (skips briefs)
cd site && npm install && npm run dev
```

Data license: City of Toronto Open Data (Open Government Licence – Toronto).
Not affiliated with the City of Toronto.
