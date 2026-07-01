# ComparaCote.ro — Romanian Betting Odds Comparison Site

## Project Goal
A website that scrapes odds from Romanian betting sites, compares them using
implied probability divergence, and flags abnormally high odds. Monetized via
affiliate links to licensed operators.

## Tech Stack
- Backend: Python, FastAPI, Playwright, pandas, SQLite, APScheduler
- Frontend: React + Vite + Tailwind CSS
- Deployment: Railway (backend, Docker + Chromium), Vercel (frontend)
- Domain: comparacote.ro (DNS via ROTLD nameservers → Vercel)

## Project Structure
comparacote/
├── backend/
│   ├── scrapers/      # One file per betting site
│   ├── analysis/      # Implied probability + best-odds-per-bookmaker
│   ├── api/           # FastAPI endpoints
│   └── database/      # SQLite logic
└── frontend/
    └── src/

## Core Logic
Convert odds to implied probability: p = 1/odd
Compare each site's probability against median of all sites
Flag divergence > 3-4% as abnormal value

## Sites to Scrape (MVP)
1. Superbet
2. Betano
*(Keep scraper architecture modular so it's easy to scale to 5+ sites later.)*

## Sports (MVP)
- Football only, 1X2 market only

## Site Features (Frontend)
### Tab 1 — Comparație (meciuri comune între site-uri)
- Sub-tab: Ligi principale (fără (R), (F), U19/U20/U21/U22/U23 în nume)
- Sub-tab: Restul ligilor (inclusiv rezerve, feminin, tineret)

### Tab 2 — Cele mai bune cote pe casă
- Pentru fiecare casă scraped: top 5 cele mai valoroase cote ale zilei
  (cele unde acea casă bate cel mai mult mediana)
- Util pentru useri cu cont pe un singur site
- Nu necesită overlap între site-uri — fiecare casă analizată independent
- Fiecare rând = link de afiliere (ideal deep-link per meci)

### Tier System (în calculator.py)
- tier = "main": niciun termen obscur în numele echipelor
- tier = "obscure": conține (R), (F), U19, U20, U21, U22, U23

## Design System
- Dark theme. Fundal #0d1117, carduri #161d27, borduri hairline #1f2733.
- Accent auriu #e8be6a (logo + highlights), folosit cu parcimonie ca să rămână
  special; auriu dimmer #8a6d35 pentru ".ro" și detalii secundare.
- Text: primary #c9d1d9, muted #8b949e.
- Header: wordmark auriu "ComparaCote.ro", data de azi sus-stânga (faded,
  uppercase, format RO, calculată dinamic), badge "18+".
- Interacțiuni: hover pe rând evidențiază cota cea mai mare; badge "cea mai bună"
  lângă cota câștigătoare; indicator "Actualizat acum X minute".
- Două weighturi font: 400 / 500. Sentence case peste tot. Doar CSS transitions,
  fără librării grele de animație.

## Business & Legal Rules
- Doar operatori licențiați ONJN pentru trafic RO (Superbet, Betano, etc.).
- Fără claim-uri false de tip "garantăm victorii". Doar afirmații verificabile
  (ex: "garantăm cele mai bune cote").
- Footer obligatoriu: disclaimer 18+ / joacă responsabil / linkuri de afiliere.
- Linkuri de afiliere: target="_blank", rel="sponsored noopener noreferrer".
- Deep-link per meci unde scraperul îl capturează; fallback la landing page altfel.

## Developer Notes
- Developer is a beginner in Python and React
- Prefer simple, well-commented code
- Explain non-obvious decisions in comments
- Use `py` instead of `python` for Windows commands

## ⚠️ Agent & Vibe Coding Rules (Token Economy & Focus)
1. **Never dump raw HTML/JSON:** Betting sites have massive, deeply nested DOMs.
   Never print full page sources or large network responses to the console. If you
   need DOM context, ask me to provide a snippet.
2. **Robust Playwright Locators:** Betting sites often use dynamic obfuscated
   classes. Prioritize stable selectors (text content, specific structural
   attributes) over brittle, long CSS paths.
3. **Execution Commands:**
   - Backend run: `cd backend && py -m uvicorn api.main:app --reload` (verify first)
   - Frontend run: `cd frontend && npm run dev`
   - Use ONLY these to start the environments. Do not guess commands.
4. **Isolated Debugging:** If a scraping script in `/scrapers/` fails, fix the
   selectors there. Do not modify the database schema or React frontend unless
   explicitly asked.