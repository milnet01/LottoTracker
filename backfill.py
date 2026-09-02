#!/usr/bin/env python3
"""Backfill pre-June-2026 draw results from za.national-lottery.com.

The official Sizekhaya feed only starts 2026-06-01 (the licence handover), so
tickets bought before that cannot be checked against it. This scrapes an
archive that still carries the Ithuba era.

One page fetch per pool per year, cached to disk so a re-run costs nothing.
Prize amounts are NOT scraped here: per-draw payout pages are fetched later,
only for draws a ticket actually won, rather than for every draw.

Ball roles come from the CSS class, not position:
    class="... ball"        main number
    class="... bonus-ball"  Lotto bonus
    class="... powerball"   PowerBall
"""

import datetime
import json
import os
import re
import time
import urllib.error
import urllib.request

BASE = "https://za.national-lottery.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"

# Anchored to this file, never to the working directory: supervise.py was
# already working around the cwd-relative form per caller with cwd=HERE, and
# verify_privacy.py resolves from __file__, so the project held both patterns.
# history.py imports ARCHIVE from here rather than keeping a second copy - the
# scraper owns where it writes, and one path cannot drift from itself.
_HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(_HERE, "archive_cache")
ARCHIVE = os.path.join(_HERE, "archive_results.json")

# site slug -> (internal game key, plusFlag)
SLUGS = {
    "lotto": ("lotto", 0),
    "lotto-plus-1": ("lotto", 1),
    "lotto-plus-2": ("lotto", 2),
    "powerball": ("powerball", 0),
    "powerball-plus": ("powerball", 1),
    "daily-lotto": ("daily", 0),
}

MONTHS = {
    m: i
    for i, m in enumerate(
        "january february march april may june july august september "
        "october november december".split(),
        1,
    )
}

# (main ball count, whether a special ball is expected), per site slug family.
# parse_page() checks every row against this. Ball ROLES come from the CSS
# class, and that is a free third-party site's markup: one appended class turns
# `... pb ball dark powerball` into something endswith() no longer matches, the
# PowerBall is filed as a sixth main number, `special` becomes None, and the
# record is WELL-FORMED. It then flows through history.py untouched and scores
# every archive-era PowerBall line one match high while never matching the PB -
# exactly the failure INV-1 exists to prevent, arriving from the side INV-3's
# overlap check cannot reach, in the era where 69 of 86 wins live. A wrong
# record is worse than no record, so a mismatch is skipped and said out loud.
SHAPE = {
    "lotto": (6, True),
    "lotto-plus-1": (6, True),
    "lotto-plus-2": (6, True),
    "powerball": (5, True),
    "powerball-plus": (5, True),
    "daily-lotto": (5, False),
}


def _write_atomic(path, text):
    """Write via a temp file in the same directory, then rename.

    open(path, "w") truncates BEFORE the write, and every reader here treats
    any file at the cache path as authoritative for all time - there is no
    length, provenance or freshness check anywhere. So an interrupted write
    leaves a short page that is permanently indistinguishable from a good one:
    a truncated LISTING page yields fewer draws, which history.covered() then
    scores an entry over (INV-6 breached with no count going wrong), and a
    truncated PAYOUT page yields a partial table, which sends amount() down
    its plain-tier fallback and prices a win from the wrong division rather
    than raising under INV-22. The pid keeps two concurrent runs apart.
    """
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def fetch(slug, year):
    os.makedirs(CACHE, exist_ok=True)
    path = f"{CACHE}/{slug}-{year}.html"
    # A past year's listing is closed, so a cached copy is good for ever. The
    # CURRENT year's is still growing, and every reader here treats a cached
    # page as authoritative for all time - so caching it freezes the archive at
    # whatever day it was first fetched, with nothing saying so.
    if os.path.exists(path) and year < datetime.date.today().year:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    req = urllib.request.Request(
        f"{BASE}/{slug}/results/{year}-archive", headers={"User-Agent": UA}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    _write_atomic(path, html)
    time.sleep(1)  # be polite to a free source
    return html


def parse_page(html, slug=None):
    """-> {'YYYY-MM-DD': {'main': [...], 'special': int|None}}"""
    out = {}
    for row in html.split("<tr>")[1:]:
        # The link slug is not always the page slug: since the June 2026
        # rebrand, /lotto-plus-2/ rows link to /lotto-5-max/ and
        # /powerball-plus/ rows to /powerball-xtra/. Match any game slug.
        m = re.search(r'href="/[a-z0-9\-]+/results/(\d{1,2})-([a-z]+)-(\d{4})"', row)
        balls = re.search(r'<ul class="balls">(.*?)</ul>', row, re.S)
        if not (m and balls):
            continue
        date = f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
        main, special = [], None
        for cls, val in re.findall(
            r'<li class="([^"]*)">\s*(\d+)\s*</li>', balls.group(1)
        ):
            if cls.endswith("bonus-ball") or cls.endswith("powerball"):
                special = int(val)
            else:
                main.append(int(val))
        if not main:
            continue
        # SHAPE is keyed on the PAGE slug, which is why parse_page takes one.
        # The argument was accepted and never used, so nothing checked that a
        # row looked like the game it was filed under.
        want = SHAPE.get(slug)
        if want is not None:
            n_main, want_special = want
            if len(main) != n_main or (special is not None) != want_special:
                print(f"  SKIPPED {slug} {date}: {len(main)} main ball(s), "
                      f"special={special!r} - expected {n_main} and "
                      f"{'a' if want_special else 'no'} special. The site's"
                      " ball markup has changed; do not trust this page.")
                continue
        out[date] = {"main": main, "special": special}
    return out


# The archive is scraped from the year of the earliest purchase SMS to the
# current one. 2022 is not a limit of the site (it carries 2021 and earlier) -
# it is where this dump's tickets start. An older ticket arriving later reads
# as UNCHECKABLE rather than being scored against the wrong draws, because
# history.scorable() gates on the first date a source actually reaches, so the
# floor being too high fails safe. The top end is computed, not written down,
# or the last year silently stops being fetched each January.
FIRST_YEAR = 2022


def build(years=None):
    if years is None:
        years = range(FIRST_YEAR, datetime.date.today().year + 1)
    archive, failed = {}, []
    for slug, (game, plus) in SLUGS.items():
        rows = {}
        for y in years:
            try:
                rows.update(parse_page(fetch(slug, y), slug))
            except urllib.error.HTTPError as e:
                # Collected rather than raised on the spot, so one 404 does not
                # hide the state of the other five pools. NOT skipped either: a
                # missing middle year is a hole in the draw list, and covered()
                # takes the first N draws on or after a start date - so it
                # would score an entry straight across the gap, against real
                # draws that are the wrong ones (INV-6). Hence the refusal
                # below rather than a partial write.
                failed.append(f"{slug} {y}: HTTP {e.code}")
        archive[f"{game}:{plus}"] = rows
        print(f"  {slug:15} {len(rows):4} draws")
    if failed:
        raise RuntimeError(
            "archive incomplete, refusing to write: " + "; ".join(failed)
            + ". A missing year is a hole covered() would score straight "
            "across; the pages that did fetch are cached, so a re-run is cheap."
        )
    return archive


# Per-draw payout pages use the CURRENT game slug even for old draws, because
# the site renamed Lotto Plus 2 -> Lotto 5 Max and PowerBall Plus -> XTRA at
# the June 2026 rebrand and rewrote its archive links to match.
PAYOUT_SLUG = {
    ("lotto", 0): "lotto",
    ("lotto", 1): "lotto-plus-1",
    ("lotto", 2): "lotto-5-max",
    ("powerball", 0): "powerball",
    ("powerball", 1): "powerball-xtra",
    ("daily", 0): "daily-lotto",
}


def payouts(game, plus_flag, date):
    """{'3': 19.40, '2 + Bonus': 30.00, ...} in rands, for one archive draw."""
    y, m, d = date.split("-")
    slug = PAYOUT_SLUG[(game, plus_flag)]
    month = [k for k, v in MONTHS.items() if v == int(m)][0]
    path = f"{CACHE}/payout-{slug}-{date}.html"
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            html = fh.read()
    else:
        url = f"{BASE}/{slug}/results/{int(d):02d}-{month}-{y}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
        os.makedirs(CACHE, exist_ok=True)
        _write_atomic(path, html)
        time.sleep(1)

    out = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [
            re.sub(r"<[^>]*>", "", c).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
        ]
        cells = [c for c in cells if c]
        if len(cells) >= 3 and cells[0].isdigit() and cells[2].startswith("R"):
            try:
                out[cells[1]] = float(cells[2][1:].replace(",", ""))
            except ValueError:
                # "Rollover" passes startswith("R") too. A row whose amount
                # will not parse is not a division row, and letting float()
                # raise here aborts check.py entirely.
                continue
    return out


if __name__ == "__main__":
    print("Backfilling archive results...")
    data = build()
    # Atomic for _write_atomic()'s reason, with more force: this truncates the
    # ONLY copy, and a failure inside json.dump leaves unparseable JSON that
    # makes history.py raise on every subsequent run.
    _write_atomic(ARCHIVE, json.dumps(data, indent=1, sort_keys=True))
    print(f"\nwrote archive_results.json ({sum(len(v) for v in data.values())} draws)")
