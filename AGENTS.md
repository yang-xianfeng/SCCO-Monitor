# AGENTS.md

## Repo overview

Single‑file Python monitor for SCCO (Southern Copper) vs copper futures.
GitHub Actions drives daily collection; CSV persists history; Plotly HTML
served via GitHub Pages.

**Entrypoint:** `main.py` — fetch → Cola coefficient → CSV append → HTML → push

## Commands

```bash
pip install -r requirements.txt
python main.py              # single run (local test)
pip install pytest pytest-mock && python -m pytest tests/ -v
```

## Structure

```
main.py              # the whole program (~300 lines)
data/history.csv     # daily OHLCV + Cola coefficient (upsert by date)
docs/index.html      # Plotly candlestick chart (regenerated each run)
docs/.nojekyll       # must exist — disables Jekyll on Pages
tests/test_main.py   # 39 tests: calc, CSV, HTML, data, notify
.github/workflows/run.yml
```

## Key facts

- **Dependencies:** `yfinance`, `requests`, `pandas`. Everything else is stdlib.
- **Configuration:** environment variables only — `USER_COST`, `FEISHU_WEBHOOK`,
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Notifications are optional.
- **No database, no server, no framework.** CSV is the data store.
- **CSV upsert:** same‑date rows overwrite (not duplicate), re‑read sorts by date.
- **GitHub Actions:** `schedule` + `workflow_dispatch`. Two runs per weekday
  (open / close US equity). Workflow order: run → configure-pages →
  upload-pages-artifact → deploy-pages → git-auto-commit.
- **Pages source must be "GitHub Actions"** (not "Deploy from a branch").
  The workflow handles both committing and deploying.
- **No test runner config** — just `pytest` directly. No lint/typecheck yet.
- **GitHub Pages:** serves `docs/` content via Actions artifact deployment.

## Signal logic

Cola coefficient = actual_market_cap / anchor_market_cap

| Ratio     | Signal  |
|-----------|---------|
| ≤ 1.10    | safe    |
| 1.10–1.20 | watch   |
| 1.20–1.50 | hot     |
| ≥ 1.50    | danger  |

## What not to add

- No technical analysis indicators (MACD/RSI/MA). The Cola coefficient IS the
  strategy.
- No package / namespace wrapping. A flat `main.py` is intentional.
- No pydantic, no click, no typer. Stdlib + env vars is enough.
- No persistence beyond CSV. No database, no ORM.
