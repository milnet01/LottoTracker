#!/usr/bin/env python3
"""Fetch SA National Lottery draw results from the official site's own JSON API.

Discovered 2026-08-01 by reading the JS bundle of www.nationallottery.co.za,
which Sizekhaya rebuilt as a single-page app after taking over the licence on
2026-06-01. The endpoints below are the ones the site's own results page calls.
They need no login and no API key. Money values are in cents.
"""

import json
import urllib.request

API = "https://www.nationallottery.co.za/api"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/128.0",
    "Origin": "https://www.nationallottery.co.za",
    "Referer": "https://www.nationallottery.co.za/",
}

# From the site's own gameId enum.
GAMES = {"lotto": 11101, "powerball": 11201, "daily": 11001}


def _post(path, body):
    req = urllib.request.Request(
        API + path, json.dumps(body).encode(), HEADERS, method="POST"
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        payload = json.load(r)
    if payload.get("code") != 0:
        raise RuntimeError(f"{path}: {payload.get('msg', payload)}")
    return payload["data"]


def draws(game, count=10):
    """Recent draws for a game. One record per pool (e.g. LOTTO, LOTTO PLUS 1)."""
    return _post(
        "/engine/draw/issueWinPoolInfoPageQuery",
        {"gameId": GAMES[game], "pageNum": 1, "pageSize": count},
    )["list"]


_divisions_cache = {}


def divisions(game, issue, win_pool_id=100, plus_flag=0):
    """Prize breakdown for one draw: which division paid what, to how many.

    Memoised: scoring asks for the same draw once per winning line, and a
    ticket running 10 draws across 7 Multiplay lines would otherwise issue
    70 identical POSTs to a free public endpoint.
    """
    key = (game, issue, win_pool_id, plus_flag)
    if key not in _divisions_cache:
        _divisions_cache[key] = _post(
            "/engine/draw/getIssueDrawResultDetail",
            {
                "gameId": GAMES[game],
                "wagerIssue": issue,
                "winPoolId": win_pool_id,
                "plusFlag": plus_flag,
            },
        )["winNotice"]["winLevels"]
    return _divisions_cache[key]


if __name__ == "__main__":
    for game in GAMES:
        print(f"\n--- {game.upper()} ---")
        for d in draws(game, 3):
            print(
                f"  {d['winPoolName']:16} draw {d['wagerIssue']}"
                f"  {d['drawTime'][:10]}  {' '.join(d['winNumList'])}"
            )
