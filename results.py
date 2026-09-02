#!/usr/bin/env python3
"""Fetch SA National Lottery draw results from the official site's own JSON API.

Discovered 2026-08-01 by reading the JS bundle of www.nationallottery.co.za,
which Sizekhaya rebuilt as a single-page app after taking over the licence on
2026-06-01. The endpoints below are the ones the site's own results page calls.
They need no login and no API key. Money values are in cents.
"""

import http.client
import json
import socket
import ssl
import time
import urllib.error
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


ATTEMPTS = 3    # >= 1; at 0 the loop body never runs and `payload` is unbound
BACKOFF = 1.0   # seconds; doubled per retry, so 1 s then 2 s

# Every HTTP attempt this module makes, for GET /status to read out
# (LOTTO-0019 §4.2, INV-28). Reset by serve.py::refresh() - SYNCHRONOUSLY,
# before the worker thread is started, not inside work(); §4.2 says why. Never
# by _post itself: a counter that reset itself would have no build to belong to.
requests_made = 0


def _post(path, body):
    """POST to the API, retrying a transport failure (LOTTO-0019 INV-27).

    Four of seven build attempts failed with SSL: UNEXPECTED_EOF_WHILE_READING
    when LOTTO-0002 was measured, and one failure aborted the whole run - this
    is the single funnel every caller reaches the network through, so bounding
    it here fixes check.py, the page's build and the fetching verifiers at once.
    """
    global requests_made
    req = urllib.request.Request(
        API + path, json.dumps(body).encode(), HEADERS, method="POST"
    )
    for attempt in range(ATTEMPTS):
        requests_made += 1
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                payload = json.load(r)
            break
        except urllib.error.HTTPError:
            # The server answered. A retry gets the same answer, and a 404
            # retried three times is 3 s of nothing. Caught BEFORE URLError,
            # which it subclasses, or the arm below would swallow it.
            raise
        except (urllib.error.URLError, ssl.SSLError, http.client.HTTPException,
                ConnectionError, json.JSONDecodeError,
                socket.timeout, TimeoutError):
            # socket.timeout explicitly: it is only an ALIAS of TimeoutError
            # from Python 3.10, and this project pins 3.8+. Without it the
            # retry silently skips the commonest slow-network case.
            #
            # The rest were added 2026-09-01 because the retry did not cover
            # the failure the docstring above names. urllib wraps a HANDSHAKE
            # error into URLError; nothing wraps one raised while the BODY is
            # read - and json.load(r) sits inside this try. So SSLEOFError,
            # IncompleteRead, a bare ConnectionResetError and a truncated
            # JSON body all escaped on attempt 1 and aborted the run, while
            # UNEXPECTED_EOF_WHILE_READING - the very error this loop was
            # built for, at four of seven measured build attempts - is an EOF,
            # at least as likely mid-transfer as mid-handshake.
            if attempt == ATTEMPTS - 1:
                raise          # the ORIGINAL error, unwrapped
            time.sleep(BACKOFF * 2**attempt)
    if not isinstance(payload, dict):
        # .get() on a list raises AttributeError, which is outside both the
        # retry arms above and every caller's expectations.
        raise RuntimeError(
            f"{path}: expected a JSON object, got {type(payload).__name__}"
        )
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


def divisions(game, issue, win_pool_id, plus_flag):
    """Prize breakdown for one draw: which division paid what, to how many.

    Every argument is required. The defaults were 100 and 0, which name the
    BASE pool - so a caller that forgot them priced a PLUS win off the base
    table and got a plausible wrong number rather than an error.

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
