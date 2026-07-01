"""
check_overlap.py — quick sanity check: how many matches do Superbet and Betano
have in common right now?

For the odds comparator to work we need the SAME match on both sites so we can
compare their odds. This throwaway script runs both scrapers and reports the
overlap, so we know there's enough common ground to compare before we build the
real analysis step.

Run it from the backend/ folder:
    cd backend && py check_overlap.py

Why fuzzy matching?
Each site writes team names a bit differently ("Shamrock Rovers" vs "Shamrock
Rovers FC", with/without diacritics, etc.), so the full "A vs B" strings almost
never match exactly. Instead we say two matches are "the same" if a team name
from the Superbet match also shows up inside the Betano match name.
"""

import asyncio
import unicodedata

# These imports work when you run the script from the backend/ folder, because
# "scrapers" is then a package right next to this file.
from scrapers.superbet import scrape_superbet
from scrapers.betano import scrape_betano


def _normalize(text):
    """Lower-case and strip Romanian diacritics so 'Țară' == 'tara'.

    unicodedata.normalize('NFKD', ...) splits accented letters into a base letter
    + a combining accent; we then drop the accents. This makes team-name matching
    far more forgiving across the two sites.
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _team_names(match_name):
    """Split a 'Home vs Away' match string into its two normalized team names."""
    parts = match_name.split(" vs ")
    return [_normalize(p) for p in parts]


# Ignore very short tokens (len < 3) so noise like "fc"/"sc"/"sv" can't match.
MIN_WORD_LEN = 3

# Generic words shared by tons of unrelated clubs. If we let these count as a
# match, "Magic United vs Brisbane City" looks like "Derry City vs Drogheda
# United" (both share "city" + "united"). So we drop them and require teams to
# agree on a DISTINCTIVE word (the actual place/club name). Short structural
# tokens like "fc"/"sc"/"sv" are already excluded by MIN_WORD_LEN.
GENERIC_WORDS = {
    "afc", "ifk", "city", "united", "town", "county", "club", "real",
    "iii", "u19", "u20", "u21", "u23",
}


def _significant_words(team):
    """Distinctive words of a normalized team name (long enough, not generic)."""
    return [w for w in team.split()
            if len(w) >= MIN_WORD_LEN and w not in GENERIC_WORDS]


def _teams_match(a, b):
    """Do these two (already normalized) team names refer to the same team?

    The two sites name teams a bit differently ("Djurgarden" vs "Djurgardens",
    "Mattersburger" vs "Mattersburg", with/without an "FC"/"SC" prefix). So we
    compare WORD by word: it's a match if any distinctive word of one team is
    equal to, or contained in, a word of the other. Comparing words (not whole
    strings) avoids matching a short name buried inside an unrelated word.
    """
    for wa in _significant_words(a):
        for wb in _significant_words(b):
            if wa == wb or wa in wb or wb in wa:
                return True
    return False


def _same_fixture(sb_name, bt_name):
    """True if a Superbet match and a Betano match are the same fixture.

    We require BOTH teams to line up — home-with-home & away-with-away, or the
    teams swapped (sites don't always agree on which side is 'home'). Requiring
    both teams (not just one) is what 'same match' really means, and it stops
    false hits where a single team name coincidentally matches.
    """
    sb_home, sb_away = _team_names(sb_name)
    bt_home, bt_away = _team_names(bt_name)
    straight = _teams_match(sb_home, bt_home) and _teams_match(sb_away, bt_away)
    swapped = _teams_match(sb_home, bt_away) and _teams_match(sb_away, bt_home)
    return straight or swapped


def find_overlap(superbet_matches, betano_matches):
    """Return a list of (superbet_name, betano_name) pairs that are the same
    fixture on both sites."""
    pairs = []
    for sb in superbet_matches:
        sb_name = sb["match"]
        for bt in betano_matches:
            if _same_fixture(sb_name, bt["match"]):
                pairs.append((sb_name, bt["match"]))
                break   # one Betano match is enough; move to the next Superbet one
    return pairs


async def main():
    # Run the scrapers one after another (not at the same time) to keep things
    # simple and avoid two browsers fighting for resources.
    print("Scraping Superbet...")
    superbet_matches = await scrape_superbet()
    print("Scraping Betano...")
    betano_matches = await scrape_betano()

    print(f"\nSuperbet: {len(superbet_matches)} matches")
    print(f"Betano:   {len(betano_matches)} matches")

    overlap = find_overlap(superbet_matches, betano_matches)

    print(f"\nOverlapping matches: {len(overlap)}")
    for sb_name, bt_name in overlap:
        print(f"  - Superbet: {sb_name}")
        print(f"    Betano:   {bt_name}")


if __name__ == "__main__":
    asyncio.run(main())
