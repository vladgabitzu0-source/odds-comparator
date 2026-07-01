# Project Status

## Last Updated
26 iunie 2026

## What's Done
- [x] VS Code + Claude Code installed and authenticated
- [x] Project folder structure created (backend/scrapers, analysis, api, database + frontend)
- [x] Python venv created and activated
- [x] CLAUDE.md written
- [x] Python packages installed (fastapi, uvicorn, playwright, pandas, apscheduler)
- [x] Playwright + Chromium installed
- [x] Git repo initialized and connected to GitHub
- [x] Superbet scraper ✅ — 65/66 matches, harvest-as-you-scroll approach
- [x] Betano scraper ✅ — expands all collapsed competition sections, ~380 matches
- [x] Analysis calculator with tier filter ✅ — implied-probability divergence vs
      median, value flag (>4%), sanity odds cap (≤10.0), main/obscure tier field

## In Progress
- Nothing

## Next Steps
1. Build FastAPI endpoint (backend/api/main.py) — serve the value analysis as JSON
2. Build React frontend — odds comparison table

## Blockers
None

## Notes
- Use `venv\Scripts\activate` to activate venv on Windows before any py commands
- Run backend with: `cd backend && py -m uvicorn api.main:app --reload`
- Superbet selectors: .e2e-event-row (container), .e2e-event-team1-name,