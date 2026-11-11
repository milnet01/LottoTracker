#!/usr/bin/env python3
"""LOTTO-0001 INV-3: the two results sources agree wherever they overlap.

Set-based on purpose. The archive sorts numbers ascending; the API preserves
drawn order. Comparing them as lists reports every single draw as a conflict.
"""

import contextlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import backfill  # noqa: E402
from backfill import parse_page  # noqa: E402
from history import ARCHIVE, POOL_NAMES, in_feed_era  # noqa: E402
from results import draws  # noqa: E402

# Pools the feed never carried from the handover on, so zero OVERLAP is the
# expected state and not the rot signal the floor below is looking for. The
# archive alone holds their draws (ADR-0014), and main() fails if it holds none.
EXPECTED_EMPTY = {("daily", 1)}


def parse_page_reads_months():
    """LOTTO-0001 §6: a month the scraper cannot read drops ONE row, loudly.

    It raised KeyError on an abbreviated month and lost the whole page
    (LOTTO-0007 (b)). Pure - no archive, no network - so it runs first.
    """
    row = ('<tr><a href="/lotto/results/{d}-{m}-2026">x</a>'
           '<ul class="balls"><li class="ball">1</li><li class="ball">2</li>'
           '<li class="ball">3</li><li class="ball">4</li>'
           '<li class="ball">5</li><li class="ball">6</li>'
           '<li class="ball bonus-ball">7</li></ul></tr>')
    html = "".join(row.format(d=d, m=m) for d, m in (
        (2, "september"), (5, "sep"), (9, "sept"), (12, "ma"), (16, "foo")))
    got = sorted(parse_page(html, "lotto"))
    want = ["2026-09-02", "2026-09-05", "2026-09-09"]
    if got != want:
        print(f"  MONTHS: parsed {got}, expected {want}")
        return False
    return True


def build_asks_only_for_years_a_game_ran():
    """LOTTO-0085: a closed game's other years are 404s, and build() refuses on one.

    Pure, like the case above: fetch() is replaced, so nothing touches the site.
    """
    asked = []
    real_fetch, backfill.fetch = backfill.fetch, lambda slug, y: asked.append((slug, y)) or ""
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            backfill.build(range(2022, 2028))
    finally:
        backfill.fetch = real_fetch
    got = sorted(y for slug, y in asked if slug == "daily-lotto-plus")
    full = sorted(y for slug, y in asked if slug == "daily-lotto")
    if got != [2025, 2026] or full != list(range(2022, 2028)):
        print(f"  YEARS: daily-lotto-plus asked {got}, daily-lotto asked {full}")
        return False
    return True


def feed_before_handover_is_ignored():
    """LOTTO-0098: a feed record dated before the handover never replaces the archive.

    Seen 2026-11-11: the feed began listing Daily Lotto and Daily Lotto Plus
    draws for 2026-02 to 2026-05, each dated a day early against its own draw
    number, and all_draws() let them overwrite the archive's correct draws.
    Pure: the feed and the archive are both stand-ins, so nothing is fetched.
    """
    import tempfile

    import history

    early, late = "2026-02-17", "2026-06-02"
    archive = {"daily:0": {early: {"main": [3, 17, 24, 26, 31], "special": None},
                           late: {"main": [5, 6, 7, 8, 9], "special": None}}}
    feed = [  # `early` is a misdated pre-handover row; `late` is after it
        {"winPoolName": "Daily Lotto", "drawTime": f"{early}T20:00:00Z",
         "winNumList": ["1", "9", "15", "16", "21"], "wagerIssue": "2531"},
        {"winPoolName": "DAILY LOTTO", "drawTime": f"{late}T19:00:00Z",
         "winNumList": ["5", "6", "7", "8", "9"], "wagerIssue": "2637"},
    ]

    def fake_feed(_game, _count=10):
        return feed

    saved = (history.ARCHIVE, history.api_draws, dict(history._cache))
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "archive.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(archive, fh)
        history.ARCHIVE = path
        history.api_draws = fake_feed
        history._cache.clear()
        try:
            got = {d["date"]: d for d in history.all_draws("daily", 0)}
        finally:
            history.ARCHIVE, history.api_draws = saved[0], saved[1]
            history._cache.clear()
            history._cache.update(saved[2])
    ok = True
    if got.get(early, {}).get("source") != "archive":
        print(f"  HANDOVER: {early} came from {got.get(early, {}).get('source')!r}"
              " - a pre-handover feed record replaced the archive")
        ok = False
    if got.get(late, {}).get("source") != "api":
        print(f"  HANDOVER: {late} came from {got.get(late, {}).get('source')!r}"
              " - the feed is no longer used after the handover")
        ok = False
    return ok


def main():
    if not parse_page_reads_months():
        return 1
    if not build_asks_only_for_years_a_game_ran():
        return 1
    if not feed_before_handover_is_ignored():
        return 1
    if not os.path.exists(ARCHIVE):
        sys.exit(f"{ARCHIVE} missing - run `python3 backfill.py` first")
    archive = json.load(open(ARCHIVE))

    overlap = agree = 0
    starved, stale, unexpected = [], [], []
    # ONE fetch per GAME. draws() is not memoised (results.divisions is), and
    # POOL_NAMES has three lotto pools and two each for powerball and daily -
    # so the per-pool loop issued seven identical-per-game POSTs to a free
    # third-party endpoint for three distinct queries, and gave a transport
    # failure seven chances to abort the run instead of three.
    by_game = {}
    for (game, plus), pool in POOL_NAMES.items():
        before = overlap
        rows = archive.get(f"{game}:{plus}", {})
        if game not in by_game:
            # Only what history.all_draws() reads: before the handover the
            # archive owns the draw, and the feed's early rows are misdated
            # (LOTTO-0098), so comparing them reports the feed's error.
            by_game[game] = [r for r in draws(game, 400) if in_feed_era(r)]
        for r in by_game[game]:
            if r["winPoolName"].upper() != pool.upper():
                continue
            date = r["drawTime"][:10]
            if date not in rows:
                continue
            # Guarded the way history.all_draws() guards the same field, and
            # for its reason: a draw the feed lists before it happens carries
            # no numbers, and int() raising here aborts the run with a
            # traceback rather than a DISAGREE line.
            raw_nums = r.get("winNumList") or []
            try:
                nums = [int(n) for n in raw_nums]
            except (TypeError, ValueError):
                print(f"  SKIPPED {game}:{plus} {date}: winNumList "
                      f"{raw_nums!r} is not a list of numbers")
                continue
            if not nums:
                continue
            special = nums[-1] if game in ("lotto", "powerball") else None
            main = nums[:-1] if special is not None else nums
            overlap += 1
            got = rows[date]
            if sorted(got["main"]) == sorted(main) and got["special"] == special:
                agree += 1
            else:
                print(f"  DISAGREE {game}:{plus} {date} {got} vs {main}/{special}")

        if (game, plus) in EXPECTED_EMPTY:
            # The exemption is checked in BOTH directions. One-directional, an
            # entry here is never falsified: a pool silenced because it broke
            # stays silenced for good. This project forbids exactly that for
            # DRAW_DAYS and the same argument applies here.
            if overlap != before:
                unexpected.append(f"{game}:{plus} ({pool})")
            if not rows:
                starved.append(f"{game}:{plus} ({pool})")
            continue

        # A pool contributing nothing is the "game naming changed" breakage
        # this check exists to catch. Without a per-pool floor the run still
        # passes on the strength of the other five.
        if overlap == before:
            # Two causes, and they are not the same problem. The archive is
            # FROZEN until backfill.py is re-run by hand, while the API side is
            # the newest 400 records and slides forward with the calendar. Once
            # the window's oldest record passes the archive's newest draw the
            # two cannot overlap at all - so this gate eventually goes red as a
            # function of elapsed time since the last backfill, roughly a year
            # out, and "renamed pool" would name the wrong cause entirely.
            newest_archive = max(rows) if rows else None
            oldest_api = min(
                (r["drawTime"][:10] for r in by_game[game]
                 if r["winPoolName"].upper() == pool.upper()),
                default=None)
            if newest_archive and oldest_api and oldest_api > newest_archive:
                stale.append(f"{game}:{plus} (archive ends {newest_archive}, "
                             f"the API window starts {oldest_api})")
            else:
                starved.append(f"{game}:{plus} ({pool})")

    for s in stale:
        print(f"  NO OVERLAP {s} - the ARCHIVE IS STALE, not the pool: "
              f"re-run `python3 backfill.py`")
    for s in starved:
        print(f"  NO OVERLAP {s} - renamed pool, or archive missing this game")
    for s in unexpected:
        print(f"  UNEXPECTEDLY PRESENT {s} - EXPECTED_EMPTY says the feed "
              f"never carried this pool, and now it does: drop the exemption")

    print(f"{overlap} overlapping draws, {agree} agree, {overlap - agree} disagree")
    return (0 if overlap and agree == overlap
            and not starved and not stale and not unexpected else 1)


if __name__ == "__main__":
    sys.exit(main())
