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
import urllib.request

BASE = "https://za.national-lottery.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
CACHE = "archive_cache"

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


def fetch(slug, year):
    os.makedirs(CACHE, exist_ok=True)
    path = f"{CACHE}/{slug}-{year}.html"
    if os.path.exists(path):
        return open(path, errors="replace").read()
    req = urllib.request.Request(
        f"{BASE}/{slug}/results/{year}-archive", headers={"User-Agent": UA}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    open(path, "w").write(html)
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
        if main:
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
    archive = {}
    for slug, (game, plus) in SLUGS.items():
        rows = {}
        for y in years:
            rows.update(parse_page(fetch(slug, y), slug))
        archive[f"{game}:{plus}"] = rows
        print(f"  {slug:15} {len(rows):4} draws")
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
        html = open(path, errors="replace").read()
    else:
        url = f"{BASE}/{slug}/results/{int(d):02d}-{month}-{y}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
        os.makedirs(CACHE, exist_ok=True)
        open(path, "w").write(html)
        time.sleep(1)

    out = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [
            re.sub(r"<[^>]*>", "", c).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
        ]
        cells = [c for c in cells if c]
        if len(cells) >= 3 and cells[0].isdigit() and cells[2].startswith("R"):
            out[cells[1]] = float(cells[2][1:].replace(",", ""))
    return out


if __name__ == "__main__":
    print("Backfilling archive results...")
    data = build()
    json.dump(data, open("archive_results.json", "w"), indent=1, sort_keys=True)
    print(f"\nwrote archive_results.json ({sum(len(v) for v in data.values())} draws)")
