# PT — paper trading bot

Runs the full pipeline (data → technical + fundamental signals → strategy
→ risk gate → execution → logging) against Alpaca's **paper** account —
no real money involved. Same code runs the live version later, just a
different set of keys.

## Setup — do this in order, all in one pass

### 1. Create a free Alpaca account
https://alpaca.markets/ → sign up. This gives you a paper trading account
automatically — no funding, no approval needed.

### 2. Get your paper API keys
- Alpaca dashboard → make sure you're on **Paper Trading** (not Live).
- API Keys section → generate a new key.
- Copy both the **Key ID** and **Secret Key** immediately — the secret is
  only shown once.

### 3. Install Python (skip if you already have 3.10+)
Check with `python3 --version` in a terminal. If missing, install from
https://www.python.org/downloads/

### 4. Set up the project locally
- Unzip this project.
- Rename `.env.example` to `.env`.
- Open `.env`, paste in your two keys from step 2.
- Leave `MODE=paper` as is.

**`.env` stays on your computer only — never upload it anywhere.**

### 5. Test it locally first
```
pip install -r requirements.txt
python3 main.py
```
Confirm this runs with no errors before touching GitHub — much easier to
fix problems here than in the cloud.

### 6. Upload to GitHub — everything, in one upload
- Create a free GitHub account if needed.
- New repository → name it `pt-bot` → set to **Public** (required for
  free dashboard hosting — this is safe, your real keys never go in the
  code, only in Secrets in step 7).
- In File Explorer: **View → Show → Hidden items** (so the `.github`
  folder is visible).
- Repo page → **Add file → Upload files** → select and drag in
  *everything* inside the `pt-bot` folder at once — all files and all
  folders (`signals`, `docs`, `.github`) together. Do **not** upload
  `.env` — only `.env.example` should go up.
- Commit changes.
- Spot-check a couple of uploaded files on GitHub afterward to confirm
  they look complete — catching a bad upload here saves debugging later.

### 7. Add your keys as GitHub Secrets
Settings → Secrets and variables → Actions → New repository secret:
- `APCA_API_KEY_ID` → your key ID
- `APCA_API_SECRET_KEY` → your secret key

These are encrypted and never appear in your code, logs, or the repo
itself.

### 8. Turn on the dashboard
Settings → Pages → Source: "Deploy from a branch" → Branch `main`,
folder `/docs` → Save. Live in a minute or two at:
`https://YOUR-USERNAME.github.io/pt-bot/`

### 9. Run it for the first time
Actions tab → **PT trading bot** → **Run workflow** → **Run workflow**.
Wait ~30 seconds, refresh, confirm a green checkmark, then check the
dashboard URL.

From here it runs itself every 30 minutes during US market hours
(weekdays) — no PC required, check the dashboard whenever you want.

## Files
- `main.py` — runs one full cycle, start to finish
- `config.py` — all settings, loaded from `.env` (or GitHub Secrets in the cloud)
- `signals/technical.py`, `signals/fundamental.py` — the two signal agents
- `strategy.py` — combines signals into a trade proposal
- `risk.py` — approves/rejects proposals, position limits, drawdown circuit breaker
- `execution.py` — the only file that talks to Alpaca for orders
- `portfolio_monitor.py` — reads real account/position state from Alpaca
- `compliance.py` — kill switch (`HALT` file) and basic anomaly check
- `db.py` — logs every decision to SQLite
- `export_dashboard.py` — exports the log to `docs/data.json` for the dashboard
- `docs/index.html` — the dashboard itself (static page, no server)
- `.github/workflows/trade.yml` — the scheduler

## Safety notes
- `MAX_POSITION_PCT` (default 5%) caps how much of the portfolio goes into
  any single trade.
- `DRAWDOWN_HALT_PCT` (default 8%) stops new buys if the account drops 8%
  from its peak equity — existing stop-losses still work regardless.
- Every buy is a bracket order — stop-loss and take-profit are attached
  at the broker the moment the trade is placed, so they'll fire even if
  the bot isn't running.
- To manually pause everything, create an empty file named `HALT` in the
  repo root and commit it. Delete it to resume.

## If something breaks
Screenshot the failed step's expanded log from the Actions tab (click
into the run → click the red X step → click the small triangles to
expand nested sections) and send it over — the actual error text is what
matters, not just "it failed."
