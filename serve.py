"""Serve the local page. Standard library only, and NEVER imports PySide6.

Three specs govern this file:
  LOTTO-0002  the model, the build lifecycle, what the page shows
  LOTTO-0014  the HTTP surface and the security boundary
  LOTTO-0013  INV-19 - nothing here may import Qt, at any depth

Everything that binds, builds or serves sits behind `if __name__ == "__main__"`,
so importing this module is safe and starts nothing. INV-19's check depends on
that: without it the check hangs instead of failing, and a hanging check reads
as a broken test rather than a broken contract.

    python3 serve.py            # http://127.0.0.1:4322
    PORT=5000 python3 serve.py       # $PORT wins: the knob a process manager sets
    LOTTO_PORT=5000 python3 serve.py # unchanged; used when $PORT is not set
"""

import datetime
import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import page

# Module scope, not lazy inside refresh()'s work(): GET /status reads
# results.requests_made on every poll, so it is needed outside a build too
# (LOTTO-0019 §4.2). results.py is stdlib-only, so this starts nothing and
# breaks no invariant - LOTTO-0013's INV-19 forbids Qt, not stdlib.
import results

HERE = os.path.dirname(os.path.abspath(__file__))
# ONE answer for where the dump is. build_model()'s guard resolved it against
# HERE and tickets.load() against the working directory, so started from
# anywhere else the page reported "the first build failed" for a dump that is
# merely missing - two named states of the cardinal rule collapsed into one.
DUMP = os.path.join(HERE, "lotto_sms_raw.txt")
DEFAULT_PORT = 4322
MAX_BODY = 4096  # LOTTO-0014 §4.1: an unbounded rfile.read() is a hang
BODY_KEYS = ("autostart", "open_on_start")

# Header values come from literals only. BaseHTTPRequestHandler does NOT
# validate CRLF in a header value - measured - so send_header() is never called
# with anything derived from a request (LOTTO-0014 INV-14).
SECURITY_HEADERS = (
    ("X-Frame-Options", "DENY"),
    ("Content-Security-Policy", "frame-ancestors 'none'"),
    ("Cache-Control", "no-store"),
)
ALLOW = {"/": "GET", "/status": "GET", "/refresh": "POST", "/settings": "POST"}


# --------------------------------------------------------------- settings I/O
#
# The paths and the reader live in supervise.py, which tray.py can import and
# this file can too; writing stays here because POST /settings is a server
# route. Rule 3: one reader, not two that will disagree. The port bounds come
# from there for the same reason - one pair of numbers, two different policies
# about a bad value (resolve_port() below exits; Supervisor falls back).

from supervise import (  # noqa: E402
    MAX_PORT,
    MIN_PORT,
    autostart_path,
    read_settings,
    settings_path,
    write_atomic,
)

DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name=Lotto Tracker
Comment=Tray control for the local lottery page
Exec="{python}" "{here}/tray.py"
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
"""


def _settings_snapshot():
    """read_settings() under the same lock write_settings() holds.

    That function writes two files and re-reads them; a read taken outside the
    lock can catch the pair half-updated and report a switch the user did not
    set - the failure the read-back exists to prevent, arriving from the other
    side. build_model() and do_GET() both read settings while a POST may be in
    flight.
    """
    with _settings_lock:
        return read_settings()


def write_settings(changes):
    """Apply the validated booleans, then re-read from disk.

    Under one lock: the server is threaded, this writes two files and then reads
    them back, and two concurrent toggles without it can each return the other's
    result - a switch snapping to a value the user did not choose, which is the
    failure the read-back exists to prevent.
    """
    with _settings_lock:
        if "autostart" in changes:
            path = autostart_path()
            if changes["autostart"]:
                write_atomic(
                    path,
                    DESKTOP_ENTRY.format(python=sys.executable, here=HERE),
                )
            else:
                # Delete it. Rewriting X-GNOME-Autostart-enabled to false would
                # leave the file present, and "presence IS the state" is what
                # stops this switch drifting from what the desktop does.
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass
        if "open_on_start" in changes:
            write_atomic(
                settings_path(),
                json.dumps({"open_on_start": changes["open_on_start"]}),
            )
        return read_settings()


# ----------------------------------------------------------------- the model


def tier_increments(game, era):
    """The INCREMENT column of TIER_PRICES, keyed by plus_flag.

    A different column from the cumulative total entered_pools() matches on;
    conflating them prices a R10.00 Lotto ticket at R22.50.
    """
    import tickets

    return {pf: inc for pf, _cum, inc in tickets.TIER_PRICES[(game, era)]}


MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def period_buckets(all_tickets, wins, entry_draws, increments):
    """The per-period rows and the no-result residue (LOTTO-0036 §4.5).

    Pure: no I/O, no globals, no clock. `entry_draws(ticket, plus_flag)` gives
    the ISO dates of the draws that entry covers, or None when nothing can
    score it; `increments(game, era)` gives that era's {plus_flag: per-board,
    per-draw cents}. Both are injected so tools/verify_periods.py can drive the
    rules over synthetic tickets with no results file (INV-57..INV-60) --
    tools/verify_page.py cannot, being renderer-only by design.

    Money belongs to the period of the DRAW, never of the purchase (§3.1),
    over INV-16's population: the scorable entries of RESOLVED tickets, BOTH
    conditions. check.py::check() gates on scorable() alone, so the resolved
    filter has to be applied to the win side here or an unresolved ticket's
    winnings land in a bucket whose cost was excluded (INV-59).

    The key set comes from the SPEND side; the win side only adds into keys
    that already exist. A win whose period carries no spend is dropped rather
    than conjuring a bucket, which would be an R0.00 spend against a real win
    (INV-60).
    """
    import tickets as tickets_mod

    months, years, no_result = {}, {}, 0
    resolved = [t for t in all_tickets if t.resolved]
    for t in resolved:
        era = "sizekhaya" if t.bought >= tickets_mod.HANDOVER else "ithuba"
        inc = increments(t.game, era)
        for plus_flag, _pool_id in t.pools:
            dates = entry_draws(t, plus_flag)
            if dates is None:
                continue  # not scorable: not spend, and NOT residue either
            # Derived upward from the per-draw primitive, never by dividing the
            # entry cost -- LOTTO-0036 4.1. No remainder exists either way.
            per_draw = inc[plus_flag] * len(t.boards)
            no_result += per_draw * (t.ndraws - len(dates))
            for iso in dates:
                months.setdefault(iso[:7], [0, 0])[0] += per_draw
                years.setdefault(iso[:4], [0, 0])[0] += per_draw

    resolved_refs = {t.ref for t in resolved}
    for w in wins:
        if w["ref"] not in resolved_refs:
            continue  # INV-59, the win side of the same population
        cents = round(w["amount"] * 100)
        if w["date"][:7] in months:
            months[w["date"][:7]][1] += cents
        if w["date"][:4] in years:
            years[w["date"][:4]][1] += cents

    def row(key, kind, label, pair):
        # Always integers, never None: a bucket exists only where a draw was
        # scored, so R0.00 here always means "checked, won nothing" (4.5).
        return {"key": key, "kind": kind, "label": label,
                "spend_cents": pair[0], "won_cents": pair[1]}

    buckets = [row(k, "year", k, years[k]) for k in sorted(years, reverse=True)]
    buckets += [
        row(k, "month", f"{MONTH_NAMES[int(k[5:7]) - 1]} {k[:4]}", months[k])
        for k in sorted(months, reverse=True)
    ]
    return {"buckets": buckets, "no_result_cents": no_result}


def build_model():
    """Everything the page renders, computed here so page.py stays pure.

    Returns the DATA half of the model. built/stale/error belong to State and
    are overlaid at render time: State.fail() leaves the model untouched by
    design, so a `stale` key living inside it could never become true.
    """
    import check
    import history
    import tickets

    if not os.path.exists(DUMP):
        return {"no_dump": True, "settings": _settings_snapshot()}

    all_tickets = tickets.load(DUMP)

    # LOTTO-0002 s4.1: `ref` joins tickets[] <-> entries[] <-> wins[]. A ticket
    # whose SMS carried no `Ref:` falls back to "?", and two of those collapse
    # onto one key - won_by_entry here, resolved_refs below and period_buckets'
    # own join would each merge two tickets and render the merge as fact. The
    # spec says report it rather than render it, and nothing did.
    anonymous = [t for t in all_tickets if t.ref == "?"]
    if len(anonymous) > 1:
        raise RuntimeError(
            f"{len(anonymous)} tickets carry no Ref:, so they share the '?' "
            f"sentinel and every join keyed on ref would merge them into one. "
            f"Refusing to render the merge (LOTTO-0002 s4.1)."
        )
    wins = check.check(all_tickets)
    _lines, counts = check.uncheckable_report(all_tickets)
    today = datetime.date.today()

    entries, spend_life, spend_cmp, unresolved_cents, unresolved_n = [], 0, 0, 0, 0
    won_by_entry = {}
    for w in wins:
        won_by_entry.setdefault(
            (w["ref"], w["plus_flag"], w["pool_id"]), 0
        )
        won_by_entry[(w["ref"], w["plus_flag"], w["pool_id"])] += round(
            w["amount"] * 100
        )

    for t in all_tickets:
        era = "sizekhaya" if t.bought >= tickets.HANDOVER else "ithuba"
        inc = tier_increments(t.game, era)
        if not t.resolved:
            unresolved_n += 1
            unresolved_cents += round(t.cost * 100)
        for plus_flag, pool_id in t.pools:
            if t.resolved:
                cost_cents = inc[plus_flag] * len(t.boards) * t.ndraws
            else:
                # An UNRESOLVED ticket has exactly one pool - the fallback to
                # its printed name - and its price matched no row in the era's
                # table, so there is no increment to look up. inc[plus_flag]
                # raised KeyError for a post-handover Daily Lotto Plus, because
                # ('daily', 'sizekhaya') carries no plus_flag 1 row: the whole
                # build died and State.fail() rendered `{"what": "1"}`, blaming
                # the operator's API for a gap in a hardcoded table. What IS
                # known is the price the bank charged, and with one pool it all
                # belongs to this entry. INV-7: reported, never guessed at.
                cost_cents = round(t.cost * 100)
            spend_life += cost_cents
            ok = history.scorable(t, plus_flag)
            if ok and t.resolved:
                spend_cmp += cost_cents
            rows = history.all_draws(t.game, plus_flag)
            reason = None
            if not rows:
                reason = "no results source carries this pool"
            elif t.start.strftime("%Y-%m-%d") < rows[0]["date"]:
                reason = (
                    "predates all draw data for this pool "
                    f"(earliest {rows[0]['date']})"
                )
            covered = len(history.covered(t, plus_flag)) if ok else None
            # covered() re-runs scorable() and re-walks the pool's draw list,
            # so it is called once here rather than twice.
            entries.append(
                {
                    "ref": t.ref,
                    "game": t.game,
                    "plus_flag": plus_flag,
                    "pool_id": pool_id,
                    "cost_cents": cost_cents,
                    "scorable": ok,
                    "reason": reason,
                    # None, never 0: "0 draws checked" on an unscorable entry
                    # is the cardinal failure one column left.
                    "won_cents": won_by_entry.get((t.ref, plus_flag, pool_id), 0)
                    if ok
                    else None,
                    "draws_covered": covered,
                    "draws_remaining": (t.ndraws - covered) if ok else None,
                    # The numbers the user actually chose (LOTTO-0035). Every
                    # entry of one ticket carries the same boards - they are a
                    # property of the ticket, not of the pool - which is why
                    # this repeats across an entry's siblings rather than
                    # being looked up separately per pool.
                    "boards": [
                        {"line": b[0], "numbers": list(b[1]), "special": b[2]}
                        for b in t.boards
                    ],
                }
            )

    won_life = sum(round(w["amount"] * 100) for w in wins)
    won_live = sum(round(w["amount"] * 100) for w in wins if not w["expired"])
    resolved_refs = {t.ref for t in all_tickets if t.resolved}
    won_cmp = sum(
        round(w["amount"] * 100) for w in wins if w["ref"] in resolved_refs
    )

    out_wins = []
    for w in wins:
        d = dict(w)
        d["amount_cents"] = round(d.pop("amount") * 100)  # drop the rands key
        expires = datetime.date.fromisoformat(d["expires"])
        d["expires_in_days"] = (expires - today).days
        out_wins.append(d)

    return {
        "wins": out_wins,
        "entries": entries,
        "tickets": [
            {
                "ref": t.ref,
                "game": t.game,
                "cost_cents": round(t.cost * 100),
                "boards": len(t.boards),
                "ndraws": t.ndraws,
                "resolved": t.resolved,
                "bought": t.bought.strftime("%Y-%m-%d"),
            }
            for t in all_tickets
        ],
        "uncheckable": {
            "entries": counts["entries"],
            "uncheckable": counts["uncheckable"],
            "too_old": counts["too_old"],
            "no_pool": counts["no_pool"],
            "wholly": len(counts["wholly"]),
            "partly": len(counts["partly"]),
        },
        # LOTTO-0036. The scorable gate is written out at the call site rather
        # than inferred from an empty date list: covered() returns [] both for
        # an unscorable entry and for a scorable one whose draws have not
        # happened, and those two must not be conflated (INV-60 vs the residue).
        "periods": period_buckets(
            all_tickets,
            wins,
            lambda t, pf: (
                [d["date"] for d in history.covered(t, pf)]
                if history.scorable(t, pf)
                else None
            ),
            tier_increments,
        ),
        "spend": {
            "compared_cents": spend_cmp,
            "lifetime_cents": spend_life,
            "unresolved_cents": unresolved_cents,
            "unresolved_tickets": unresolved_n,
        },
        "won": {
            "compared_cents": won_cmp,
            "lifetime_cents": won_life,
            "unexpired_cents": won_live,
        },
        "settings": _settings_snapshot(),
    }


# ------------------------------------------------------------------- state


def _win_key(w):
    """What makes two win records the same line (LOTTO-0019 §4.3).

    `line` is a board LABEL - tickets.py builds boards as (label, numbers,
    special) - so this key holds no drawn numbers.
    """
    return (w["ref"], w["plus_flag"], w["pool_id"], w["line"], w["date"])


def _compare(previous, current):
    """-> {"new_wins": int, "new_cents": int}, or None when there is nothing to
    compare against.

    The None is the contract, not a convenience: reporting a first build's every
    win as `new` would tell a user who just opened the app that they had won
    every prize the dump has ever held. The property is the predecessor's
    EXISTENCE, never its emptiness - a no_dump predecessor genuinely held no
    wins, so "everything is new" is true of it (INV-29).
    """
    if previous is None:
        return None
    was = {_win_key(w) for w in previous.get("wins", ())}
    fresh = [w for w in current.get("wins", ()) if _win_key(w) not in was]
    return {
        "new_wins": len(fresh),
        "new_cents": sum(w["amount_cents"] for w in fresh),
    }


class State:
    """The one mutable thing in the server. All access under one lock."""

    def __init__(self):
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        self.model = None
        self.building = False
        self.built = None
        self.stale = False
        self.error = None
        # What the last COMPLETED build found that its predecessor did not, or
        # None when there was nothing to compare against (LOTTO-0019 INV-29).
        self.found = None

    def get(self):
        with self._lock:
            return (
                self.model,
                self.building,
                self.built,
                self.stale,
                self.error,
                self.found,
            )

    def begin(self):
        """True if this caller owns the build. Sets `building` before returning,
        which is what makes wait_idle() race-free."""
        with self._lock:
            if self.building:
                return False
            self.building = True
            return True

    def finish(self, model):
        with self._lock:
            # BEFORE rebinding self.model - the diff is against the outgoing one.
            self.found = _compare(self.model, model)
            self.model = model
            self.built = datetime.datetime.now().isoformat(timespec="seconds")
            self.stale = False
            self.error = None
            self.building = False
            self._idle.notify_all()

    def fail(self, exc, pools=()):
        with self._lock:
            # model UNTOUCHED - that is what INV-18 rests on.
            self.stale = True
            self.error = {"what": str(exc), "pools": list(pools)}
            # A build that raised completed no comparison. Leaving an earlier
            # refresh's summary here would outlive the build it describes.
            self.found = None
            self.building = False
            self._idle.notify_all()

    def wait_idle(self, timeout):
        with self._lock:
            if not self.building:
                return True
            return self._idle.wait_for(lambda: not self.building, timeout)


def refresh(state, build_model_fn):
    """Rebuild on a worker thread. Clears the memos FIRST.

    Clearing before is the contract: a second build in the same process makes
    zero requests and returns an identical result, so a refresh that skipped
    this would redraw the same numbers and report success. Worse, clearing two
    of the three would price new draws from the previous run's division tables.
    """
    if not state.begin():
        return False

    # SYNCHRONOUSLY, before the thread starts (LOTTO-0019 §4.2, INV-28).
    # begin() has already set `building`, and this function returns before
    # work() runs - so a reset inside work() would leave a window where
    # /status reports building:true beside the PREVIOUS build's total.
    # The three memo clears stay on the worker thread: they satisfy
    # LOTTO-0002 §4.2's "cleared before the build" either way.
    results.requests_made = 0

    def work():
        import check
        import history

        history._cache.clear()
        results._divisions_cache.clear()
        check._struct.clear()
        try:
            state.finish(build_model_fn())
        except BaseException as exc:  # noqa: BLE001 - any failure keeps the model
            # BaseException, not Exception: SystemExit, KeyboardInterrupt and
            # MemoryError are none of them, and one escaping here leaves
            # begin()'s `building` flag set for the life of the process, with
            # /status reporting a build that ended long ago. The same class of
            # escape took the SMS watcher down at login (LOTTO-0050).
            state.fail(exc)

    threading.Thread(target=work, daemon=True).start()
    return True


# -------------------------------------------------------------------- server


_settings_lock = threading.Lock()


def make_server(build_model_fn, token, port):
    """Build the server. The seam is the BUILDER, not the model: handing this a
    finished model would leave POST /refresh nothing to invoke."""
    state = State()
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    allowed_origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        # On the HANDLER, not on the server. BaseServer.timeout is read only
        # by handle_request(), and serve_forever() ignores it outright - so
        # the `server.timeout = 30` that used to carry this comment protected
        # nothing, and the hang it names (a client declaring 4000 bytes and
        # sending one) was live. StreamRequestHandler.setup() applies this one
        # to the socket, which is what LOTTO-0014 §4.1 asks for.
        timeout = 30
        # The default is "BaseHTTP/0.6 Python/3.13.14" - a version fingerprint
        # of both the server and the interpreter, which a security boundary
        # should not volunteer.
        server_version = "lotto"
        sys_version = ""

        def log_message(self, format, *args):
            """Silenced. log_request passes self.requestline - a request-derived
            string - to stderr, which under the tray is inherited and under a
            unit lands in the journal."""

        # -- helpers ---------------------------------------------------------

        def _send(self, code, body=b"", ctype=None):
            # Close the connection whenever this response did NOT consume the
            # request body. Under HTTP/1.1 keep-alive the unread bytes are
            # parsed as the NEXT request line and headers on the same socket,
            # so a rebound origin could POST a body spelling out a request
            # with a Host we allowlist, draw a 421 on the outer request, and
            # have the smuggled one served in full - token and ticket rows -
            # as the next response on a connection it can read. That defeats
            # the Host allowlist, which is the whole of §2. Every early exit
            # answers without reading (421, 404, 405, 403, 413, 400) and so
            # does the accepted POST /refresh, which has no body to consume.
            declared = self.headers.get("Content-Length")
            if declared not in (None, "", "0") and not self._body_read:
                self.close_connection = True
            if code >= 400:
                self.close_connection = True
            # NOT a `Connection: close` header, deliberately. Announcing the
            # close would be better HTTP - a client reusing the socket sees a
            # reset rather than an ordinary end - but §4.1 says "No response
            # carries any header outside its row", and INV-14's case asserts
            # the header-name set is EXACTLY the set for that response shape,
            # which is what catches a reflected header. Adding one reddened
            # that case, and re-fixturing a security assertion to fit a
            # cosmetic improvement is the wrong trade. Closing the socket is
            # what stops the desync; the announcement is not needed for it.
            # Whether §4.1's rule is meant to reach framing headers is a
            # question for the contract, not something to decide here.
            self.send_response(code)
            if ctype:
                self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in SECURITY_HEADERS:
                self.send_header(k, v)
            self.end_headers()
            if body and self.command != "HEAD":
                self.wfile.write(body)

        def _host_ok(self):
            return (self.headers.get("Host") or "").lower() in allowed_hosts

        def _origin_ok(self):
            origin = self.headers.get("Origin")
            # Absent is allowed: a top-level navigation carries none, and the
            # tray's own urllib POST sends none. The token covers that case.
            return origin is None or origin in allowed_origins

        def _token_ok(self):
            got = self.headers.get("X-Lotto-Token") or ""
            # compare_digest refuses a str carrying any code point above
            # U+007F, and http.client decodes headers as iso-8859-1 - so the
            # bytes 0x80-0xFF, which Fetch permits in a header value, reach
            # here as exactly such a string. It raised TypeError: the client
            # got no response at all, and a traceback reached the stderr
            # log_message() is silenced to keep clean.
            if not got.isascii():
                return False
            return secrets.compare_digest(got, token)

        def _read_body(self):
            self._body_read = True
            raw = self.headers.get("Content-Length")
            try:
                n = int(raw)
            except (TypeError, ValueError):
                return None, 400
            if n < 0:
                return None, 400
            if n > MAX_BODY:
                return None, 413
            data = self.rfile.read(n) if n else b"{}"
            try:
                obj = json.loads(data or b"{}")
            except ValueError:
                return None, 400
            if not isinstance(obj, dict):
                return None, 400
            for k, v in obj.items():
                if k not in BODY_KEYS or not isinstance(v, bool):
                    return None, 400
            return obj, 200

        # Set per request, before any handler runs, so _send() can tell a
        # response that consumed the body from one that did not.
        _body_read = False

        def _path(self):
            return self.path.split("?", 1)[0]

        def _route(self, method):
            """Fixed order; the first failure answers and no later check runs.
            Host first, or a rebound origin learns which paths exist."""
            # Reset per REQUEST, not per connection: handle() loops
            # handle_one_request() on one instance, so a class attribute left
            # True by an earlier POST would tell _send() a later request's
            # body had been consumed when it had not.
            self._body_read = False
            if not self._host_ok():
                self._send(421)
                return None
            path = self._path()
            if path not in ALLOW:
                self._send(404)
                return None
            if ALLOW[path] != method:
                self.close_connection = True
                self.send_response(405)
                self.send_header("Allow", ALLOW[path])  # fixed table, not the request
                self.send_header("Content-Length", "0")
                for k, v in SECURITY_HEADERS:
                    self.send_header(k, v)
                self.end_headers()
                return None
            return path

        # -- routes ----------------------------------------------------------

        def do_GET(self):
            path = self._route("GET")
            if path is None:
                return
            model, building, built, stale, error, found = state.get()
            requests = results.requests_made
            if path == "/status":
                body = json.dumps(
                    {
                        "building": building,
                        "built": built,
                        "stale": stale,
                        # LOTTO-0019 §4.2. `requests` is the build in flight (or
                        # the last one); `found` is the last COMPLETED build.
                        "requests": requests,
                        "found": found,
                    }
                ).encode()
                self._send(200, body, "application/json")
                return
            view = dict(model or {})
            view.update(
                {
                    "built": built,
                    "stale": stale,
                    "error": error,
                    "building": building,
                    # The HTML view too, not just /status: the opening-build page
                    # renders when model is None, so a key living only in the
                    # model could never reach it. `found` deliberately does NOT
                    # join it - nothing in page.py renders it (§4.2).
                    "requests": requests,
                }
            )
            if model is None and not error and not building:
                view["no_build"] = True
            # `view = dict(model or {})` carries no settings when there is no
            # model, which is every empty-page state except no_dump (which
            # builds its own). Without this both switches render UNCHECKED
            # whatever is actually stored - a page reporting a state that is
            # not the state, on the one page whose entire job is not doing
            # that. Read only when absent; a built model already carries it.
            if "settings" not in view:
                view["settings"] = _settings_snapshot()
            try:
                body = page.render(view, token).encode()
            except Exception as exc:  # noqa: BLE001
                # do_POST guards its one raising call and this had none, so a
                # renderer failure reached ThreadingHTTPServer.handle_error and
                # the client got a reset connection rather than a response. The
                # 500 still carries SECURITY_HEADERS (INV-12). Only the
                # exception's TYPE is printed: log_message() is silenced
                # because request-derived text must not reach the journal, and
                # a rendering exception can quote model data.
                print(f"render failed: {type(exc).__name__}", file=sys.stderr)
                self._send(500)
                return
            self._send(200, body, "text/html; charset=utf-8")

        # Every other method routes through the same ladder. Without these,
        # BaseHTTPRequestHandler answers 501 from handle_one_request() before
        # a line of this class runs: no Host check, and send_error() emits
        # none of SECURITY_HEADERS - breaking INV-12's "every response,
        # including that 421" and INV-21's no-store clause. HEAD is
        # CORS-safelisted, so a hostile page reached that path with a plain
        # fetch(). _route() gives each of these a 421, a 404, or a 405 with
        # the Allow header from the fixed table, which is what §4.1 prescribes.
        # Residue, stated rather than hidden: a method outside this list still
        # reaches the stdlib 501. fetch() cannot send CONNECT, TRACE or TRACK,
        # so nothing a page can do gets there.
        def do_HEAD(self):
            self._route("HEAD")

        def do_PUT(self):
            self._route("PUT")

        def do_DELETE(self):
            self._route("DELETE")

        def do_OPTIONS(self):
            self._route("OPTIONS")

        def do_PATCH(self):
            self._route("PATCH")

        def do_POST(self):
            path = self._route("POST")
            if path is None:
                return
            if not self._token_ok() or not self._origin_ok():
                self._send(403)
                return
            if path == "/refresh":
                self._send(202 if refresh(state, build_model_fn) else 409)
                return
            changes, code = self._read_body()
            if changes is None:
                self._send(code)
                return
            try:
                now = write_settings(changes)
            except OSError:
                self._send(500)
                return
            self._send(200, json.dumps(now).encode(), "application/json")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    # The read timeout lives on Handler (see its `timeout`), because
    # serve_forever() ignores BaseServer.timeout.
    return server, state


def resolve_port(env=None):
    """$PORT, then $LOTTO_PORT, then 4322 - and a bad value exits before the bind.

    $PORT is the knob an external process manager sets, so it wins; $LOTTO_PORT
    keeps working exactly as it did, and is what supervise.py writes into the
    child (LOTTO-0013 §4.5). Unset and empty are not values - they mean "no
    preference" and fall through to the next source.

    **A value that was meant as a port and cannot be one is fatal**, for either
    variable. Falling back would put the page on a port the caller was never
    told about: a manager that asked for 80 and silently got 4322 has been lied
    to, and the user who typed the variable one command ago is not looking at
    4322 either. That is why this exits rather than warning, and why the message
    names the value it rejected (LOTTO-0002 §6).

    **supervise.py::_port_or_default() reads the same two variables in the same
    order and FALLS BACK instead of exiting. Do not "unify" the two.** This one
    is MACHINE-facing - an external manager must never be silently handed a port
    other than the one it asked for. That one is HUMAN-facing, where exiting
    means a tray that vanishes with no window and no terminal to explain itself,
    so it falls back and raises a notification instead. Two behaviours for one
    input, on purpose; that docstring carries the other half of the reasoning.
    """
    env = os.environ if env is None else env
    for name in ("PORT", "LOTTO_PORT"):
        raw = env.get(name)
        if not raw:
            continue
        try:
            port = int(raw)
        except ValueError:
            raise SystemExit(
                f"{name}={raw!r} is not a number — expected {MIN_PORT}-{MAX_PORT}"
            )
        if not MIN_PORT <= port <= MAX_PORT:
            raise SystemExit(f"{name}={port} is outside {MIN_PORT}-{MAX_PORT}")
        return port
    return DEFAULT_PORT


def main():
    port = resolve_port()
    token = os.environ.get("LOTTO_TOKEN") or secrets.token_urlsafe(32)
    no_build = bool(os.environ.get("LOTTO_NO_BUILD"))
    try:
        server, state = make_server(build_model, token, port)
    except OSError as exc:
        raise SystemExit(f"cannot bind 127.0.0.1:{port} — {exc}")
    # Bind before the first build, not after: the server answers immediately
    # with a "building" page rather than leaving the browser to time out.
    if not no_build:
        refresh(state, build_model)
    print(f"serving http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
