#!/usr/bin/env python3
"""Thirteen cases, one per invariant INV-12 to INV-21 and INV-23 to INV-25, for
the local page and the tray that drives it.

Joins tools/verify_privacy.py, verify_sources.py, verify_coverage.py and
verify_pools.py. Exit code is the signal, as with the other four.

    python3 tools/verify_page.py            # all thirteen
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
    if broken("qt_import"):
        # RED-TEST: a shared helper grows a Qt import. Copy the tree and add one.
        root = tempfile.mkdtemp(prefix="lotto-qt-")
        for f in ("serve.py", "page.py", "supervise.py", "check.py", "history.py",
                  "tickets.py", "results.py", "backfill.py"):
            shutil.copy(os.path.join(ROOT, f), root)
        with open(os.path.join(root, "serve.py"), "a") as fh:
            fh.write("\nimport PySide6.QtCore  # noqa: F401\n")

    probe = (
        "import sys, os, json\n"
        "import {mod}\n"
        "qt = [m for m in sys.modules if 'PySide' in m or m.split('.')[0] == 'Qt']\n"
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
    if broken("qt_import"):
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
                # which is what makes `PORT=' 5999 '` readable.
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
]

# Each break must make exactly the named case fail. Named in the *Test:* clauses.
BREAKS = {
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
    "terminate_only": "no_orphan_server",
    "url_pushstate": "nothing_in_the_url",
    "notify_on_202": "refresh_reports_the_build",
    "stale_is_success": "refresh_reports_the_build",
    "success_wording": "refresh_reports_the_build",
    "port_silent_fallback": "port_from_environment",
    "lotto_port_wins": "port_from_environment",
    "tray_icon_when_managed": "tray_headless_when_managed",
    "headless_stops_server": "tray_headless_when_managed",
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
