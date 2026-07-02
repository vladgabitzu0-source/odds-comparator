import { useEffect, useState } from "react";

// Where the FastAPI backend lives. Defaults to the Railway production API, but
// can be overridden for local dev by setting VITE_API_URL in a .env file
// (e.g. VITE_API_URL=http://localhost:8000) — Vite exposes VITE_* vars on
// import.meta.env at build time.
const API_BASE =
  import.meta.env.VITE_API_URL ||
  "https://odds-comparator-production.up.railway.app";
const API_URL = `${API_BASE}/api/odds`;

// Generic landing page per source. Used ONLY as a fallback when a match has no
// per-match deep link. Mirrors AFFILIATE_LINKS in calculator.py. "sample" is the
// static demo source (labelled "Demo Source"), not a real bookmaker.
const FALLBACK_LINKS = {
  superbet: "https://superbet.ro/pariuri-sportive/fotbal",
  sample: "https://example.com/date-demo",
};

// The three 1X2 outcomes, in display order (1 = home, X = draw, 2 = away).
const OUTCOMES = ["home", "draw", "away"];

// Column header label for each outcome. Sentence case, with the bet code first.
const OUTCOME_HEADERS = {
  home: "1 (gazde)",
  draw: "X (egal)",
  away: "2 (oaspeți)",
};

// Human-readable label for each outcome, used in the best-odds cards.
const OUTCOME_LABELS = {
  home: "1 (gazde)",
  draw: "X (egal)",
  away: "2 (oaspeți)",
};

// Brand palette. Kept in sync with the CSS custom properties in index.css.
// Inline styles use these so the exact brand hexes are applied precisely;
// Tailwind handles layout/spacing. Gold is used sparingly so it stays special.
const C = {
  bg: "#0d1117",
  card: "#161d27",
  border: "#1f2733",
  gold: "#e8be6a",
  goldDim: "#8a6d35",
  text: "#c9d1d9",
  muted: "#8b949e",
  green: "#3fb950",
  red: "#f85149",
};

// Romanian weekday/month names so the header date renders correctly without
// depending on the browser shipping the "ro-RO" Intl locale data. getDay()
// returns 0 for Sunday, so the days array starts there.
const RO_DAYS = [
  "duminică",
  "luni",
  "marți",
  "miercuri",
  "joi",
  "vineri",
  "sâmbătă",
];
const RO_MONTHS = [
  "ianuarie",
  "februarie",
  "martie",
  "aprilie",
  "mai",
  "iunie",
  "iulie",
  "august",
  "septembrie",
  "octombrie",
  "noiembrie",
  "decembrie",
];

// e.g. "MARȚI, 30 IUNIE 2026". toUpperCase() works on the Romanian diacritics
// (ț → Ț, â → Â) so the uppercase header reads correctly.
function romanianDate(d = new Date()) {
  return `${RO_DAYS[d.getDay()]}, ${d.getDate()} ${
    RO_MONTHS[d.getMonth()]
  } ${d.getFullYear()}`.toUpperCase();
}

// "Acum X minute" label. Romanian uses "de minute" from 20 upward
// (acum 20 de minute), so we branch on the count.
function updatedLabel(mins) {
  if (mins < 1) return "Actualizat acum câteva secunde";
  if (mins === 1) return "Actualizat acum 1 minut";
  if (mins < 20) return `Actualizat acum ${mins} minute`;
  return `Actualizat acum ${mins} de minute`;
}

// Show odds consistently as two decimals (1.9 -> "1.90"). Falls back to the raw
// value if it isn't a finite number, so unexpected data never crashes a render.
function fmtOdd(odd) {
  const n = Number(odd);
  return Number.isFinite(n) ? n.toFixed(2) : String(odd);
}

// For one match, find the single most valuable outcome: the one whose "best"
// site beats the median by the biggest margin. That outcome's higher odd is the
// row's "cea mai bună" pick (highlighted gold on hover).
function bestValue(match) {
  let best = null;
  for (const outcome of OUTCOMES) {
    const a = match.analysis[outcome];
    const site = a.best_site; // "superbet" or "sample" (the higher odd)
    const divergence = a[`${site}_div`]; // how far above median, as a fraction
    const odd = match[site][outcome];
    if (best === null || divergence > best.divergence) {
      best = { outcome, site, divergence, odd };
    }
  }
  return best;
}

// One outcome column for a match: both bookmakers' odds stacked, with the higher
// (better-paying) one emphasised. When this is the row's best-value outcome it
// also gets the "cea mai bună" badge + a value chip, and its winning odd carries
// the .best-odd class that lights up gold on row hover.
function OutcomeCell({ outcome, match, best }) {
  const sb = match.superbet[outcome];
  const sp = match.sample[outcome];
  const winnerSite = match.analysis[outcome].best_site; // higher odd here
  const isBestOutcome = best.outcome === outcome;

  // One "Bookmaker  odd" line. `winner` = this site has the higher odd for the
  // outcome (emphasised). `mark` = this exact odd is the row's best value. The
  // odd itself is an affiliate link to the bookmaker's per-match deep link,
  // falling back to its football landing page when no deep link was captured.
  const line = (site, label, odd) => {
    const winner = winnerSite === site;
    const mark = isBestOutcome && winner;
    const href = match[`${site}_url`] || FALLBACK_LINKS[site];
    return (
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px]" style={{ color: C.muted }}>
          {label}
        </span>
        {/* Affiliate link. rel="sponsored" marks it as a paid link;
            noopener/noreferrer for safety. Styling matches the plain odd — only
            the cursor/hover signals it's clickable (best-odd lights up gold). */}
        <a
          href={href}
          target="_blank"
          rel="sponsored noopener noreferrer"
          className={
            mark ? "odd-link best-odd px-1.5 py-px" : "odd-link px-1.5 py-px"
          }
          style={{
            color: winner ? C.text : C.muted,
            fontWeight: winner ? 500 : 400,
          }}
        >
          {fmtOdd(odd)}
        </a>
      </div>
    );
  };

  return (
    <td className="px-3 py-2 align-top">
      <div className="flex flex-col gap-0.5">
        {line("superbet", "Superbet", sb)}
        {line("sample", "Demo Source", sp)}
      </div>
      {isBestOutcome && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          <span
            className="rounded px-1.5 py-px text-[10px]"
            style={{
              color: C.gold,
              backgroundColor: "rgba(232,190,106,0.08)",
              border: "1px solid rgba(232,190,106,0.35)",
            }}
          >
            cea mai bună
          </span>
          <span
            className="rounded px-1.5 py-px text-[10px]"
            style={{
              color: C.green,
              backgroundColor: "rgba(63,185,80,0.08)",
            }}
          >
            +{(best.divergence * 100).toFixed(1)}%
          </span>
        </div>
      )}
    </td>
  );
}

// One <tr> per match. Zebra striping + hover come from .match-row in index.css.
function MatchRow({ match }) {
  const best = bestValue(match);
  return (
    <tr className="match-row align-top">
      <td className="px-3 py-2">
        <div style={{ fontWeight: 500 }}>{match.match}</div>
        <div className="text-[12px]" style={{ color: C.muted }}>
          {match.competition || "—"}
        </div>
      </td>
      {OUTCOMES.map((o) => (
        <OutcomeCell key={o} outcome={o} match={match} best={best} />
      ))}
    </tr>
  );
}

function MatchesTable({ matches }) {
  if (matches.length === 0) {
    return (
      <div
        className="rounded-xl px-4 py-10 text-center text-sm"
        style={{
          backgroundColor: C.card,
          border: `1px solid ${C.border}`,
          color: C.muted,
        }}
      >
        Niciun meci comun în acest tab momentan. Revino după următoarea
        actualizare.
      </div>
    );
  }

  // Show the biggest value first: sort by each match's best-outcome divergence,
  // descending. Copy with [...] so we don't mutate the prop array in place.
  const sorted = [...matches].sort(
    (a, b) => bestValue(b).divergence - bestValue(a).divergence
  );

  return (
    <div
      className="overflow-x-auto rounded-xl"
      style={{ backgroundColor: C.card, border: `1px solid ${C.border}` }}
    >
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr
            className="text-left"
            style={{
              color: C.muted,
              borderBottom: `1px solid ${C.border}`,
            }}
          >
            <th className="px-3 py-3" style={{ fontWeight: 500 }}>
              Meci
            </th>
            {OUTCOMES.map((o) => (
              <th key={o} className="px-3 py-3" style={{ fontWeight: 500 }}>
                {OUTCOME_HEADERS[o]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((m) => (
            <MatchRow key={m.match} match={m} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// One card = one bookmaker's top 5 most valuable odds of the day. Each row is an
// affiliate link out to the bookmaker (deep-link per match where captured).
function BestOddsCard({ bookmaker, picks }) {
  return (
    <div
      className="overflow-hidden rounded-xl"
      style={{ backgroundColor: C.card, border: `1px solid ${C.border}` }}
    >
      <div
        className="flex items-center gap-2 px-4 py-3"
        style={{ borderBottom: `1px solid ${C.border}` }}
      >
        {/* Small gold tick keeps the brand accent present without a full gold
            header. */}
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: C.gold }}
        />
        <h3 className="text-sm" style={{ fontWeight: 500, color: C.text }}>
          {bookmaker}
        </h3>
        <span className="ml-auto text-[11px]" style={{ color: C.muted }}>
          top {picks.length}
        </span>
      </div>

      {picks.length === 0 ? (
        <p className="px-4 py-3 text-sm" style={{ color: C.muted }}>
          Nicio cotă disponibilă.
        </p>
      ) : (
        <ul>
          {picks.map((p, i) => (
            <li
              key={`${p.match}-${p.outcome}`}
              style={{ borderTop: i === 0 ? "none" : `1px solid ${C.border}` }}
            >
              {/* Whole row is the affiliate link. rel="sponsored" marks it as a
                  paid link; noopener/noreferrer for safety. */}
              <a
                href={p.link}
                target="_blank"
                rel="sponsored noopener noreferrer"
                className="affiliate-row flex items-center gap-3 px-4 py-2.5 text-sm"
              >
                <span
                  className="w-4 shrink-0 text-center text-[12px]"
                  style={{ color: C.muted }}
                >
                  {i + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate" style={{ color: C.text }}>
                    {p.match}
                  </span>
                  <span className="text-[12px]" style={{ color: C.muted }}>
                    {OUTCOME_LABELS[p.outcome] || p.outcome}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <span
                    className="rounded px-1.5 py-px text-[10px]"
                    style={{
                      color: C.green,
                      backgroundColor: "rgba(63,185,80,0.08)",
                    }}
                  >
                    +{(p.divergence * 100).toFixed(1)}%
                  </span>
                  <span className="aff-odd" style={{ fontWeight: 500 }}>
                    {fmtOdd(p.odd)}
                  </span>
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// "Cele mai bune cote pe casă" — one card per bookmaker, top 5 each.
function BestOddsSection({ byBookmaker }) {
  if (!byBookmaker) return null;
  const bookmakers = Object.keys(byBookmaker);
  return (
    <section>
      <div className="mb-4">
        <h2 className="text-lg" style={{ fontWeight: 500, color: C.text }}>
          Cele mai bune cote pe casă
        </h2>
        <p className="mt-1 text-sm" style={{ color: C.muted }}>
          Pentru fiecare casă, cele mai valoroase cote ale zilei — utile dacă ai
          cont pe un singur site.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {bookmakers.map((name) => (
          <BestOddsCard key={name} bookmaker={name} picks={byBookmaker[name]} />
        ))}
      </div>
    </section>
  );
}

// Chart/odds motif in a rounded square with a thin gold border — the brand mark.
function BrandIcon() {
  return (
    <span
      className="flex h-9 w-9 items-center justify-center rounded-lg"
      style={{
        border: `1px solid rgba(232,190,106,0.45)`,
        backgroundColor: "rgba(232,190,106,0.06)",
      }}
      aria-hidden="true"
    >
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        {/* three ascending bars = an odds/value motif */}
        <rect x="2" y="10" width="3.2" height="6" rx="1" fill={C.gold} />
        <rect x="7.4" y="6" width="3.2" height="10" rx="1" fill={C.gold} />
        <rect x="12.8" y="2.5" width="3.2" height="13.5" rx="1" fill={C.gold} />
      </svg>
    </span>
  );
}

// The gold wordmark: "ComparaCote" in gold, ".ro" in dimmer gold, weight 500
// with slightly tightened tracking.
function Wordmark() {
  return (
    <span
      className="text-2xl"
      style={{ fontWeight: 500, letterSpacing: "-0.02em" }}
    >
      <span style={{ color: C.gold }}>ComparaCote</span>
      <span style={{ color: C.goldDim }}>.ro</span>
    </span>
  );
}

// CSS-only spinner in gold.
function Spinner() {
  return (
    <div
      className="flex min-h-screen flex-col items-center justify-center gap-4"
      style={{ backgroundColor: C.bg }}
    >
      <div
        className="h-12 w-12 animate-spin rounded-full border-4"
        style={{ borderColor: C.border, borderTopColor: C.gold }}
      />
      <p style={{ color: C.muted }}>Se încarcă cotele… (rulează scraperele)</p>
    </div>
  );
}

// A single nav tab. Active = gold text with a gold underline; inactive = muted.
function NavTab({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className="nav-tab -mb-px border-b-2 px-1 pb-3 text-sm"
      style={{
        color: active ? C.gold : C.muted,
        borderColor: active ? C.gold : "transparent",
        fontWeight: active ? 500 : 400,
      }}
    >
      {children}
    </button>
  );
}

// Footer disclaimer — responsible gambling + affiliate transparency.
function Footer() {
  return (
    <footer
      className="mt-12 px-6 py-6"
      style={{ borderTop: `1px solid ${C.border}` }}
    >
      <p
        className="mx-auto max-w-5xl text-center text-[12px] leading-relaxed"
        style={{ color: C.muted }}
      >
        ComparaCote.ro compară cote afișate de operatori licențiați ONJN. Cotele
        se modifică în timp real — verifică valoarea finală pe site-ul casei de
        pariuri. Pariurile implică risc. 18+ | Joacă responsabil. Conținut cu
        linkuri de afiliere.
      </p>
    </footer>
  );
}

export default function App() {
  const [data, setData] = useState(null); // { count, main, obscure, best_odds_per_bookmaker }
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("main"); // "main" | "obscure" | "best"
  const [fetchedAt, setFetchedAt] = useState(null); // client fetch time (ms)
  const [now, setNow] = useState(Date.now()); // ticks so "acum X minute" updates

  // Fetch once when the component first mounts.
  useEffect(() => {
    fetch(API_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((payload) => {
        setData(payload);
        setFetchedAt(Date.now());
      })
      .catch((err) => setError(err.message));
  }, []);

  // Re-render every 30s so the "Actualizat acum X minute" indicator stays live.
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  if (error) {
    return (
      <div
        className="flex min-h-screen items-center justify-center px-6"
        style={{ backgroundColor: C.bg }}
      >
        <p style={{ color: C.red }}>Eroare la încărcarea cotelor: {error}</p>
      </div>
    );
  }

  if (!data) {
    return <Spinner />;
  }

  const tabs = [
    { key: "main", label: "Ligi principale", count: data.main.length },
    { key: "obscure", label: "Restul ligilor", count: data.obscure.length },
    { key: "best", label: "Cele mai bune cote" },
  ];

  // Prefer the server's scrape-completion time (generated_at, ISO 8601 UTC) so
  // the indicator reflects how old the DATA is, not when this browser fetched
  // it. Fall back to the client fetch time if an older backend omits the field.
  const generatedMs = data.generated_at ? Date.parse(data.generated_at) : NaN;
  const baseMs = Number.isFinite(generatedMs) ? generatedMs : fetchedAt;
  const minutesAgo =
    baseMs === null ? 0 : Math.max(0, Math.floor((now - baseMs) / 60000));

  return (
    <div className="min-h-screen" style={{ backgroundColor: C.bg }}>
      <header style={{ borderBottom: `1px solid ${C.border}` }}>
        <div className="mx-auto max-w-5xl px-6 pt-4">
          {/* Top line: today's date (left) and the 18+ badge (right). */}
          <div className="flex items-center justify-between">
            <span
              className="text-[11px] uppercase tracking-wide"
              style={{ color: C.muted }}
            >
              {romanianDate()}
            </span>
            <span
              className="rounded px-1.5 py-0.5 text-[11px]"
              style={{ backgroundColor: C.gold, color: C.bg, fontWeight: 500 }}
            >
              18+
            </span>
          </div>

          {/* Brand row: icon + wordmark + short tagline. */}
          <div className="mt-3 flex items-center gap-3">
            <BrandIcon />
            <Wordmark />
            <span
              className="ml-1 hidden text-sm sm:inline"
              style={{ color: C.muted }}
            >
              Compară cote · găsește valoarea
            </span>
          </div>

          {/* Nav tabs — active tab underlined in gold. */}
          <nav
            className="mt-4 flex gap-6"
            style={{ borderBottom: `1px solid ${C.border}` }}
          >
            {tabs.map((t) => (
              <NavTab
                key={t.key}
                active={tab === t.key}
                onClick={() => setTab(t.key)}
              >
                {t.label}
                {t.count !== undefined && (
                  <span style={{ color: C.muted }}> ({t.count})</span>
                )}
              </NavTab>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-6">
        {/* "Actualizat acum X minute" — based on when the browser fetched the
            data (the API doesn't expose a scrape timestamp). */}
        <div className="mb-4 flex items-center gap-2">
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: C.green }}
          />
          <span className="text-[12px]" style={{ color: C.muted }}>
            {updatedLabel(minutesAgo)}
          </span>
        </div>

        {tab === "best" ? (
          <BestOddsSection byBookmaker={data.best_odds_per_bookmaker} />
        ) : (
          <MatchesTable matches={tab === "main" ? data.main : data.obscure} />
        )}
      </main>

      <Footer />
    </div>
  );
}
