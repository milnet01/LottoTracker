#!/usr/bin/env python3
"""Seventeen cases, one per invariant INV-12 to INV-21, INV-23 to INV-25 and
INV-27 to INV-30 — the local page, the tray that drives it, and (since
LOTTO-0019) the results transport underneath both.

Joins tools/verify_privacy.py, verify_sources.py, verify_coverage.py and
verify_pools.py. Exit code is the signal, as with the other four.

    python3 tools/verify_page.py            # all seventeen
    python3 tools/verify_page.py --list
    python3 tools/verify_page.py --break host_endswith   # RED-TEST: must FAIL

Three constraints, inherited from LOTTO-0002 §7 and binding on all thirteen:

  * No network. The seam is the BUILDER, not the model: make_server takes a
    callable, so POST /refresh has something to invoke.
  * No real data. Every case runs with BOTH $HOME and $XDG_CONFIG_HOME pointed
    at a fresh temporary directory, and tickets built from the VAS00000000000
    sentinel rather than lotto_sms_raw.txt. Both variables, because the config
    paths honour XDG_CONFIG_HOME first and KDE and GNOME both export it.
  * Recompute, don't import the judgement. INV-16 recomputes the compared spend
    from tickets.TIER_PRICES, never by calling serve.py's own tier_increments().

--break exists because this is greenfield: there is no pre-fix code to red-test
against, so the only way to know a case CAN fail is to break the rule it
guards and watch it. Each break is named in the invariant's *Test:* clause.
"""

import http.client
import json
import os
import re
import shutil
import site
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import page  # noqa: E402
import serve  # noqa: E402
import supervise  # noqa: E402

SENTINEL = "VAS00000000000"
# Fixture numbers for INV-48. The two sets are DISJOINT on purpose: a renderer
# that shows the chosen numbers in both columns passes every per-number
# assertion if they overlap, and this is the case that catches it.
CHOSEN_MAIN = [3, 11, 24, 38, 45]
DRAWN_MAIN = [6, 17, 29, 41, 50]
# Read at import, while $HOME is still the real one: temp_home() moves $HOME for
# every case, and on this machine PySide6 lives in the USER site-packages under
# it — so the tray probe would find no Qt at all and report the wrong reason.
USER_SITE = site.getusersitepackages()
BREAK = os.environ.get("LOTTO_BREAK") or ""


def broken(name):
    return BREAK == name


class Fail(Exception):
    pass


def need(cond, msg):
    if not cond:
        raise Fail(msg)


# --------------------------------------------------------------- fixtures


def temp_home():
    """A fresh $HOME and $XDG_CONFIG_HOME. Both, never just $HOME."""
    d = tempfile.mkdtemp(prefix="lotto-verify-")
    os.environ["HOME"] = d
    os.environ["XDG_CONFIG_HOME"] = os.path.join(d, ".config")
    return d


def fixture_model(**over):
    """A model in the §4.1 shape. No real ticket ever reaches this file."""
    m = {
        "wins": [
            {
                "ref": SENTINEL,
                "game": "lotto",
                "plus_flag": 0,
                "pool_id": 100,
                "date": "2026-07-01",
                "division": "Division 7",
                "matched": "MATCH 3",
                "amount_cents": 5000,
                "expires": "2027-07-01",
                "expires_in_days": 333,
                "expired": False,
                "source": "api",
            }
        ],
        "entries": [
            {
                "ref": SENTINEL,
                "game": "lotto",
                "plus_flag": 0,
                "pool_id": 100,
                "cost_cents": 500,
                "scorable": True,
                "reason": None,
                "won_cents": 5000,
                "draws_covered": 1,
                "draws_remaining": 0,
            }
        ],
        "tickets": [
            {
                "ref": SENTINEL,
                "game": "lotto",
                "cost_cents": 500,
                "boards": 1,
                "ndraws": 1,
                "resolved": True,
                "bought": "2026-07-01",
            }
        ],
        "uncheckable": {
            "entries": 1,
            "uncheckable": 0,
            "too_old": 0,
            "no_pool": 0,
            "wholly": 0,
            "partly": 0,
        },
        "spend": {
            "compared_cents": 500,
            "lifetime_cents": 500,
            "unresolved_cents": 0,
            "unresolved_tickets": 0,
        },
        "won": {
            "compared_cents": 5000,
            "lifetime_cents": 5000,
            "unexpired_cents": 5000,
        },
        # LOTTO-0036. Present so the period control is IN the bytes
        # nothing_in_the_url scans; without it that case covers a control it
        # never renders, which is empty cover (LOTTO-0036 §10).
        "periods": {
            "buckets": [
                {"key": "2026", "kind": "year", "label": "2026",
                 "spend_cents": 500, "won_cents": 5000},
                {"key": "2026-07", "kind": "month", "label": "July 2026",
                 "spend_cents": 500, "won_cents": 5000},
            ],
            "no_result_cents": 0,
        },
        "settings": {"autostart": False, "open_on_start": True},
        "built": "2026-08-02T12:00:00",
        "stale": False,
        "error": None,
        "building": False,
    }
    m.update(over)
    return m


class Stub:
    """A builder stub. Records whether the memos were empty WHEN IT WAS CALLED —
    which is the only moment that can distinguish clear-before from clear-after."""

    def __init__(self, model=None, raises=False):
        self.model = model if model is not None else fixture_model()
        self.raises = raises
        self.calls = 0
        self.memos_empty_at_call = None

    def __call__(self):
        import check
        import history
        import results

        self.calls += 1
        self.memos_empty_at_call = not (
            history._cache or results._divisions_cache or check._struct
        )
        if self.raises:
            raise RuntimeError("stub builder failure")
        return self.model


def serve_on(builder, token="tok"):
    """A real server on an ephemeral port. Returns (server, state, port, thread)."""
    import threading

    port = supervise.free_port()
    srv, state = serve.make_server(builder, token, port)
    if broken("host_endswith"):
        # RED-TEST for INV-12: the weaker comparison §4.2's table pairs with
        # evil.example.127.0.0.1:<port>.
        allow = f"127.0.0.1:{port}"
        srv.RequestHandlerClass._host_ok = lambda self: (
            (self.headers.get("Host") or "").lower().endswith(allow)
        )
    if broken("no_security_headers"):
        serve.SECURITY_HEADERS = ()
    if broken("token_exempt_refresh"):
        # RED-TEST for INV-13: the likeliest breach — exempt the one route the
        # tray uses, leaving /settings guarded.
        real = srv.RequestHandlerClass._token_ok
        srv.RequestHandlerClass._token_ok = lambda self: (
            True if self.path.split("?")[0] == "/refresh" else real(self)
        )
    if broken("reflect_path"):
        # RED-TEST for INV-14: reflect self.path RAW. No X-Injected header
        # results, which is why the case asserts the whole header name set.
        real_send = srv.RequestHandlerClass._send

        def leaky(self, code, body=b"", ctype=None):
            self.send_response(code)
            self.send_header("X-Echo-Path", self.path)
            if ctype:
                self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in serve.SECURITY_HEADERS:
                self.send_header(k, v)
            self.end_headers()
            if body:
                self.wfile.write(body)

        srv.RequestHandlerClass._send = leaky
        del real_send
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, state, port, t


def req(port, method, path, host=None, headers=None, body=None, skip_host=False):
    """One request. skip_host is the only way to send NO Host header — urllib
    supplies one automatically, so a case written the obvious way tests nothing."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5) \
        if not skip_host else _no_host_conn(port)
    hdrs = dict(headers or {})
    if host is not None and not skip_host:
        hdrs["Host"] = host
    payload = json.dumps(body).encode() if body is not None else None
    if payload is not None:
        hdrs.setdefault("Content-Type", "application/json")
    if skip_host:
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in hdrs.items():
            conn.putheader(k, v)
        conn.putheader("Content-Length", str(len(payload or b"")))
        conn.endheaders()
        if payload:
            conn.send(payload)
    else:
        if method == "POST":
            hdrs.setdefault("Content-Length", str(len(payload or b"")))
        conn.request(method, path, body=payload, headers=hdrs)
    r = conn.getresponse()
    data = r.read()
    out = (r.status, dict(r.getheaders()), data)
    conn.close()
    return out


def _no_host_conn(port):
    return http.client.HTTPConnection("127.0.0.1", port, timeout=5)


# ------------------------------------------------------------------ the cases


def host_allowlist():
    """INV-12 — a Host outside the allowlist gets 421 and no body; every
    response carries the anti-framing headers and never a CORS header."""
    temp_home()
    stub = Stub()
    srv, state, port, _t = serve_on(stub)
    try:
        good = [f"127.0.0.1:{port}", f"localhost:{port}", f"LOCALHOST:{port}"]
        poison = [
            f"evil.example:{port}",            # port-only check
            f"127.0.0.1.evil.example:{port}",  # startswith
            f"evil.example.127.0.0.1:{port}",  # endswith
        ]
        routes = [("GET", "/"), ("GET", "/status"),
                  ("POST", "/refresh"), ("POST", "/settings")]
        for method, path in routes:
            for h in poison:
                st, hdrs, body = req(port, method, path, host=h,
                                      headers={"X-Lotto-Token": "tok"},
                                      body={} if method == "POST" else None)
                need(st == 421, f"{method} {path} Host={h}: expected 421, got {st}")
                need(body == b"", f"{method} {path} Host={h}: 421 must have no body")
                check_headers(hdrs, f"{method} {path} Host={h}")
            # No Host header at all.
            st, hdrs, _ = req(port, method, path, skip_host=True,
                               headers={"X-Lotto-Token": "tok"},
                               body={} if method == "POST" else None)
            need(st == 421, f"{method} {path} with no Host: expected 421, got {st}")
            check_headers(hdrs, f"{method} {path} no Host")
        # The positive control, per route — a blanket 200 is unsatisfiable.
        state.wait_idle(5)
        for h in good:
            st, hdrs, _ = req(port, "GET", "/", host=h)
            need(st == 200, f"GET / Host={h}: expected 200, got {st}")
            check_headers(hdrs, f"GET / Host={h}")
            st, _, _ = req(port, "GET", "/status", host=h)
            need(st == 200, f"GET /status Host={h}: expected 200, got {st}")
        st, _, _ = req(port, "POST", "/settings", host=good[0],
                        headers={"X-Lotto-Token": "tok"}, body={"autostart": False})
        need(st == 200, f"tokened POST /settings: expected 200, got {st}")
        state.wait_idle(5)
        st, _, _ = req(port, "POST", "/refresh", host=good[0],
                        headers={"X-Lotto-Token": "tok"})
        need(st == 202, f"tokened POST /refresh: expected 202, got {st}")
    finally:
        srv.shutdown()


def check_headers(hdrs, where):
    low = {k.lower(): v for k, v in hdrs.items()}
    need(low.get("x-frame-options") == "DENY", f"{where}: X-Frame-Options missing")
    need(
        low.get("content-security-policy") == "frame-ancestors 'none'",
        f"{where}: frame-ancestors missing",
    )
    need(low.get("cache-control") == "no-store", f"{where}: no-store missing")
    for k in low:
        need(
            not k.startswith("access-control-allow"),
            f"{where}: CORS header {k} present",
        )


def token_required():
    """INV-13 — a POST without the run's exact token is 403 and changes nothing."""
    home = temp_home()
    stub = Stub()
    srv, state, port, _t = serve_on(stub, token="realtoken-abcdefghij")
    host = f"127.0.0.1:{port}"
    ap = serve.autostart_path()
    try:
        state.wait_idle(5)
        # A proper PREFIX of the real token, so a startswith implementation is
        # actually caught; a random wrong token passes one.
        wrong = "realtoken-abcde"
        rejects = [
            ({}, "no token"),
            ({"X-Lotto-Token": wrong}, "prefix token"),
            (
                {"X-Lotto-Token": "realtoken-abcdefghij",
                 "Origin": "http://evil.example"},
                "wrong Origin with right token",
            ),
        ]
        # Every rejected POST runs BEFORE any accepted one, from a config dir
        # where the file does not exist: "still absent" is only an assertion in
        # that order.
        for hdrs, label in rejects:
            for path in ("/settings", "/refresh"):
                before = stub.calls
                st, _, _ = req(port, "POST", path, host=host, headers=hdrs,
                                body={"autostart": True} if path == "/settings" else None)
                need(st == 403, f"{path} ({label}): expected 403, got {st}")
                need(not os.path.exists(ap), f"{path} ({label}): wrote the autostart file")
                need(stub.calls == before, f"{path} ({label}): started a rebuild")
        accepts = [
            ({"X-Lotto-Token": "realtoken-abcdefghij"}, "right token, no Origin"),
            (
                {"X-Lotto-Token": "realtoken-abcdefghij", "Origin": f"http://127.0.0.1:{port}"},
                "right token, good Origin",
            ),
        ]
        for hdrs, label in accepts:
            st, _, _ = req(port, "POST", "/settings", host=host, headers=hdrs,
                            body={"autostart": True})
            need(st == 200, f"/settings ({label}): expected 200, got {st}")
            need(os.path.exists(ap), f"/settings ({label}): did not write the file")
            state.wait_idle(5)
            st, _, _ = req(port, "POST", "/refresh", host=host, headers=hdrs)
            need(st == 202, f"/refresh ({label}): expected 202, got {st}")
            state.wait_idle(5)
        # The rendered page must carry the token, or every toggle 403s while
        # every other case still passes.
        _st, _h, body = req(port, "GET", "/", host=host)
        need(b"realtoken-abcdefghij" in body, "the rendered page does not carry the token")
    finally:
        srv.shutdown()
        shutil.rmtree(home, ignore_errors=True)

    # The channel the tray depends on: a child spawned with LOTTO_TOKEN in its
    # environment accepts that token. LOTTO_NO_BUILD keeps it off the network.
    child_port = supervise.free_port()
    env = {**os.environ, "LOTTO_TOKEN": "childtoken-0123456789",
           "LOTTO_PORT": str(child_port), "LOTTO_NO_BUILD": "1"}
    child = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py")],
                             cwd=ROOT, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{child_port}/status", timeout=1)
                break
            except (urllib.error.URLError, OSError):
                time.sleep(0.1)
        else:
            raise Fail("the LOTTO_TOKEN child never came up")
        st, _, _ = req(child_port, "POST", "/refresh", host=f"127.0.0.1:{child_port}",
                        headers={"X-Lotto-Token": "childtoken-0123456789"})
        need(st == 202, f"child did not accept its LOTTO_TOKEN: got {st}")
    finally:
        child.terminate()
        child.wait(timeout=5)


EXPECTED_HEADERS = {
    "server", "date", "content-length", "x-frame-options",
    "content-security-policy", "cache-control",
}


def no_reflected_headers():
    """INV-14 — no request-derived string reaches a header or a written file."""
    home = temp_home()
    stub = Stub()
    srv, state, port, _t = serve_on(stub)
    host = f"127.0.0.1:{port}"
    ap = serve.autostart_path()
    try:
        state.wait_idle(5)
        # First write the file, so there is something to assert about: a
        # poisoned path is not /settings, it 404s, and nothing is written.
        st, _, _ = req(port, "POST", "/settings", host=host,
                        headers={"X-Lotto-Token": "tok"}, body={"autostart": True})
        need(st == 200, f"setup POST /settings: got {st}")
        need(os.path.exists(ap), "setup did not write the autostart file")
        before = open(ap, "rb").read()

        # PERCENT-ENCODED, not raw. Raw CRLF truncates the request line, the
        # handler sees "/a", and the case passes against a server with no
        # header hygiene at all — measured.
        poison = "/a%0d%0aX-Injected:+yes"
        for method, path in [("GET", poison), ("GET", "/status" + "%0d%0aX-I:+y"),
                             ("POST", poison)]:
            st, hdrs, _ = req(port, method, path, host=host,
                               headers={"X-Lotto-Token": "tok"},
                               body={} if method == "POST" else None)
            names = {k.lower() for k in hdrs}
            need(
                "x-injected" not in names,
                f"{method} {path}: an X-Injected header appeared",
            )
            extra = names - EXPECTED_HEADERS - {"content-type", "allow"}
            need(not extra, f"{method} {path}: unexpected header(s) {sorted(extra)}")
            for k, v in hdrs.items():
                need(
                    poison not in v and "X-Injected" not in v,
                    f"{method} {path}: header {k} echoes the request path",
                )
        need(open(ap, "rb").read() == before, "the autostart file changed")

        # Assert the CONTENT outright, not merely that it did not change:
        # byte-equality passes a file that has been wrong since it was written,
        # which is exactly the __file__ trap. The Exec line must name tray.py.
        text = before.decode()
        need("/tray.py" in text, "the .desktop Exec does not name tray.py")
        need("serve.py" not in text, "the .desktop Exec names serve.py")
        need(sys.executable in text, "the .desktop Exec does not use sys.executable")
        for line in ("[Desktop Entry]", "Type=Application", "Name=Lotto Tracker",
                     "Terminal=false", "Categories=Utility;",
                     "X-GNOME-Autostart-enabled=true"):
            need(line in text, f"the .desktop file is missing {line!r}")

        # Body validation is what keeps "only two validated booleans are ever
        # written" true.
        for bad in ({"autostart": "yes"}, {"nonsense": True}, [1, 2, 3]):
            st, _, _ = req(port, "POST", "/settings", host=host,
                            headers={"X-Lotto-Token": "tok"}, body=bad)
            need(st == 400, f"body {bad!r}: expected 400, got {st}")
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/settings", body=b"{}",
                     headers={"Host": host, "X-Lotto-Token": "tok",
                              "Content-Length": str(serve.MAX_BODY + 1)})
        need(conn.getresponse().status == 413, "an over-long body was not 413")
        conn.close()
        st, _, _ = req(port, "POST", "/settings", host=host,
                        headers={"X-Lotto-Token": "tok"}, body={})
        need(st == 200, "an empty object should be a valid no-op")
    finally:
        srv.shutdown()
        shutil.rmtree(home, ignore_errors=True)


def uncheckable_not_a_loss():
    """INV-15 — an entry nothing can score never renders as a loss."""
    temp_home()
    forbidden = {"", "-", "–", "—", "0", "0.00", "R0.00",
                 "R0", "0,00", "R 0.00", "n/a", "N/A"}
    partly_reason = "no results source carries this pool"
    wholly_reason = "predates all draw data for this pool (earliest 2025-01-01)"
    model = fixture_model(
        entries=[
            # partly uncheckable: one pool scorable, one not
            {"ref": SENTINEL, "game": "daily", "plus_flag": 0, "pool_id": 100,
             "cost_cents": 300, "scorable": True, "reason": None,
             "won_cents": 0, "draws_covered": 3, "draws_remaining": 0},
            {"ref": SENTINEL, "game": "daily", "plus_flag": 1, "pool_id": 101,
             "cost_cents": 300, "scorable": False, "reason": partly_reason,
             "won_cents": None, "draws_covered": None, "draws_remaining": None},
            # WHOLLY uncheckable — 426 real tickets are this shape against 11
            # partly, and a renderer iterating tickets that scored at least once
            # drops them all while passing on the pair above.
            {"ref": SENTINEL, "game": "lotto", "plus_flag": 0, "pool_id": 100,
             "cost_cents": 500, "scorable": False, "reason": wholly_reason,
             "won_cents": None, "draws_covered": None, "draws_remaining": None},
        ],
        uncheckable={"entries": 3, "uncheckable": 2, "too_old": 1, "no_pool": 1,
                     "wholly": 1, "partly": 1},
        wins=[],
    )
    html = render_pure(model)
    import re

    # Unscorable entries deliberately render in BOTH the outstanding section and
    # the entries table (§4.5), so scope the per-cell assertions to the entries
    # table; the presence assertions below cover the other section separately.
    table = re.search(r'<table id="entries">.*?</table>', html, re.S)
    need(table is not None, "the entries table is missing entirely")
    rows = [r for r in re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(0), re.S)
            if "<td" in r]
    need(len(rows) == 3, f"expected 3 entry rows, found {len(rows)}")

    for reason in (partly_reason, wholly_reason):
        need(reason in html, f"the reason {reason!r} is not rendered")

    def cell_text(c):
        """Tags stripped, entities DECODED, whitespace collapsed.

        Decoding matters: a renderer emitting `&mdash;` produces a dash on
        screen, and comparing the raw markup against "—" would never match it —
        the case would go green against exactly the rendering it forbids.
        """
        import html as _h

        return " ".join(_h.unescape(re.sub(r"<[^>]+>", "", c)).split())

    unscorable_rows = [r for r in rows if wholly_reason in r or partly_reason in r]
    need(
        len(unscorable_rows) == 2,
        f"expected both unscorable entries in the entries table, found "
        f"{len(unscorable_rows)} — a renderer that iterates only tickets which "
        f"scored at least once drops the wholly uncheckable ones",
    )
    for r in unscorable_rows:
        cells = [cell_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        need(len(cells) == 6, f"an entry row has {len(cells)} cells, expected 6")
        _ref, _pool, _cost, covered, won, reason = cells
        # The empty string is IN the forbidden set: a blank cell in a money
        # column reads as nil, which is the failure this project exists to stop.
        need(
            won not in forbidden,
            f"the amount cell of an unscorable entry rendered {won!r}, which is "
            f"one of the forbidden strings {sorted(forbidden)}",
        )
        need(
            covered not in forbidden,
            f"the draws-checked cell of an unscorable entry rendered {covered!r}",
        )
        need("not checkable" in won.lower(), f"the amount cell reads {won!r}")
        need(reason, "an unscorable row rendered no reason at all")

    # The scorable half of the partly-uncheckable ticket must render too, or the
    # invariant's second clause has no assertion at all.
    scorable_rows = [r for r in rows if "daily/0" in r]
    need(scorable_rows, "the scorable pool of the partly uncheckable ticket is missing")
    need("R0.00" in scorable_rows[0], "a scored-but-lost entry should show R0.00")


def render_pure(model, token="tok"):
    """Render with all_draws replaced by a double that RAISES.

    That is what makes "page.py performs no I/O" a real assertion: with no
    archive_results.json, history.all_draws() falls straight through to a live
    API call which SUCCEEDS on a connected machine, so a renderer calling it
    would otherwise pass unnoticed.
    """
    import history

    real = history.all_draws

    def explode(*a, **k):
        raise AssertionError("page.py called all_draws() — it must perform no I/O")

    history.all_draws = explode
    try:
        return page.render(model, token)
    finally:
        history.all_draws = real


def spend_over_checkable():
    """INV-16 — the compared spend is the apportioned cost of the checkable
    entries of RESOLVED tickets, and nothing else."""
    temp_home()
    import tickets as tk

    # Four tickets: fully checkable, partly, wholly unscorable, and one whose
    # price resolves to no tier. Without the fourth the "of resolved tickets"
    # clause cannot fail, and the real dump supplies no case (0 unresolved).
    inc = {pf: i for pf, _c, i in tk.TIER_PRICES[("lotto", "ithuba")]}
    entries, spend_life, expected_cmp = [], 0, 0
    spec = [
        ("full", True, [(0, True), (1, True)]),
        ("partly", True, [(0, True), (1, False)]),
        ("wholly", True, [(0, False)]),
        ("unresolved", False, [(0, True)]),
    ]
    for ref, resolved, pools in spec:
        for pf, ok in pools:
            cost = inc[pf] * 1 * 1  # one board, one draw
            spend_life += cost
            if ok and resolved:
                expected_cmp += cost      # recomputed from TIER_PRICES directly
            entries.append({
                "ref": SENTINEL, "game": "lotto", "plus_flag": pf, "pool_id": 100 + pf,
                "cost_cents": cost, "scorable": ok,
                "reason": None if ok else "predates all draw data for this pool",
                "won_cents": 0 if ok else None,
                "draws_covered": 1 if ok else None,
                "draws_remaining": 0 if ok else None,
            })
    unresolved_cents = 999
    model = fixture_model(
        entries=entries, wins=[],
        spend={"compared_cents": expected_cmp, "lifetime_cents": spend_life,
               "unresolved_cents": unresolved_cents, "unresolved_tickets": 1},
        won={"compared_cents": 0, "lifetime_cents": 0, "unexpired_cents": 0},
        uncheckable={"entries": len(entries), "uncheckable": 2, "too_old": 2,
                     "no_pool": 0, "wholly": 1, "partly": 1},
    )
    if broken("spend_is_lifetime"):
        model["spend"]["compared_cents"] = spend_life

    html = render_pure(model)
    want = f"R{expected_cmp / 100:,.2f}"
    life = f"R{spend_life / 100:,.2f}"
    need(want in html, f"the compared spend {want} is not on the page")
    need(life in html, f"the lifetime spend {life} is not on the page")
    need(
        expected_cmp < spend_life,
        "the fixture is degenerate: compared and lifetime spend are equal",
    )
    need(
        f"R{unresolved_cents / 100:,.2f}" in html,
        "the unresolved ticket has no separate labelled line",
    )
    # And the rendered compared figure must EQUAL the independent recomputation.
    import re

    row = re.search(r"Spent on entries that could be scored.*?>([R0-9,.]+)<", html, re.S)
    need(row is not None, "could not find the compared-spend figure on the page")
    need(
        row.group(1) == want,
        f"compared spend is {row.group(1)}, recomputed {want} from TIER_PRICES",
    )


def refresh_refetches():
    """INV-17 — a refresh empties all three memos BEFORE rebuilding."""
    temp_home()
    import check
    import history
    import results

    history._cache[("sentinel", 0)] = ["stale"]
    results._divisions_cache[("sentinel", 1, 100, 0)] = ["stale"]
    check._struct[("sentinel", 0, 100)] = {"stale": "stale"}

    state = serve.State()
    stub = Stub()
    if broken("clear_after_build"):
        # RED-TEST: clear AFTER building. "Empty afterwards" is satisfied
        # perfectly while the build reads the previous run's division tables.
        def late(state_, fn):
            if not state_.begin():
                return False

            def work():
                try:
                    state_.finish(fn())
                finally:
                    history._cache.clear()
                    results._divisions_cache.clear()
                    check._struct.clear()

            import threading

            threading.Thread(target=work, daemon=True).start()
            return True

        need(late(state, stub), "refresh was declined")
    else:
        need(serve.refresh(state, stub), "refresh was declined")
    need(state.wait_idle(5), "the build did not finish within 5s")

    need(stub.calls == 1, f"the builder ran {stub.calls} times, expected 1")
    need(
        stub.memos_empty_at_call is True,
        "the memos were NOT empty when the builder was called — a build that "
        "clears afterwards prices new draws from the previous run's tables",
    )
    need(not history._cache, "history._cache is not empty")
    need(not results._divisions_cache, "results._divisions_cache is not empty")
    need(not check._struct, "check._struct is not empty")


def failed_refresh_keeps_model():
    """INV-18 — a failed refresh keeps the previous model and says so."""
    temp_home()
    good = Stub()
    srv, state, port, _t = serve_on(good)
    host = f"127.0.0.1:{port}"
    try:
        # make_server does not build; main() does. Establish a good model first,
        # or "the previous model survived" has no previous model to be about.
        need(serve.refresh(state, good), "the opening refresh was declined")
        need(state.wait_idle(5), "the opening build did not finish")
        _st, _h, before = req(port, "GET", "/", host=host)
        built_before = json.loads(req(port, "GET", "/status", host=host)[2])["built"]
        need(built_before, "no successful build was recorded")

        bad = Stub(raises=True)
        if broken("clear_model_on_failure"):
            real_fail = serve.State.fail

            def wipe(self, exc, pools=()):
                self.model = None          # RED-TEST: lose the previous model
                real_fail(self, exc, pools)

            serve.State.fail = wipe
        try:
            need(serve.refresh(state, bad), "the refresh was declined")
            need(state.wait_idle(5), "the failed build did not finish")
            _st, _h, after = req(port, "GET", "/", host=host)
            status = json.loads(req(port, "GET", "/status", host=host)[2])
            need(status["stale"] is True, "GET /status does not report stale")
            need(
                status["built"] == built_before,
                "built moved on a FAILED refresh",
            )
            need(
                SENTINEL.encode() in after,
                "the previous model's wins are gone after a failed refresh",
            )
            need(b"R50.00" in after, "the previous model's amounts are gone")
            need(b"earlier fetch" in after, "the page does not say the figures are stale")
            del before
        finally:
            if broken("clear_model_on_failure"):
                serve.State.fail = real_fail
    finally:
        srv.shutdown()


def serve_is_headless():
    """INV-19 — importing serve or supervise pulls in no Qt, blocks, or spawns."""
    root = ROOT
    # RED-TEST: a shared helper grows a Qt import. Copy the tree and add one.
    # Two breaks, one per binding, because the predicate has to see both and a
    # PySide-shaped one cannot prove it does: PySide6 is what §3 pins, PyQt is
    # what a habit reaches for, and PyQt6 is importable on this machine
    # (LOTTO-0017). Only one break is ever applied at a time.
    if broken("qt_import") or broken("pyqt_import"):
        binding = "PySide6.QtCore" if broken("qt_import") else "PyQt6.QtCore"
        root = tempfile.mkdtemp(prefix="lotto-qt-")
        for f in ("serve.py", "page.py", "supervise.py", "check.py", "history.py",
                  "tickets.py", "results.py", "backfill.py"):
            shutil.copy(os.path.join(ROOT, f), root)
        with open(os.path.join(root, "serve.py"), "a") as fh:
            fh.write(f"\nimport {binding}  # noqa: F401\n")

    probe = (
        "import sys, os, json, re\n"
        "import {mod}\n"
        # Three arms, one per binding this could arrive as. The PyQt arm is
        # LOTTO-0017: without it a `PyQt6.QtCore` import passes a check whose
        # invariant reads "no Qt" - the name holds no 'PySide' and its
        # top-level package is 'PyQt6', not 'Qt'. Matched on the top-level
        # package so a submodule (PyQt6.QtWidgets) counts and an unrelated
        # package merely containing the letters does not.
        "qt = [m for m in sys.modules if 'PySide' in m "
        "or re.fullmatch(r'Qt|PyQt\\d*', m.split('.')[0])]\n"
        "kids = []\n"
        "try:\n"
        "    import glob\n"
        "    for p in glob.glob('/proc/self/task/*/children'):\n"
        "        kids += open(p).read().split()\n"
        "except OSError:\n"
        "    pass\n"
        "print(json.dumps({{'qt': qt, 'children': kids}}))\n"
    )
    for mod in ("serve", "supervise"):
        try:
            out = subprocess.run(
                [sys.executable, "-c", probe.format(mod=mod)],
                cwd=root, capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            raise Fail(f"importing {mod} blocked — it must start no server")
        need(out.returncode == 0, f"importing {mod} failed: {out.stderr.strip()[:300]}")
        data = json.loads(out.stdout.strip().splitlines()[-1])
        need(not data["qt"], f"importing {mod} pulled in Qt: {data['qt']}")
        need(not data["children"], f"importing {mod} spawned {data['children']}")
    if root != ROOT:
        shutil.rmtree(root, ignore_errors=True)


def no_orphan_server():
    """INV-20 — a Supervisor that started a server and stopped it leaves no
    process holding the port."""
    temp_home()
    port = supervise.free_port()          # a concrete number, never LOTTO_PORT=0
    os.environ["LOTTO_NO_BUILD"] = "1"    # bind and serve, build nothing
    sup = supervise.Supervisor(port=port)
    if broken("terminate_only"):
        # RED-TEST: no kill(), no wait(), no poll() — nothing collects the
        # status, so the child is never reaped.
        def bare(self, timeout=5.0):
            self.token = None
            if self.child is not None and self.child.poll() is None:
                self.child.terminate()
                time.sleep(0.5)

        sup.stop = bare.__get__(sup, supervise.Supervisor)
    try:
        sup.start()
        # The readiness wait is what stops this being a tautology: a serve.py
        # that dies instantly on an import error satisfies both closing
        # assertions — it has certainly exited, and the port is certainly free.
        need(sup.is_ready(15), "the child never answered on its port")
        pid = sup.child.pid
        sup.stop()

        # Order matters: os.kill(pid, 0) does NOT reap, while poll()/wait() do,
        # so checking exit through poll() first would make the returncode
        # assertion below always true.
        gone = False
        for _ in range(50):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                gone = True
                break
            except PermissionError:
                gone = True
                break
        need(gone, f"pid {pid} is still in the process table after stop()")
        need(
            sup.child.returncode is not None,
            "the child's exit status was never collected — it was not reaped",
        )
        bound = False
        for _ in range(50):                # not TIME_WAIT: SO_REUSEADDR binds
                                           # over that (measured). This covers
                                           # the kernel's teardown window.
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                bound = True
                break
            except OSError:
                time.sleep(0.1)
            finally:
                s.close()
        need(bound, f"port {port} is still held after stop()")
    finally:
        os.environ.pop("LOTTO_NO_BUILD", None)
        if sup.child is not None and sup.child.poll() is None:
            sup.child.kill()
            sup.child.wait(timeout=5)


def refresh_reports_the_build():
    """INV-23 - a refresh is reported as DONE only after its build finished,
    and a build that failed, is still running or was never started is never
    reported as a success."""
    temp_home()
    import threading

    # Two servers, because make_server() binds its builder at construction and
    # POST /refresh re-invokes that same callable: one cannot both block and
    # raise. The gate is an Event rather than a sleep so the case CONTROLS when
    # the build finishes - a machine under load cannot turn this into a flake.
    gate = threading.Event()

    def gated():
        gate.wait(30)
        return fixture_model()

    srv, _state, port, _t = serve_on(gated)
    srv2, _state2, port2, _t2 = serve_on(Stub(raises=True))

    def driver(p):
        # start() is the only MINTER of the token, not the only writer: this
        # Supervisor talks to a server it did not spawn (LOTTO-0013 §4.1).
        sup = supervise.Supervisor(port=p)
        sup.token = "tok"
        return sup

    sup, bad_sup = driver(port), driver(port2)

    if broken("notify_on_202"):
        # RED-TEST: the shipped defect - treat the 202 as completion.
        def early(self, timeout=300.0, interval=2.0):
            self.post("/refresh", timeout=min(supervise.POST_TIMEOUT, timeout))
            return supervise.REFRESH_DONE

        supervise.Supervisor.refresh = early
    if broken("stale_is_success"):
        # RED-TEST: wait correctly, then ignore `stale`. A patient lie.
        real_refresh = supervise.Supervisor.refresh

        def blind(self, timeout=300.0, interval=2.0):
            out = real_refresh(self, timeout=timeout, interval=interval)
            return supervise.REFRESH_DONE if out == supervise.REFRESH_FAILED else out

        supervise.Supervisor.refresh = blind
    if broken("success_wording"):
        # RED-TEST: the timing half stays correct and the wording half lies.
        supervise.REFRESH_MESSAGE[supervise.REFRESH_RUNNING] = "Results refreshed."

    try:
        # 1. It must not have returned while the builder is still blocked. This
        #    is the assertion that separates REPORTED from FINISHED; a 202
        #    arrives in milliseconds.
        gate.clear()
        out = {}
        job = threading.Thread(
            target=lambda: out.update(r=sup.refresh(interval=0.2)), daemon=True
        )
        job.start()
        job.join(0.6)  # three poll intervals
        need(
            job.is_alive(),
            "refresh() returned while the build was still running - 202 means "
            "accepted, not finished",
        )

        # 5. A second refresh while that build is in flight: 409 -> BUSY, and
        #    returned at once rather than waiting on someone else's build.
        started = time.monotonic()
        busy = sup.refresh(interval=0.2)
        need(
            busy == supervise.REFRESH_BUSY,
            f"a refresh during a build reported {busy!r}, expected REFRESH_BUSY",
        )
        need(
            time.monotonic() - started < 0.2,
            "the 409 was polled on rather than reported at once",
        )

        # 2. Released, it reports DONE.
        gate.set()
        job.join(15)
        need(not job.is_alive(), "refresh() never returned after the build finished")
        need(
            out.get("r") == supervise.REFRESH_DONE,
            f"a finished build reported {out.get('r')!r}, expected REFRESH_DONE",
        )

        # 4. Still blocked when a short budget expires: RUNNING, and neither of
        #    the two verdicts nothing observed.
        gate.clear()
        running = sup.refresh(timeout=0.5, interval=0.2)
        need(
            running == supervise.REFRESH_RUNNING,
            f"an unfinished build reported {running!r}, expected REFRESH_RUNNING",
        )
        gate.set()

        # 3. A build that raises reports FAILED. (That the previous model
        #    survives is INV-18's, and failed_refresh_keeps_model asserts it.)
        failed = bad_sup.refresh(interval=0.2)
        need(
            failed == supervise.REFRESH_FAILED,
            f"a failed build reported {failed!r}, expected REFRESH_FAILED",
        )

        # The wording half. No server needed, and checkable only because the
        # map lives in Qt-free supervise.py.
        outcomes = (
            supervise.REFRESH_DONE,
            supervise.REFRESH_FAILED,
            supervise.REFRESH_RUNNING,
            supervise.REFRESH_BUSY,
        )
        for outcome in outcomes:
            need(
                (supervise.REFRESH_MESSAGE.get(outcome) or "").strip(),
                f"outcome {outcome!r} has no sentence in REFRESH_MESSAGE",
            )
        for outcome in outcomes[1:]:
            said = supervise.REFRESH_MESSAGE[outcome].casefold()
            for word in ("refreshed", "updated", "up to date", "success"):
                need(
                    word not in said,
                    f"{outcome!r} reads as success: {word!r} in "
                    f"{supervise.REFRESH_MESSAGE[outcome]!r}",
                )
    finally:
        gate.set()  # or a server thread stays parked inside the builder
        srv.shutdown()
        srv2.shutdown()


def nothing_in_the_url():
    """INV-21 — no ticket data in any URL, fragment or title; no-store on all."""
    temp_home()
    stub = Stub()
    srv, state, port, _t = serve_on(stub)
    host = f"127.0.0.1:{port}"
    try:
        need(serve.refresh(state, stub), "the opening refresh was declined")
        need(state.wait_idle(5), "the opening build did not finish")
        _s1, h1, plain = req(port, "GET", "/", host=host)
        _s2, h2, withq = req(port, "GET", "/?game=lotto&ref=" + SENTINEL, host=host)
        need(plain == withq, "GET / renders differently with a query string")
        j1 = json.loads(req(port, "GET", "/status", host=host)[2])
        j2 = json.loads(req(port, "GET", "/status?x=1", host=host)[2])
        need(set(j1) == set(j2), "GET /status key set differs with a query string")
        need(j1["stale"] == j2["stale"], "GET /status stale differs with a query")

        need(b"<title>Lotto Tracker</title>" in plain, "the title is not the constant")
        text = plain.decode()
        for forbidden in ("pushState", "replaceState", "location.hash",
                          "location.search", "location.href", "location.assign",
                          'href="?', "href='?", 'href="#', "<form"):
            need(
                forbidden not in text,
                f"the page contains {forbidden!r} — that puts ticket data in the URL",
            )
        for hdrs, where in ((h1, "GET /"), (h2, "GET /?…")):
            check_headers(hdrs, where)

        # The routing floor: both responses must name nothing from the request.
        st, hdrs, body = req(port, "GET", "/nope", host=host)
        need(st == 404, f"an unknown path returned {st}, expected 404")
        need(body == b"", "the 404 has a body")
        check_headers(hdrs, "404")
        st, hdrs, _ = req(port, "POST", "/", host=host,
                           headers={"X-Lotto-Token": "tok"}, body={})
        need(st == 405, f"POST / returned {st}, expected 405")
        need(hdrs.get("Allow") == "GET", f"405 Allow is {hdrs.get('Allow')!r}")
        check_headers(hdrs, "405")
    finally:
        srv.shutdown()


def _serve_child(env_extra, **kw):
    return subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "serve.py")],
        cwd=ROOT,
        env={**os.environ, "LOTTO_NO_BUILD": "1", **env_extra},
        **kw,
    )


def _child_on(env_extra, port, timeout=15.0):
    """True once a `python3 serve.py` spawned with these variables answers on
    `port`. The seam is the PROCESS, not resolve_port(): the question this half
    of INV-24 asks is what main() actually binds. LOTTO_NO_BUILD keeps it off
    the network."""
    child = _serve_child(env_extra)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if child.poll() is not None:
                return False       # it exited; it is not serving anywhere
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=1)
                return True
            except urllib.error.HTTPError:
                return True        # any status is an answer; 421 is still a bind
            except (urllib.error.URLError, OSError):
                time.sleep(0.1)
        return False
    finally:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def port_from_environment():
    """INV-24 — $PORT wins, $LOTTO_PORT is unchanged, and a value meant as a
    port that cannot be one exits instead of binding something else."""
    temp_home()
    real = serve.resolve_port
    if broken("port_silent_fallback"):
        # RED-TEST: the exact shape the invariant forbids — a bad value falls
        # back to 4322, which every caller reads as "it did what I asked".
        def lenient(env=None):
            try:
                return real(env)
            except SystemExit:
                return serve.DEFAULT_PORT

        serve.resolve_port = lenient
    if broken("lotto_port_wins"):
        # RED-TEST: precedence the other way round. Indistinguishable from
        # correct on every machine where only one of the two is ever set.
        def swapped(env=None):
            env = os.environ if env is None else env
            flip = dict(env)
            flip["PORT"] = env.get("LOTTO_PORT") or ""
            flip["LOTTO_PORT"] = env.get("PORT") or ""
            return real(flip)

        serve.resolve_port = swapped

    # Explicit dicts, never the ambient environment: a case that reads os.environ
    # passes or fails according to how the developer's shell happens to be set.
    try:
        for env, want, why in (
            ({}, serve.DEFAULT_PORT, "neither variable set"),
            ({"PORT": "", "LOTTO_PORT": ""}, serve.DEFAULT_PORT, "both empty"),
            ({"LOTTO_PORT": "5001"}, 5001, "LOTTO_PORT alone"),
            ({"PORT": "5999"}, 5999, "PORT alone"),
            ({"PORT": "5999", "LOTTO_PORT": "5001"}, 5999, "PORT must win"),
            ({"PORT": "", "LOTTO_PORT": "5001"}, 5001, "an empty PORT is no value"),
            # Resolution SHORT-CIRCUITS: nothing looked at the bad one, so it is
            # not an error. An implementation that validates both eagerly exits
            # here, and passes every other assertion in this case.
            ({"PORT": "5999", "LOTTO_PORT": "abc"}, 5999, "a bad LOTTO_PORT behind a valid PORT"),
        ):
            got = serve.resolve_port(env)
            need(got == want, f"{why}: resolved to {got}, expected {want}")

        # Both variables, because the unhandled ValueError this replaces was in
        # the LOTTO_PORT path and fixing only the new one leaves it there.
        for name, value in (
            ("PORT", "abc"), ("PORT", "80"), ("PORT", "0"), ("PORT", "65536"),
            ("PORT", "-1"), ("PORT", "4322.0"),
            ("LOTTO_PORT", "abc"), ("LOTTO_PORT", "80"),
        ):
            try:
                got = serve.resolve_port({name: value})
            except SystemExit as exc:
                # The JOINED form, not the bare value: the message also carries
                # the bounds, so `"0" in msg` is satisfied by the 0 in "1024"
                # and asserts nothing for the value most likely to be mishandled.
                # Either spelling of the value - the non-numeric path reprs it,
                # which is what makes `PORT='59 99'` readable.
                joined = (f"{name}={value}", f"{name}={value!r}")
                need(
                    any(j in str(exc) for j in joined),
                    f"the message does not name {name}={value}: {exc}",
                )
            else:
                raise Fail(
                    f"{name}={value} resolved to {got} rather than exiting — "
                    "a caller that asked for a port it cannot have was told nothing"
                )
    finally:
        serve.resolve_port = real

    # The tray resolves the same two variables in the same order — one knob
    # across the project — and differs only in what a BAD value does: it falls
    # back with a message where serve.py exits (LOTTO-0013 §4.5). Both halves
    # are asserted, because the fallback is what makes the shared precedence
    # safe rather than a second silent substitution.
    saved = {k: os.environ.get(k) for k in ("PORT", "LOTTO_PORT")}
    real_pod = supervise._port_or_default
    if broken("supervisor_ignores_port"):
        # RED-TEST: the tray reads its own variable only — the shape before
        # LOTTO-0024, where a $PORT set for the whole project is silently
        # ignored on the one path a human starts by hand.
        def lotto_only(port):
            if port is None and not os.environ.get("LOTTO_PORT"):
                return supervise.DEFAULT_PORT, None
            return real_pod(port)

        supervise._port_or_default = lotto_only
    if broken("tray_silent_fallback"):
        # RED-TEST: it still falls back, and stops saying so. The fallback is
        # only defensible while the user is told — otherwise it is the silent
        # substitution serve.py exits to avoid, with no terminal to notice it in.
        def mute(port):
            return real_pod(port)[0], None

        supervise._port_or_default = mute
    try:
        for env, want, fallback, why in (
            ({}, supervise.DEFAULT_PORT, False, "neither set"),
            ({"LOTTO_PORT": "5001"}, 5001, False, "LOTTO_PORT alone"),
            ({"PORT": "5999"}, 5999, False, "PORT alone"),
            ({"PORT": "5999", "LOTTO_PORT": "5001"}, 5999, False, "PORT must win"),
            ({"PORT": "", "LOTTO_PORT": "5001"}, 5001, False, "an empty PORT is no value"),
            ({"PORT": "abc"}, supervise.DEFAULT_PORT, True, "a bad PORT falls back"),
            ({"PORT": "80"}, supervise.DEFAULT_PORT, True, "an out-of-range PORT"),
            ({"LOTTO_PORT": "abc"}, supervise.DEFAULT_PORT, True, "a bad LOTTO_PORT"),
        ):
            for key in ("PORT", "LOTTO_PORT"):
                os.environ.pop(key, None)
            os.environ.update(env)
            sup = supervise.Supervisor()
            need(sup.port == want, f"the tray, {why}: got {sup.port}, expected {want}")
            need(
                bool(sup.port_fallback) == fallback,
                f"the tray, {why}: port_fallback is {sup.port_fallback!r}",
            )
            if fallback:
                # Named, or the notification cannot say what was ignored - and a
                # fallback nobody can act on is the silent substitution again.
                name, value = next(iter(env.items()))
                need(
                    f"{name}={value}" in sup.port_fallback
                    or f"{name}={value!r}" in sup.port_fallback,
                    f"the fallback message does not name {name}={value}: "
                    f"{sup.port_fallback}",
                )
    finally:
        supervise._port_or_default = real_pod
        for key, value in saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value

    # End to end, three children: the resolved port is the port that gets bound;
    # a REJECTED value ends the process rather than binding something else; and a
    # supervised child lands on the port the tray is watching even when the
    # session exports a PORT of its own (LOTTO-0013 §4.5's 421).
    port = supervise.free_port()
    need(_child_on({"PORT": str(port)}, port), f"no server answered on PORT={port}")

    # Not redundant with the resolution half above: an implementation whose
    # main() caught the SystemExit and bound DEFAULT_PORT anyway passes every
    # assertion up there while doing exactly what port_silent_fallback does.
    idle = supervise.free_port()
    bad = _serve_child(
        {"PORT": "abc", "LOTTO_PORT": str(idle)},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _out, err = bad.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        bad.kill()
        bad.wait(timeout=5)
        raise Fail("a rejected PORT left a server running instead of exiting")
    need(bad.returncode != 0, f"a rejected PORT exited {bad.returncode}, expected non-zero")
    need("PORT='abc'" in err, f"the exit message does not name the value: {err.strip()[:200]}")
    # The valid LOTTO_PORT is the trap: a fallback would have bound it happily.
    probe = socket.socket()
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("127.0.0.1", idle))
    except OSError:
        raise Fail(f"a rejected PORT fell back and bound {idle}")
    finally:
        probe.close()

    decoy, wanted = supervise.free_port(), supervise.free_port()
    os.environ["PORT"] = str(decoy)
    sup = supervise.Supervisor(port=wanted)
    os.environ["LOTTO_NO_BUILD"] = "1"
    try:
        sup.start()
        need(
            sup.is_ready(15),
            f"the child ignored the supervisor's port {wanted}; an inherited "
            f"PORT={decoy} would 421 every request the tray makes",
        )
    finally:
        sup.stop()
        os.environ.pop("PORT", None)
        os.environ.pop("LOTTO_NO_BUILD", None)


# The probe runs in its own process because importing tray.py imports PySide6,
# and this file must stay importable by the four headless tools beside it.
# Qt is never CONSTRUCTED here: QApplication is replaced with something that
# raises, so reaching it at all is the failure.
TRAY_PROBE = r'''
import json, os, sys
sys.path.insert(0, {root!r})
import supervise, tray

calls = []


class FakeChild:
    def wait(self, timeout=None):
        calls.append("wait")
        return 0

    def poll(self):
        return None


class FakeSup:
    port_fallback = None
    url = "http://127.0.0.1:65000"

    def __init__(self, port=None):
        self.child = FakeChild()

    def start(self):
        calls.append("start")

    def is_ready(self, timeout=10.0):
        calls.append("is_ready")
        return True

    def stop(self, timeout=5.0):
        calls.append("stop")


def explode(*a, **k):
    raise RuntimeError("constructed a Qt object")


supervise.Supervisor = FakeSup
tray.QApplication = explode

brk = os.environ.get("LOTTO_BREAK") or ""
if brk == "tray_icon_when_managed":
    tray.managed = lambda: False
if brk == "headless_stops_server":
    inner = tray.run_headless

    def stopper(sup=None):
        sup = supervise.Supervisor() if sup is None else sup
        sup.stop()
        return inner(sup)

    tray.run_headless = stopper

out = {{"calls": calls, "error": None, "rc": None}}
try:
    out["rc"] = tray.main()
except BaseException as exc:
    out["error"] = "{{}}: {{}}".format(type(exc).__name__, exc)
out["calls"] = calls
print(json.dumps(out))
'''


def _tray_probe(env_extra):
    # A None value means UNSET, not empty: the absent case must be absent even
    # in a shell that exports LWSM_MANAGED itself.
    env = {**os.environ, **{k: v for k, v in env_extra.items() if v is not None}}
    for key, value in env_extra.items():
        if value is None:
            env.pop(key, None)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (USER_SITE, env.get("PYTHONPATH")) if p
    )
    out = subprocess.run(
        [sys.executable, "-c", TRAY_PROBE.format(root=ROOT)],
        cwd=ROOT, capture_output=True, text=True, timeout=60, env=env,
    )
    need(out.returncode == 0, f"the tray probe died: {out.stderr.strip()[:400]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


def tray_headless_when_managed():
    """INV-25 — LWSM_MANAGED=1 runs the tray with no icon and no path that can
    stop the server; every other value is the unchanged tray."""
    temp_home()
    run = _tray_probe({"LWSM_MANAGED": "1"})
    need(run["error"] is None, f"the managed run reached Qt: {run['error']}")
    need("start" in run["calls"], "the managed run never started the server")
    need("wait" in run["calls"], "the managed run did not wait on the child")
    need(
        "stop" not in run["calls"],
        "a headless path stopped a server the manager believes it owns",
    )
    need(run["rc"] == 0, f"the managed run returned {run['rc']}, expected the child's 0")

    # Absence is the unchanged path, and so is every value that is not "1" - a
    # presentation hint that anything truthy satisfies is one a stray
    # LWSM_MANAGED=0 turns on.
    for value in (None, "", "0", "true", "yes", "2"):
        other = _tray_probe({"LWSM_MANAGED": value})
        need(
            other["error"] is not None and "Qt" in other["error"],
            f"LWSM_MANAGED={value!r} did not take the tray path: {other}",
        )
        need(
            "start" not in other["calls"],
            f"LWSM_MANAGED={value!r} started a server on the headless path",
        )


# ------------------------------------------------- LOTTO-0019: build reporting
#
# INV-27, INV-28, INV-29, INV-30. Two of these install a TRANSPORT seam beside
# the builder seam the other eleven cases use, which is a deliberate exception
# to §7's inherited constraints: an inert stub builder never enters
# results._post(), so requests_made would be 0 on every refresh and both of
# build_progress_is_visible's counter breaks would be unobservable. The
# no-network and no-real-data constraints are untouched — nothing here reaches
# the operator's API or reads the dump.

_OK_PAYLOAD = json.dumps({"code": 0, "data": {"list": []}}).encode()


def _stub_transport(fail_first=0):
    """Replace results' urlopen. Returns (restore, calls) — `calls` is a list
    appended to per ATTEMPT, so len(calls) is the true attempt count.

    PROCESS-GLOBAL and there is no narrower seam: results.py does
    `import urllib.request`, so this attribute IS the shared module's, _post()
    holds no opener object, and urllib.request.install_opener() is equally
    global. While installed it also intercepts supervise.Supervisor.status()
    and .post() — so every caller restores it in a `finally`. tools' req()
    uses http.client and is unaffected.
    """
    import io

    real = urllib.request.urlopen
    calls = []

    def stub(_req_or_url, *a, **k):
        calls.append(1)
        if len(calls) <= fail_first:
            raise urllib.error.URLError("SSL: UNEXPECTED_EOF_WHILE_READING")
        return io.BytesIO(_OK_PAYLOAD)

    urllib.request.urlopen = stub

    def restore():
        urllib.request.urlopen = real

    return restore, calls


def post_retries_transport_failure():
    """INV-27 — _post retries a transport failure, then re-raises the original.

    Two stub scripts in turn: raise twice then succeed, and raise on every
    attempt. An HTTPError is checked separately: it must cost exactly one.
    """
    import results

    real_backoff = results.BACKOFF
    real_attempts = results.ATTEMPTS
    real_http = urllib.error.HTTPError
    # Or the exhaustion path really sleeps 3 s, the way LOTTO-0013's INV-23
    # case budgets its own poll interval down.
    results.BACKOFF = 0.001
    if broken("no_retry"):
        # RED-TEST: the shipped behaviour before LOTTO-0012 — one attempt, and
        # the first URLError aborts the caller.
        results.ATTEMPTS = 1
    if broken("retry_http_error"):
        # RED-TEST: shadow the class the ordering rule depends on, so the
        # `except HTTPError: raise` arm never fires and HTTPError — a URLError
        # subclass — falls into the retry arm below it.
        class _NeverMatches(Exception):
            pass

        urllib.error.HTTPError = _NeverMatches

    restore, calls = _stub_transport(fail_first=2)
    try:
        results.requests_made = 0
        got = results._post("/x", {})
        need(got == {"list": []}, f"payload not returned after retries: {got!r}")
        need(
            len(calls) == 3,
            f"took {len(calls)} attempts to survive 2 failures, expected 3",
        )
        need(
            results.requests_made == 3,
            f"counter says {results.requests_made} after 3 attempts (INV-28)",
        )
    finally:
        restore()

    # Script two: always raises. The ORIGINAL exception must escape, unwrapped.
    restore, calls = _stub_transport(fail_first=99)
    try:
        try:
            results._post("/x", {})
        except urllib.error.URLError as exc:
            need(
                "UNEXPECTED_EOF" in str(exc),
                f"exhaustion raised {exc!r}, not the original URLError",
            )
        else:
            raise Fail("an always-failing transport did not raise")
        need(
            len(calls) == real_attempts,
            f"exhaustion took {len(calls)} attempts, expected {real_attempts}",
        )
    finally:
        restore()

    # An HTTPError is an answer, not a transport failure: exactly one attempt.
    import io

    real_urlopen = urllib.request.urlopen
    http_calls = []

    def always_404(*a, **k):
        http_calls.append(1)
        raise real_http("http://x/", 404, "Not Found", {}, io.BytesIO(b""))

    urllib.request.urlopen = always_404
    try:
        try:
            results._post("/x", {})
        except Exception:
            pass
        need(
            len(http_calls) == 1,
            f"a 404 cost {len(http_calls)} attempts, expected 1 — an HTTPError "
            "is an answer and a retry gets the same one",
        )
    finally:
        urllib.request.urlopen = real_urlopen
        urllib.error.HTTPError = real_http
        results.BACKOFF = real_backoff
        results.ATTEMPTS = real_attempts


class _CountingStub:
    """A builder that really reaches results._post(), and blocks until released.

    An inert stub cannot exercise the counter at all — that is why these two
    cases add the transport seam.
    """

    def __init__(self, gate, fetches=2):
        self.gate = gate
        self.fetches = fetches
        self.calls = 0

    def __call__(self):
        import results

        self.calls += 1
        # Blocks BEFORE fetching, not after: the counter's value at the moment
        # the build is in flight but has issued nothing is the only observation
        # that separates a reset made before the thread started from one made
        # on it. Fetching first makes both readings converge on the same total.
        self.gate.wait(10)
        for _ in range(self.fetches):
            results.draws("lotto", 1)
        return fixture_model()


def build_progress_is_visible():
    """INV-28 — the counter counts attempts, resets before the thread starts,
    and is what /status reports and page.render() interpolates."""
    import threading

    import results

    temp_home()
    real_backoff = results.BACKOFF
    results.BACKOFF = 0.001
    gate = threading.Event()
    stub = _CountingStub(gate, fetches=2)
    # fail_first=1: the first fetch costs TWO attempts, so attempts (3) exceed
    # calls (2). Without a retry in the case the two are equal and
    # count_per_call cannot be observed failing.
    restore, _calls = _stub_transport(fail_first=1)
    real_refresh, real_post = serve.refresh, results._post
    srv = None

    if broken("no_counter_reset") or broken("reset_on_worker_thread"):
        late = broken("reset_on_worker_thread")

        def rigged(state_, fn):
            """RED-TEST: omit the reset entirely, or defer it onto the worker
            thread — where it runs AFTER begin() has set `building`, so /status
            reports the previous build's total while the new one is in flight."""
            if not state_.begin():
                return False

            def work():
                if late:
                    # The window the spec names, made deterministic rather than
                    # raced: the reset lives on the worker thread, and the
                    # worker thread has not reached it yet while /status is
                    # already answering `building: true`.
                    gate.wait(10)
                    results.requests_made = 0
                try:
                    state_.finish(fn())
                except Exception as exc:  # noqa: BLE001
                    state_.fail(exc)

            threading.Thread(target=work, daemon=True).start()
            return True

        serve.refresh = rigged

    if broken("count_per_call"):
        # RED-TEST: count calls, not attempts — the figure then freezes during
        # exactly the retry storm it exists to narrate.
        def once_per_call(path, body):
            before = results.requests_made
            try:
                return real_post(path, body)
            finally:
                results.requests_made = before + 1

        results._post = once_per_call

    try:
        srv, state, port, _t = serve_on(stub)
        host = f"127.0.0.1:{port}"

        # --- build 1: let it run to completion -----------------------------
        gate.set()
        need(serve.refresh(state, stub), "refresh 1 was declined")
        need(state.wait_idle(5), "build 1 did not finish within 5s")
        first = json.loads(req(port, "GET", "/status", host=host)[2])["requests"]
        need(
            first == 3,
            f"/status reported {first} requests for two fetches of which one "
            "retried once — expected 3 ATTEMPTS, not 2 calls",
        )

        # --- build 2: read /status WHILE it is still blocked ----------------
        # This is the assertion reset_on_worker_thread breaks and nothing else
        # can see: after wait_idle() a late reset has already run.
        gate.clear()
        # The stub's failure script is reset, or build 2 sees no retry and its
        # attempt count is legitimately lower than build 1's — a flaky
        # assertion rather than a wrong one (LOTTO-0019 §7).
        _calls.clear()
        need(serve.refresh(state, stub), "refresh 2 was declined")
        # Synchronous: refresh() resets before it starts the thread, so this
        # holds the instant it returns, whatever the scheduler does next.
        need(
            results.requests_made == 0,
            f"results.requests_made is {results.requests_made} the instant "
            f"refresh() returned, which is build 1's total ({first}) — the "
            "reset was omitted or deferred onto the worker thread (INV-28)",
        )
        answer = json.loads(req(port, "GET", "/status", host=host)[2])
        need(answer["building"], "build 2 was not in flight while gated")
        need(
            answer["requests"] == 0,
            f"/status reported {answer['requests']} requests for a build that "
            f"has issued none — build 1's total ({first}) is leaking into the "
            "build in flight (INV-28)",
        )
        gate.set()
        need(state.wait_idle(5), "build 2 did not finish within 5s")
        second = json.loads(req(port, "GET", "/status", host=host)[2])["requests"]
        need(
            second == first,
            f"build 2 reported {second} requests against build 1's {first} — "
            "the counter is accumulating across builds",
        )

        # --- the server-side half of the rendering clause -------------------
        html = page.render({"building": True, "built": None, "requests": 7}, "tok")
        need('id="progress"' in html, "the building page carries no progress span")
        need(
            "7 lookups so far" in html,
            f"the building page does not interpolate the count: {html[:400]!r}",
        )
        one = page.render({"building": True, "built": None, "requests": 1}, "tok")
        need("1 lookup so far" in one, "the count is not singularised at 1")
    finally:
        restore()
        serve.refresh, results._post = real_refresh, real_post
        results.BACKOFF = real_backoff
        gate.set()
        if srv is not None:
            srv.shutdown()
            srv.server_close()


def no_comparison_is_not_no_wins():
    """INV-29 — `found` is null when nothing was compared, an object with
    new_wins 0 when it was, and the two never read as the same sentence."""
    temp_home()
    win = {
        "ref": SENTINEL,
        "game": "lotto",
        "plus_flag": 0,
        "pool_id": 100,
        "line": "A",
        "date": "2026-07-04",
        "amount_cents": 24000,
    }
    other = dict(win, line="B", amount_cents=1000)

    models = [
        fixture_model(wins=[win]),
        fixture_model(wins=[win]),
        fixture_model(wins=[win, other]),
    ]
    seq = iter(models)
    state = serve.State()

    if broken("found_on_first_build"):
        # RED-TEST: compare against an empty model rather than declining to
        # compare — the first build then reports every existing win as new.
        real_compare = serve._compare
        serve._compare = lambda prev, cur: real_compare(prev or {}, cur)

    try:
        for i in range(3):
            need(serve.refresh(state, lambda: next(seq)), f"refresh {i + 1} declined")
            need(state.wait_idle(5), f"build {i + 1} did not finish within 5s")
            found = state.get()[5]
            if i == 0:
                need(
                    found is None,
                    f"the FIRST build reported {found!r} — with no predecessor "
                    "there is nothing to compare against, and reporting its "
                    "wins as new tells the user they won today (INV-29)",
                )
            elif i == 1:
                need(
                    found == {"new_wins": 0, "new_cents": 0},
                    f"an unchanged rebuild reported {found!r}, expected zeroes",
                )
            else:
                need(
                    found == {"new_wins": 1, "new_cents": 1000},
                    f"one added win reported {found!r}",
                )
    finally:
        if broken("found_on_first_build"):
            serve._compare = real_compare

    # The three sentences must be three sentences.
    if broken("null_found_reads_as_zero"):
        # RED-TEST: the cardinal rule in notification form — "could not
        # compare" rendered exactly like "compared, found nothing".
        real_msg = supervise.refresh_message
        supervise.refresh_message = lambda outcome, found=None: real_msg(
            outcome, found if found is not None else {"new_wins": 0, "new_cents": 0}
        )
    try:
        said = [
            supervise.refresh_message(supervise.REFRESH_DONE, None),
            supervise.refresh_message(
                supervise.REFRESH_DONE, {"new_wins": 0, "new_cents": 0}
            ),
            supervise.refresh_message(
                supervise.REFRESH_DONE, {"new_wins": 2, "new_cents": 24000}
            ),
        ]
        need(
            len(set(said)) == 3,
            "the three DONE states do not produce three distinct sentences — "
            f"{said!r}",
        )
    finally:
        if broken("null_found_reads_as_zero"):
            supervise.refresh_message = real_msg


# Every legitimate DONE sentence, and nothing else. Built from the two integers
# alone, so a widened `found` cannot smuggle a reference into it (INV-30).
NOTE_SHAPE = re.compile(
    r"^Results refreshed\. ("
    r"First check this session — nothing to compare against\."
    r"|No new wins\."
    r"|\d+ new winning lines?, R[\d,]+\.\d\d\."
    r")$"
)


def notification_carries_no_ticket_data():
    """INV-30 — the success notification is composed from found's two integers,
    or from nothing when found is null. No ticket data can reach it."""
    if broken("summary_names_a_ticket"):
        # RED-TEST: the well-meant version — name the ticket and the draw.
        real_msg = supervise.refresh_message

        def chatty(outcome, found=None):
            line = real_msg(outcome, found)
            if found and found.get("new_wins") and found.get("ref"):
                line += f" Your {found['game']} line {found['line']} won on {found['date']}."
            return line

        supervise.refresh_message = chatty
    try:
        # `found` widened to carry a whole win record beside the two integers:
        # if anything but the integers is read, it has something to leak.
        widened = {
            "new_wins": 2,
            "new_cents": 24000,
            "ref": SENTINEL,
            "game": "powerball",
            "line": "B",
            "date": "2026-07-04",
            "matched": "MATCH 5 + PB",
        }
        for found in (None, {"new_wins": 0, "new_cents": 0}, widened,
                      {"new_wins": 1, "new_cents": 24000}):
            said = supervise.refresh_message(supervise.REFRESH_DONE, found)
            need(
                NOTE_SHAPE.match(said) is not None,
                f"the notification is not the fixed shape: {said!r} — "
                "something other than new_wins/new_cents reached it (INV-30)",
            )
            for leak in (SENTINEL, "powerball", "2026-07-04", "MATCH 5"):
                need(
                    leak not in said,
                    f"the notification names {leak!r}: {said!r}",
                )
    finally:
        if broken("summary_names_a_ticket"):
            supervise.refresh_message = real_msg


def numbers_chosen_and_drawn():
    """INV-48 — the page shows the numbers chosen beside the numbers drawn, and
    an absent set is said in words rather than rendered blank.

    The second clause is the cardinal rule reaching the numbers columns: a
    blank cell where numbers should be reads as "no numbers", which is a
    statement about the ticket rather than about what is known.
    """
    temp_home()
    import re

    if broken("no_drawn_numbers"):
        # Show what the user picked and not what came up. The likeliest real
        # regression: the chosen half is easy and the drawn half needs the
        # model to carry per-win draw detail, so the drawn half is what a
        # half-finished change drops.
        real_cell = page._numbers_cell
        page._numbers_cell = lambda nums, special=None: (
            "<td></td>" if nums == DRAWN_MAIN else real_cell(nums, special)
        )
    if broken("blank_numbers_cell"):
        # Blank ONLY the absent case, leaving every real set rendered normally.
        # Two ways to get this break wrong, both found by writing it:
        # mangling present numbers trips assertion 1 first and never reaches
        # the cardinal-rule clause, and patching _balls misses entirely because
        # _boards_cell answers the empty case itself without calling it. The
        # break has to sit on the function that actually decides absence.
        real_boards = page._boards_cell
        page._boards_cell = lambda boards: (
            '<td class="nums"></td>' if not boards else real_boards(boards)
        )

    try:
        model = fixture_model(
            wins=[
                {
                    "ref": SENTINEL, "game": "powerball", "plus_flag": 0,
                    "pool_id": 100, "date": "2026-07-01",
                    "division": "Division 8", "matched": "MATCH 1 + PB",
                    "amount_cents": 1500, "expires": "2027-07-01",
                    "expires_in_days": 333, "expired": False,
                    "numbers": CHOSEN_MAIN, "special": 7,
                    "drawn_main": DRAWN_MAIN, "drawn_special": 7,
                },
            ],
            entries=[
                {"ref": SENTINEL, "game": "powerball", "plus_flag": 0,
                 "pool_id": 100, "cost_cents": 1000, "scorable": True,
                 "reason": None, "won_cents": 1500, "draws_covered": 2,
                 "draws_remaining": 3,
                 "boards": [{"line": "A", "numbers": CHOSEN_MAIN, "special": 7}]},
                # An entry whose boards never made it into the model. Not a
                # hypothetical: every entry built before LOTTO-0035 has none,
                # so a cached or older model reaches the renderer this way.
                {"ref": SENTINEL, "game": "lotto", "plus_flag": 0,
                 "pool_id": 100, "cost_cents": 500, "scorable": True,
                 "reason": None, "won_cents": 0, "draws_covered": 1,
                 "draws_remaining": 4, "boards": []},
            ],
            uncheckable={"entries": 2, "uncheckable": 0, "too_old": 0,
                         "no_pool": 0, "wholly": 0, "partly": 0},
        )
        html = render_pure(model)

        # 1. Both sides of the comparison reach the win row.
        for n in CHOSEN_MAIN:
            need(f">{n}</span>" in html, f"chosen number {n} is not rendered")
        for n in DRAWN_MAIN:
            need(f">{n}</span>" in html, f"drawn number {n} is not rendered")
        need("Your numbers" in html, "no 'Your numbers' column header")
        need("Drawn" in html, "no 'Drawn' column header")

        # 2. The special is rendered and marked as such, or a PowerBall ticket
        #    reads as a six-main-number ticket.
        need('class="ball special"' in html,
             "the special number is not distinguished from the mains")

        # 3. The cardinal rule: an absent set says so, and is never blank.
        need("not recorded" in html,
             "an entry with no boards rendered nothing at all")
        for empty in ('<td class="nums"></td>', "<td></td>"):
            need(empty not in html,
                 f"a numbers cell rendered as {empty!r} - blank is not an answer")

        # 4. The chosen and drawn sets must not be conflated: they differ here,
        #    so rendering one twice would pass every assertion above.
        wins_tbl = re.search(r"<h2>Claimable now</h2>.*?</table>", html, re.S)
        need(wins_tbl is not None, "the wins table is missing entirely")
        cells = re.findall(r'<td class="nums">(.*?)</td>', wins_tbl.group(0), re.S)
        need(len(cells) >= 2,
             f"expected two numbers cells on the win row, found {len(cells)}")
        need(cells[0] != cells[1],
             "the chosen and drawn cells rendered identically - one is a copy")
    finally:
        if broken("no_drawn_numbers"):
            page._numbers_cell = real_cell
        if broken("blank_numbers_cell"):
            page._boards_cell = real_boards


CASES = [
    ("host_allowlist", "INV-12", host_allowlist),
    ("token_required", "INV-13", token_required),
    ("no_reflected_headers", "INV-14", no_reflected_headers),
    ("uncheckable_not_a_loss", "INV-15", uncheckable_not_a_loss),
    ("spend_over_checkable", "INV-16", spend_over_checkable),
    ("refresh_refetches", "INV-17", refresh_refetches),
    ("failed_refresh_keeps_model", "INV-18", failed_refresh_keeps_model),
    ("serve_is_headless", "INV-19", serve_is_headless),
    ("no_orphan_server", "INV-20", no_orphan_server),
    ("nothing_in_the_url", "INV-21", nothing_in_the_url),
    ("refresh_reports_the_build", "INV-23", refresh_reports_the_build),
    ("port_from_environment", "INV-24", port_from_environment),
    ("tray_headless_when_managed", "INV-25", tray_headless_when_managed),
    ("post_retries_transport_failure", "INV-27", post_retries_transport_failure),
    ("build_progress_is_visible", "INV-28", build_progress_is_visible),
    ("no_comparison_is_not_no_wins", "INV-29", no_comparison_is_not_no_wins),
    ("notification_carries_no_ticket_data", "INV-30", notification_carries_no_ticket_data),
    ("numbers_chosen_and_drawn", "INV-48", numbers_chosen_and_drawn),
]

# Each break must make exactly the named case fail. Named in the *Test:* clauses.
BREAKS = {
    "no_drawn_numbers": "numbers_chosen_and_drawn",
    "blank_numbers_cell": "numbers_chosen_and_drawn",
    "host_endswith": "host_allowlist",
    "no_security_headers": "host_allowlist",
    "token_exempt_refresh": "token_required",
    "reflect_path": "no_reflected_headers",
    "blank_money_cell": "uncheckable_not_a_loss",
    "dash_for_unscorable": "uncheckable_not_a_loss",
    "drop_unscorable_rows": "uncheckable_not_a_loss",
    "spend_is_lifetime": "spend_over_checkable",
    "clear_after_build": "refresh_refetches",
    "clear_model_on_failure": "failed_refresh_keeps_model",
    "qt_import": "serve_is_headless",
    "pyqt_import": "serve_is_headless",
    "terminate_only": "no_orphan_server",
    "url_pushstate": "nothing_in_the_url",
    "notify_on_202": "refresh_reports_the_build",
    "stale_is_success": "refresh_reports_the_build",
    "success_wording": "refresh_reports_the_build",
    "port_silent_fallback": "port_from_environment",
    "lotto_port_wins": "port_from_environment",
    "supervisor_ignores_port": "port_from_environment",
    "tray_silent_fallback": "port_from_environment",
    "tray_icon_when_managed": "tray_headless_when_managed",
    "headless_stops_server": "tray_headless_when_managed",
    "no_retry": "post_retries_transport_failure",
    "retry_http_error": "post_retries_transport_failure",
    "no_counter_reset": "build_progress_is_visible",
    "reset_on_worker_thread": "build_progress_is_visible",
    "count_per_call": "build_progress_is_visible",
    "found_on_first_build": "no_comparison_is_not_no_wins",
    "null_found_reads_as_zero": "no_comparison_is_not_no_wins",
    "summary_names_a_ticket": "notification_carries_no_ticket_data",
}


def apply_render_breaks():
    """Breaks that live in the renderer rather than the server."""
    if broken("blank_money_cell"):
        page._money_cell = lambda won: "<td></td>"
    if broken("dash_for_unscorable"):
        # The sharpest break for the cardinal rule: score normally, but render
        # "no data" as an em-dash. Nothing else on the page changes, and a dash
        # is the likelier real-world rendering than a literal zero.
        real_cell = page._money_cell
        page._money_cell = lambda won: (
            "<td>&mdash;</td>" if won is None else real_cell(won)
        )
    if broken("drop_unscorable_rows"):
        real = page._entries_section

        def only_scorable(model):
            m = dict(model)
            m["entries"] = [e for e in model.get("entries", []) if e.get("scorable")]
            return real(m)

        page._entries_section = only_scorable
    if broken("url_pushstate"):
        page.JS = page.JS.replace(
            'if(%s)poll();', 'history.pushState({},"","?game=lotto");if(%s)poll();'
        )


def main(argv):
    if "--list" in argv:
        for name, inv, _ in CASES:
            print(f"{inv}  {name}")
        print("\nbreaks:")
        for b, case in sorted(BREAKS.items()):
            print(f"  --break {b:24} -> {case} must FAIL")
        return 0

    only = None
    for i, a in enumerate(argv):
        if a == "--only" and i + 1 < len(argv):
            only = argv[i + 1]
        if a == "--break" and i + 1 < len(argv):
            os.environ["LOTTO_BREAK"] = argv[i + 1]
    global BREAK
    BREAK = os.environ.get("LOTTO_BREAK") or ""
    if BREAK:
        need_case = BREAKS.get(BREAK)
        if need_case is None:
            print(f"unknown break {BREAK!r}; --list shows them all")
            return 2
        only = only or need_case
        print(f"RED TEST: break={BREAK} — {need_case} is expected to FAIL\n")
    apply_render_breaks()

    failures = 0
    for name, inv, fn in CASES:
        if only and name != only:
            continue
        try:
            fn()
            print(f"  PASS  {inv}  {name}")
        except Fail as exc:
            failures += 1
            print(f"  FAIL  {inv}  {name}\n          {exc}")
        except Exception as exc:  # noqa: BLE001 - report, do not mask
            failures += 1
            print(f"  ERROR {inv}  {name}\n          {type(exc).__name__}: {exc}")

    if BREAK:
        if failures:
            print(f"\nred test OK: {BREAKS[BREAK]} failed as it should")
            return 0
        print(f"\nRED TEST DID NOT GO RED: {BREAKS[BREAK]} passed with {BREAK} applied")
        return 1
    print(f"\n{len(CASES) - failures}/{len(CASES)} cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
