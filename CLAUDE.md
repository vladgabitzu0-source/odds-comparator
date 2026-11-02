# Odds comparator

Football 1X2 odds comparison. Odds from several sources are converted to implied
probability (`p = 1 / odd`), compared against the cross-source median, and
matches whose odds diverge by more than ~3-4% are flagged as abnormal value.

## Architecture
- `backend/scrapers/` one module per source (`superbet.py` live, `sample_data.py` labeled sample data)
- `backend/analysis/calculator.py` isolated scraping, matching, implied-probability analysis, best odds per bookmaker
- `backend/api/main.py` FastAPI app with an in-memory cache and a background refresh job
- `frontend/` React + Vite + Tailwind single-page UI

## Run (Windows PowerShell)
```powershell
# backend
cd backend
py -m pip install -r requirements.txt
py -m playwright install chromium
py -m uvicorn api.main:app --reload

# frontend (second terminal)
cd frontend
npm install
npm run dev
```

## Checks
```powershell
cd backend;  py -m compileall -q .
cd frontend; npm run lint; npm run build
```

## Conventions
- Keep code simple and commented; explain non-obvious decisions.
- One scraper per file; a failing source must never break the others.
- Never print raw HTML/JSON from scraped pages; log one-line summaries.
- Prefer stable Playwright locators (text, structural attributes) over long CSS paths.
- Outbound bookmaker links use `target="_blank"` and `rel="noopener noreferrer"`.
- Sample data must always be labeled as sample data in the API and UI.
