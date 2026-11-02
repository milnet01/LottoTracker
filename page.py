"""Render the model dict to one HTML string. Pure: no I/O, no imports of
check/history/results/tickets, no network, no disk (LOTTO-0002 §4.1).

Everything this renders is already in the model. That is load-bearing rather
than tidy: it is what lets tools/verify_page.py render the whole page against a
fixture with no socket and no archive_results.json, and it is why the
derivations LOTTO-0002 §4.5 and §4.6 describe happen in serve.py's builder.

The cardinal rule this file must not lose (CLAUDE.md, LOTTO-0002 INV-15): an
entry nothing can score is UNCHECKABLE, not a loss. It never renders as a blank
cell, a dash, a zero, or an absence from the table.
"""

import html
import json
from datetime import date

TITLE = "Lotto Tracker"  # constant: INV-21 forbids ticket data in the title

# INV-78: on every page state. The site and the trailers carry the same words.
DISCLAIMER = (
    "LottoTracker is an independent app. It is not affiliated with or endorsed "
    "by the South African National Lottery, its operator, or Standard Bank. "
    "Always check results and claim prizes through the official lottery before "
    "relying on what the app shows."
)


# The names the reader knows, in place of the (game, plus_flag) key. Current names:
# the June 2026 rebrand renamed Lotto Plus 2 and PowerBall Plus (tickets.py).
# Not history.POOL_NAMES, which matches the API's wire format and may not change
# when a sentence should. An unknown pool shows its key rather than a guess.
GAME_NAMES = {"lotto": "Lotto", "powerball": "PowerBall", "daily": "Daily Lotto"}
POOL_NAMES = {
    ("lotto", 0): "Lotto",
    ("lotto", 1): "Lotto Plus 1",
    ("lotto", 2): "Lotto 5 Max",
    ("powerball", 0): "PowerBall",
    ("powerball", 1): "PowerBall XTRA",
    ("daily", 0): "Daily Lotto",
    ("daily", 1): "Daily Lotto Plus",
}


def _pool_name(game, plus_flag):
    return POOL_NAMES.get((game, plus_flag), f"{game}/{plus_flag}")


def _e(s):
    return html.escape(str(s), quote=True)


def _js(value):
    """A Python value as a JS literal, safe inside a <script> block.

    json.dumps escapes for a JSON parser, not for an HTML script context: `<`
    and `/` come through bare, so a value spelling `</script>` would end the
    block early. Neither current writer can produce one - the token is
    secrets.token_urlsafe and `built` is an ISO timestamp - which is what keeps
    this theoretical. It is one new writer away from live.
    """
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _rands(cents):
    """Cents -> 'R1,234.50'. Only ever called with an integer (LOTTO-0002 §4.1)."""
    return f"R{cents / 100:,.2f}"


def _money_cell(won_cents):
    """The one cell INV-15 asserts against.

    `None` means nothing could score this entry; `0` means it was scored and did
    not win. They must not render the same, and `None` must not render as any of
    the empty-looking strings INV-15 forbids.
    """
    if won_cents is None:
        return '<td class="notcheckable money">not checkable</td>'
    # A prize stands out and a checked zero steps back, in weight as well as in
    # colour. Both still print their figure, so R0.00 cannot read as no data.
    look = "money won" if won_cents else "money nil"
    return f'<td class="{look}">{_e(_rands(won_cents))}</td>'


def _draws_cell(value):
    """draws_covered / draws_remaining are None for an unscorable entry.

    Rendering 0 here would be the cardinal error one column left: "0 draws
    checked" on a 2019 ticket reads as a result rather than as an absence.
    """
    if value is None:
        return '<td class="notcheckable">unknown &mdash; not checkable</td>'
    return f"<td>{_e(value)}</td>"


def _balls(numbers, special=None, hits=None, special_hit=False):
    """One set of numbers as markup, main numbers then any special (LOTTO-0035).

    The cardinal rule reaches here too: an absent set is said in words, never
    rendered as an empty cell. An empty list is absence, not "no numbers" - a
    board always has numbers, so nothing to show means nothing was known.

    `hits` is None except on a win, where a ball outside it is drawn hollow
    (INV-97). A ball on any other row is never marked either way.
    """
    def look(hit):
        return "" if hits is None or hit else " miss"

    if not numbers:
        return '<span class="notcheckable">not recorded</span>'
    out = " ".join(
        f'<span class="ball{look(hits and n in hits)}">{_e(n)}</span>' for n in numbers
    )
    if special is not None:
        out += f' <span class="ball special{look(special_hit)}">{_e(special)}</span>'
    return out


def _numbers_cell(numbers, special=None):
    return f"<td class=\"nums\">{_balls(numbers, special)}</td>"


def _win_number_cells(w):
    """The chosen and drawn cells of one win, with what matched filled (INV-97).

    The same rule as check.py::match(), which this file may not import. A PowerBall
    meets only a PowerBall, so a main number equal to it is no match, while a Lotto
    bonus ball counts against every number on the board. Daily Lotto has neither.
    With either side unknown nothing is marked: a hollow ball says "did not match",
    and that cannot be said against numbers nobody has.
    """
    mine, drawn = w.get("numbers") or [], w.get("drawn_main") or []
    special, drawn_special = w.get("special"), w.get("drawn_special")
    if not mine or not drawn:
        return _numbers_cell(mine, special) + _numbers_cell(drawn, drawn_special)
    game = w.get("game")
    powerball_hit = game == "powerball" and special == drawn_special
    bonus_hit = game == "lotto" and drawn_special in mine
    my_hits = set(drawn) | ({drawn_special} if game == "lotto" else set())
    return (
        f'<td class="nums">{_balls(mine, special, my_hits, powerball_hit)}</td>'
        f'<td class="nums">'
        f"{_balls(drawn, drawn_special, set(mine), powerball_hit or bonus_hit)}</td>"
    )


def _boards_cell(boards):
    """Every board on a ticket, one per line, labelled when there is >1."""
    if not boards:
        return '<td class="notcheckable">not recorded</td>'
    if len(boards) == 1:
        b = boards[0]
        return _numbers_cell(b.get("numbers"), b.get("special"))
    parts = [
        f'<div><span class="muted">{_e(b.get("line"))}</span> '
        + _balls(b.get("numbers"), b.get("special"))
        + "</div>"
        for b in boards
    ]
    return f'<td class="nums">{"".join(parts)}</td>'


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _long_date(iso):
    """9 May 2026, from 2026-05-09. Anything else comes back as it was."""
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def _date_cell(iso, after="", cls=""):
    """A date for a person, with the form that sorts in data-sort (INV-100). The
    script orders on the attribute, so the words can change freely."""
    attr = f' class="{cls}"' if cls else ""
    if not iso:
        return f"<td{attr}>{_e(iso)}{after}</td>"
    return f'<td{attr} data-sort="{_e(iso)}">{_e(_long_date(iso))}{after}</td>'


def _bought_cell(entry):
    """When the ticket was bought. Absent is said in words, like any other gap."""
    bought = entry.get("bought")
    if not bought:
        return '<td class="notcheckable">not recorded</td>'
    return _date_cell(bought)


def _newest_first(items, date_key):
    """Latest first, anything undated last. Stable, so one ticket's pools stay
    together in their own order (LOTTO-0002 INV-85)."""
    return sorted(items, key=lambda i: i.get(date_key) or "", reverse=True)


# What each kind of column offers. The first word is the column's natural first
# click: newest and highest read downwards, names read A to Z.
SORT_WORDS = {
    "date": (("desc", "newest first"), ("asc", "oldest first")),
    "num": (("desc", "highest first"), ("asc", "lowest first")),
    "text": (("asc", "A to Z"), ("desc", "Z to A")),
}


MONEY_HEADINGS = {"Amount", "Cost", "Won"}


def _game_cell(game, plus_flag):
    """A game's name with a dot in its colour, read from the row's data-game."""
    return f'<td class="game"><span class="pip"></span>{_e(_pool_name(game, plus_flag))}</td>'


def _sorted_table(table_id, columns, rows, default_col, default_dir="desc"):
    """A table with sortable headings and the same choices in a dropdown.

    The dropdown is not a duplicate: a phone shows each row as a card, with no
    heading row to click (LOTTO-0002 INV-85, INV-86). `columns` is a list of
    (heading, kind), where a kind of None means the column does not sort. `rows`
    must already be in the default order: this names that order, it does not
    apply it, so the page reads correctly with no script running.
    """
    heads, options = [], []
    for i, (heading, kind) in enumerate(columns):
        if kind is None:
            heads.append(f"<th>{_e(heading)}</th>")
            continue
        current = ""
        if i == default_col:
            word = "descending" if default_dir == "desc" else "ascending"
            current = f' aria-sort="{word}"'
        # Right-aligned like the figures under them (LOTTO-0007 (w)).
        money = ' class="money"' if heading in MONEY_HEADINGS else ""
        heads.append(
            f'<th data-kind="{kind}"{money}{current}><button type="button" '
            f'class="sorthead">{_e(heading)}</button></th>'
        )
        for direction, words in SORT_WORDS[kind]:
            chosen = i == default_col and direction == default_dir
            options.append(
                f'<option value="{i}:{direction}"{" selected" if chosen else ""}>'
                f"{_e(heading)}: {words}</option>"
            )
    return (
        f'<div class="row"><label>Sort by <select class="sortby" '
        f'data-table="{table_id}">{"".join(options)}</select></label></div>'
        f'<div class="tablewrap cards"><table id="{table_id}"><thead><tr>'
        f'{"".join(heads)}</tr></thead><tbody>{rows}</tbody></table></div>'
    )


def _notice(model):
    """The three states in which the page shows no ticket data (LOTTO-0002 §6).

    Each is correct only because it says why. The reason is never "you have no
    wins", so an empty page without one of these is the cardinal failure.
    """
    err = model.get("error")
    if err:
        pools = ", ".join(err.get("pools") or []) or "all pools"
        return (
            '<div class="notice bad"><strong>Results unavailable.</strong> '
            f"The results source could not be reached ({_e(err['what'])}), so "
            f"<strong>no ticket could be checked</strong> — {_e(pools)}. "
            "This is not a statement that you have won nothing: nothing was "
            "checked at all. Press Refresh to try again.</div>"
        )
    if model.get("no_build"):
        return (
            '<div class="notice"><strong>No build was performed</strong> '
            "(LOTTO_NO_BUILD is set). No ticket has been checked, and nothing "
            "below is a result.</div>"
        )
    if model.get("no_dump"):
        return (
            '<div class="notice bad"><strong>No messages found.</strong> '
            "lotto_sms_raw.txt is missing, so there are no tickets to check — "
            "this is not zero wins. Run <code>python3 find_lotto_sms.py</code> "
            "to pull them from the phone.</div>"
        )
    if model.get("stale"):
        return (
            '<div class="notice"><strong>These figures are from an earlier '
            "fetch.</strong> The last refresh failed, so the previous results "
            "are still shown rather than being replaced by nothing.</div>"
        )
    return ""


def _sms_quiet_section(model):
    """Say the phone has gone quiet, and what that costs (LOTTO-0034 INV-84).

    The page may name the date, where the tray's notice may not: this page
    already shows every ticket, and it is not logged or synced off the machine.
    """
    quiet = model.get("sms_quiet")
    if not quiet:
        return ""
    if quiet["days"] is None:
        lead = "<strong>No lottery SMS has been read yet.</strong> "
    else:
        lead = (
            f"<strong>No lottery SMS for {_count(quiet['days'], 'day', 'days')}."
            f"</strong> The newest one here is from {_e(quiet['newest'])}. "
        )
    return (
        f'<div class="notice bad">{lead}If you have bought a ticket since then, '
        "it is not on this page and the app cannot warn you when it runs out. "
        "Check that your phone is connected through KDE Connect and that the "
        "Lotto Tracker tray icon is running.</div>"
    )


def _senders_section(model):
    """Records from a sender the bank is not known to use (LOTTO-0062 s4.4).

    Rendered only when there is one: a heading over an empty list would read
    as an alarm with nothing behind it (INV-75). Never in a notification -
    that rule is CLAUDE.md's, and this is the page.
    """
    flagged = model.get("unknown_senders") or []
    if not flagged:
        return ""
    rows = "".join(
        f"<li>{_e(f['received'])} — {_e(f['kind'])} — {_e(f['ref'])} — "
        f"from <code>{_e(f['sender'])}</code></li>"
        for f in flagged
    )
    return (
        '<div class="notice bad"><strong>From a sender not seen before</strong>'
        f"<ul>{rows}</ul>These are still counted on this page. If one is the "
        "bank, it has a new sender name; if not, the message was not from the "
        "bank.</div>"
    )


def _count(n, one, many):
    """Say "1 entry" and "2 entries"; the page said "1 entries" (LOTTO-0007 (w))."""
    return f"{n:,} {one if n == 1 else many}"


def _uncheckable_banner(u):
    """Renders above the wins, never below, and is not collapsible (§4.5)."""
    if not u or not u.get("uncheckable"):
        return ""
    bits = []
    if u.get("odd_board"):
        n = u["odd_board"]
        bits.append(f"{n:,} {'is' if n == 1 else 'are'} on a ticket whose board "
                    "holds more numbers than one line of its game")
    if u.get("too_old"):
        n = u["too_old"]
        bits.append(f"{n:,} predate{'s' if n == 1 else ''} all draw data "
                    "for their pool")
    if u.get("no_pool"):
        n = u["no_pool"]
        bits.append(f"{n:,} {'is' if n == 1 else 'are'} in a pool no results "
                    "source carries")
    detail = "; ".join(bits)
    return (
        # "standing" because it never clears: warning colours are kept for what
        # needs doing, or the real warnings stop being seen.
        '<div class="notice standing"><strong>'
        f"{u['uncheckable']:,} of {_count(u['entries'], 'entry', 'entries')} "
        "cannot be checked."
        # Worded to hold for all three reasons: "nothing exists to score them
        # against" is false of an oversized board whose pool has draws (INV-68).
        "</strong> They are <strong>not losses</strong> &mdash; none of them "
        f"could be scored. {_e(detail)}. This affects "
        + (
            # "0 tickets wholly and 1 partly" says nothing with its first half.
            f"{_count(u.get('wholly', 0), 'ticket', 'tickets')} wholly and "
            f"{u.get('partly', 0):,} partly"
            if u.get("wholly")
            else f"{_count(u.get('partly', 0), 'ticket', 'tickets')} partly"
        )
        + "; a partly-checkable ticket is still scored on its other pools."
        "</div>"
    )


def _payment_cell(w):
    """The win's payment state in words (LOTTO-0002 s4.5 item 1, INV-70).

    A win with no `payment` key reads as unknown: missing data never reads as
    paid, and a deadline with no state beside it would hide that it is missing.
    """
    state = w.get("payment", "unknown")
    if state == "partly paid":
        p, c = w.get("ref_paid_cents"), w.get("ref_computed_cents")
        if p is not None and c is not None:
            return (f'<td class="wrap">partly paid — the bank paid {_e(_rands(p))} of '
                    f"{_e(_rands(c))} on this ticket</td>")
        return "<td>partly paid</td>"
    if state == "unpaid":
        return "<td>unpaid</td>"
    return "<td>payment unknown</td>"


def _waiting(wins):
    """The wins section 1 lists (LOTTO-0011, INV-70).

    A win the bank paid carries no deadline anywhere on the page. Every other
    unexpired win is here, "unknown" included - which is what keeps the
    empty-state sentence true when no payout data parsed at all.
    """
    return [w for w in wins
            if not w.get("expired") and w.get("payment", "unknown") != "paid"]


# The cells a win shows whatever its payment state. "Draw" is the default sort.
WIN_COLUMNS = [("Game", "text"), ("Your numbers", None), ("Drawn", None),
               ("Division", "text"), ("Matched", "text"), ("Draw", "date"),
               ("Amount", "num")]


def _win_cells(w):
    return (
        _game_cell(w["game"], w["plus_flag"])
        + _win_number_cells(w)
        + f'<td>{_e(w.get("division"))}</td><td>{_e(w.get("matched"))}</td>'
        + _date_cell(w.get("date"))
        + f'<td class="money">{_e(_rands(w["amount_cents"]))}'
        + (' <span class="muted">estimate</span>' if w.get("estimate") else "")
        + "</td>"
    )


def _ball_key(model):
    """What a hollow ball means, said once, and only where one can appear (INV-97)."""
    if not model.get("wins"):
        return ""
    return (
        '<p class="ballkey"><span class="ball" aria-hidden="true"></span> matched '
        '<span class="ball miss" aria-hidden="true"></span> did not match</p>'
    )


def _wins_section(model):
    live = _waiting(model.get("wins", []))
    # Latest draw first, the user's call of 2026-11-02 (INV-85). A deadline
    # within 30 days stays marked, and the Expires heading sorts by it.
    live = _newest_first(live, "date")
    if not live:
        body = (
            '<p class="muted">No unexpired win is waiting on the bank. This '
            "counts only the entries that could be checked &mdash; see the "
            "banner above.</p>"
        )
    else:
        rows = []
        for w in live:
            d = w.get("expires_in_days")
            cls = "soon" if d is not None and d <= 30 else ""
            if d == 0:
                cls = "today"
                expires = f'<td class="stack" data-sort="{_e(w.get("expires"))}">today</td>'
            elif d is not None and d < 0:
                # Past its claim date. Not "today" - and s4.5 requires every
                # win to name its date, which the old `d <= 0` branch threw
                # away along with the distinction.
                cls = "today"
                expires = _date_cell(
                    w.get("expires"), ' <span class="muted">(claim date passed)</span>', "stack")
            else:
                expires = _date_cell(
                    w.get("expires"),
                    "" if d is None
                    else f' <span class="muted">({_count(d, "day", "days")})</span>',
                    "stack")
            rows.append(
                f'<tr class="{cls}" data-game="{_e(w["game"])}">'
                + _win_cells(w)
                + _payment_cell(w)
                + expires
                + "</tr>"
            )
        body = _sorted_table(
            "wins",
            WIN_COLUMNS + [("Payment", "text"), ("Expires", "date")],
            "".join(rows),
            5,
        )
    return f"<section><h2>Not yet paid</h2>{body}</section>"


def _paid_section(model):
    """Wins the bank has paid: their numbers appear nowhere else on the page.

    No Expires column: a paid win carries no deadline anywhere (INV-70, INV-94).
    """
    paid = [w for w in model.get("wins", []) if w.get("payment") == "paid"]
    if not paid:
        body = (
            '<p class="muted">No win here has a matching payment in the bank\'s '
            "messages.</p>"
        )
    else:
        body = _sorted_table(
            "paid",
            WIN_COLUMNS,
            "".join(
                f'<tr data-game="{_e(w["game"])}">{_win_cells(w)}</tr>'
                for w in _newest_first(paid, "date")
            ),
            5,
        )
    return f"<section><h2>Paid by the bank</h2>{body}</section>"


def _outstanding_section(model):
    """Deliberately not called "Live tickets".

    A 2019 ticket has no draws still to come, and filing unscorable entries
    under a heading that asserts they do would be the cardinal error wearing the
    section title (LOTTO-0002 §4.5).
    """
    coming, unchecked = [], []
    for e in model.get("entries", []):
        if not e.get("scorable"):
            unchecked.append(e)
        elif (e.get("draws_remaining") or 0) > 0:
            coming.append(e)

    def rows(entries, remaining_col):
        out = []
        for e in _newest_first(entries, "bought"):
            out.append(
                f'<tr data-game="{_e(e["game"])}"><td class="ref">{_e(e["ref"])}</td>'
                + _bought_cell(e)
                + _game_cell(e["game"], e["plus_flag"])
                + _boards_cell(e.get("boards"))
                + (
                    f"<td>{e['draws_remaining']}</td>"
                    if remaining_col
                    else f'<td class="notcheckable wrap">{_e(e.get("reason") or "not checkable")}</td>'
                )
                + "</tr>"
            )
        return "".join(out)

    parts = []
    if coming:
        parts.append(
            "<h3>Draws still to come</h3>"
            + _sorted_table(
                "coming",
                [("Ticket", "text"), ("Bought", "date"), ("Game", "text"),
                 ("Your numbers", None), ("Draws remaining", "num")],
                rows(coming, True),
                1,
            )
        )
    if unchecked:
        parts.append(
            f"<h3>Not checkable ({_count(len(unchecked), 'entry', 'entries')})</h3>"
            '<p class="muted">Draws remaining is unknown for these: there is '
            "nothing to measure a window against. They are not losses.</p>"
            + _sorted_table(
                "unchecked",
                [("Ticket", "text"), ("Bought", "date"), ("Game", "text"),
                 ("Your numbers", None), ("Why not", "text")],
                rows(unchecked, False),
                1,
            )
        )
    if not parts:
        parts.append('<p class="muted">Nothing outstanding.</p>')
    return "<section><h2>Still outstanding</h2>" + "".join(parts) + "</section>"


def _entries_section(model):
    """Every entry, filterable client-side only (INV-21: the URL never changes)."""
    rows = []
    for e in _newest_first(model.get("entries", []), "bought"):
        pool = f"{e['game']}/{e['plus_flag']}"
        rows.append(
            f'<tr data-game="{_e(e["game"])}" data-pool="{_e(pool)}">'
            f'<td class="ref">{_e(e["ref"])}</td>'
            + _bought_cell(e)
            + _game_cell(e["game"], e["plus_flag"])
            + f'<td class="money">{_e(_rands(e["cost_cents"]))}</td>'
            + _draws_cell(e.get("draws_covered"))
            + _money_cell(e.get("won_cents"))
            + f'<td class="notcheckable wrap">{_e(e.get("reason") or "")}</td></tr>'
        )
    games = sorted({e["game"] for e in model.get("entries", [])})
    opts = "".join(
        f'<option value="{_e(g)}">{_e(GAME_NAMES.get(g, g))}</option>' for g in games
    )
    # §4.5 item 3 promises the table is filterable by game AND pool. Every row
    # has carried data-pool since it was written, with nothing reading it -
    # the attribute looked wired and had no consumer at all. Same client-side
    # shape as the game filter, so INV-21 is untouched: no query parameter, no
    # fragment, no history entry, only visibility on rows already present.
    pools = sorted({(e["game"], e["plus_flag"]) for e in model.get("entries", [])})
    popts = "".join(
        f'<option value="{_e(g)}/{_e(f)}">{_e(_pool_name(g, f))}</option>'
        for g, f in pools
    )
    return (
        '<section><h2>Every entry</h2><div class="row">'
        '<label>Filter by game <select id="gamefilter">'
        f'<option value="">all</option>{opts}</select></label> '
        '<label>Exact game <select id="poolfilter">'
        f'<option value="">all</option>{popts}</select></label></div>'
        + _sorted_table(
            "entries",
            [("Ticket", "text"), ("Bought", "date"), ("Game", "text"),
             ("Cost", "num"), ("Draws checked", "num"), ("Won", "num"),
             ("Why not", "text")],
            "".join(rows),
            1,
        )
        + "</section>"
    )


def _when(row):
    """A ticket's last draw, said the way a person would."""
    days = row["final_in_days"]
    if days == 0:
        return "Last draw today"
    if days == 1:
        return f'Last draw tomorrow, {_e(row["final"])}'
    return f'Last draw {_e(row["final"])}'


def _buy_headline(view):
    """The one sentence the page exists to say (LOTTO-0002 INV-93)."""
    soon = [r for r in view["running"] if r["buy_soon"]]
    still = {r["game"] for r in view["running"]}
    gone = [g for g in view["ran_out"] if g["game"] not in still]
    if len(gone) == 1:
        g = gone[0]
        return f'Buy {_e(g["name"])} now. Your last ticket ended {_e(g["final"])}.'
    if gone:
        names = " and ".join(_e(g["name"]) for g in gone)
        return f"Buy {names} now. Your last tickets have ended."
    if soon:
        r = soon[0]
        return f'Buy {_e(r["name"])} soon. {_when(r)}.'
    if view["running"]:
        r = next((x for x in view["running"] if not x["followed"]), view["running"][0])
        return f'Nothing to buy yet. {_e(r["name"])} runs out next: {_e(r["final"])}.'
    return "No ticket on this page has draws still to come."


def _draw_balls(row):
    """One ball per draw paid for: hollow once it has happened, filled still to come.

    Hidden from a screen reader, because the sentence beside it says the same.
    """
    used = row["ndraws"] - row["left"]
    return (
        '<div class="burn" aria-hidden="true">'
        + "".join(f'<span class="ball used" style="--i:{i}"></span>' for i in range(used))
        + '<span class="ball"></span>' * row["left"]
        + "</div>"
    )


def _run_row(row):
    tag = ""
    if row["buy_soon"]:
        tag = ' <span class="tag">Buy soon</span>'
    elif row["followed"]:
        tag = ' <span class="muted">next ticket already bought</span>'
    left = _count(row["left"], "draw", "draws")
    return (
        f'<li class="run" data-game="{_e(row["game"])}">'
        f'<div class="runname">{_e(row["name"])}{tag}</div>'
        + _draw_balls(row)
        + f'<div class="runfacts"><strong>{left} left</strong> of {row["ndraws"]}. '
        f"{_when(row)}.</div></li>"
    )


def _go(tab, words):
    """A button to another tab. No link: a fragment would touch the URL (INV-89)."""
    return f'<button type="button" class="golink" data-goto="{tab}">{_e(words)}</button>'


def _glance_wins(model):
    waiting = _waiting(model.get("wins", []))
    if not waiting:
        said = (
            "No unexpired win is waiting on the bank. This counts only the "
            "entries that could be checked."
        )
    else:
        soonest = min(w.get("expires") or "9999" for w in waiting)
        said = (
            f"<strong>{_count(len(waiting), 'win', 'wins')}</strong> waiting on "
            f"the bank. The first claim deadline is {_e(_long_date(soonest))}."
        )
    return (
        f'<div class="glance"><h3>Prizes</h3><p>{said}</p>'
        f'{_go("wins", "See your wins")}</div>'
    )


def _glance_money(model):
    """The newest year, verbatim from serve.py. No bucket means no figure at all:
    R0.00 here would say "checked, won nothing" of a year nobody checked."""
    buckets = (model.get("periods") or {}).get("buckets") or []
    year = next((b for b in buckets if b["kind"] == "year"), None)
    if year is None:
        said = "No draw has been checked against a result yet, so there is nothing to compare."
    else:
        said = (
            f'Draws checked in {_e(year["label"])}: spent '
            f'<strong>{_e(_rands(year["spend_cents"]))}</strong>, won '
            f'<strong>{_e(_rands(year["won_cents"]))}</strong>.'
        )
    return (
        f'<div class="glance"><h3>Money</h3><p>{said}</p>'
        f'{_go("spending", "See spending by period")}</div>'
    )


def _overview_section(model):
    """What the page is for, in order of what the reader must act on (INV-93)."""
    view = model.get("running")
    if view is None:
        # Not "nothing is running": the calendar was never asked.
        buy = (
            '<h2 class="headline">Not known when your tickets run out.</h2>'
            '<p class="notcheckable">The tickets could not be read against the draw '
            "calendar.</p>"
        )
    else:
        rows = "".join(_run_row(r) for r in view["running"])
        lost = ""
        if view["unknown"]:
            n = view["unknown"]
            lost = (
                f'<p class="notcheckable">{_count(n, "ticket", "tickets")} could not '
                "be placed on the draw calendar, so "
                f'{"it is" if n == 1 else "they are"} not listed here.</p>'
            )
        empty = ""
        if not rows:
            empty = (
                '<p class="muted">If you have bought one since, its SMS has not '
                "reached this app yet.</p>"
            )
        buy = (
            f'<h2 class="headline">{_buy_headline(view)}</h2>{empty}'
            + (f'<ul class="runs">{rows}</ul>' if rows else "")
            + lost
        )
    return (
        f'<section class="overview">{buy}<div class="glances">'
        f"{_glance_wins(model)}{_glance_money(model)}</div></section>"
    )


def _spend_section(model):
    s, w = model.get("spend", {}), model.get("won", {})
    unresolved = ""
    if s.get("unresolved_tickets"):
        unresolved = (
            f"<tr><td>Tickets whose price matches no known board price</td>"
            f'<td class="money">{_e(_rands(s.get("unresolved_cents", 0)))}</td>'
            f'<td class="muted">{s["unresolved_tickets"]:,} tickets &mdash; '
            "reported, not guessed at; in neither side of the comparison</td></tr>"
        )
    return (
        "<section><h2>Spend against winnings</h2>"
        '<p class="muted">The comparison is drawn over the entries that could '
        "actually be checked, on resolved tickets only. Comparing lifetime "
        "spend against it would turn every unscorable entry into a loss.</p>"
        "<table><tbody>"
        f'<tr><td>Spent on entries that could be scored</td><td class="money">'
        f'{_e(_rands(s.get("compared_cents", 0)))}</td><td class="muted">the comparison</td></tr>'
        f'<tr><td>Won on those same entries</td><td class="money">'
        f'{_e(_rands(w.get("compared_cents", 0)))}</td><td class="muted">the comparison</td></tr>'
        f'<tr><td>Lifetime spend, every entry</td><td class="money">'
        f'{_e(_rands(s.get("lifetime_cents", 0)))}</td>'
        '<td class="muted">separate figure &mdash; never subtracted from the line above</td></tr>'
        f"{unresolved}</tbody></table></section>"
    )


def _period_bars(bucket):
    """One period's two figures as bars, the larger filling the track.

    Hidden from a screen reader, because the two cells beside it say the same. A
    bucket's figures are always integers, so no bar here stands for "no data": a
    zero draws an empty track, which is R0.00 said again (INV-98).
    """
    most = max(bucket["spend_cents"], bucket["won_cents"], 1)

    def track(label, look, cents):
        # A sliver at least, or a small win beside a large spend looks like none.
        width = max(100 * cents / most, 1.5) if cents else 0
        return (
            f'<span>{label}</span><span class="track">'
            f'<span class="fill {look}" style="width:{width:.1f}%"></span></span>'
        )

    return (
        '<td aria-hidden="true"><div class="bars">'
        + track("Spent", "spent", bucket["spend_cents"])
        + track("Won", "gain", bucket["won_cents"])
        + "</div></td>"
    )


def _periods_section(model):
    """Spend against winnings, one period at a time (LOTTO-0036).

    Renders serve.py's figures VERBATIM and sums nothing: adding up a displayed
    column here is exactly INV-16's failure one section down (LOTTO-0002 4.6).

    Every bucket was scored, so both cells are integers and R0.00 always means
    "checked, won nothing" -- the three-valued question is settled at the
    source, not in a _money_cell()-style branch here.
    """
    p = model.get("periods") or {}
    buckets = p.get("buckets") or []
    if not buckets:
        # The heading and a reason, never a bare heading and never nothing.
        # A caption over an empty table invites "so I won nothing"; the whole
        # section vanishing reads as a fault. Both are the cardinal rule, and
        # naming why is what CLAUDE.md's "an empty page is correct only when
        # it carries a notice naming why" asks for. User decision 2026-09-02;
        # s6 said caption and no table.
        return (
            "<section><h2>Spend against winnings by period</h2>"
            '<p class="notcheckable">No period has a scored draw in it yet, so '
            "there is nothing to compare. This is not a total of zero &mdash; "
            "it means no draw this ticket history covers has been checked "
            "against a result.</p></section>"
        )
    rows, opts = {"year": [], "month": []}, {"year": [], "month": []}
    for i, b in enumerate(buckets):
        hide = "" if i == 0 else ' style="display:none"'
        rows[b["kind"]].append(
            f'<tr data-period="{_e(b["key"])}"{hide}>'
            f'<td>{_e(b["label"])}</td>'
            f'<td class="money">{_e(_rands(b["spend_cents"]))}</td>'
            f'<td class="money">{_e(_rands(b["won_cents"]))}</td>'
            f"{_period_bars(b)}</tr>"
        )
        opts[b["kind"]].append(
            f'<option value="{_e(b["key"])}">{_e(b["label"])}</option>'
        )
    cur = p.get("current_month")
    if cur:
        # LOTTO-0051 / INV-71: the current month before anything in it is
        # scored. NOT a bucket, so NO money cell: a figure here would read as
        # "checked, won nothing" for a month nobody checked. Option first among
        # the months, row between the years and the months, the same order.
        rows["month"].insert(
            0,
            f'<tr data-period="{_e(cur["key"])}" style="display:none">'
            f'<td>{_e(cur["label"])}</td>'
            '<td colspan="3" class="notcheckable">Nothing in this month has '
            "been checked against a result yet.</td></tr>",
        )
        opts["month"].insert(
            0, f'<option value="{_e(cur["key"])}">{_e(cur["label"])}</option>'
        )
    residue = ""
    if p.get("no_result_cents"):
        residue = (
            f'<p class="muted">Paid for, no result yet: '
            f'{_e(_rands(p["no_result_cents"]))} &mdash; in no period above, '
            "and never subtracted from one. A draw has no period until its "
            "result is in, whether it has not happened yet or has not been "
            "fetched.</p>"
        )
    return (
        '<section><h2>Spend against winnings by period</h2>'
        '<p class="muted">By the date of the draw, not of the purchase: a '
        "ticket's price is spread over the draws it paid for, so a period's "
        "two figures describe the same draws. Drawn over the same entries as "
        "the comparison below, which is why it starts where the results do "
        "&mdash; earlier periods have nothing that can be scored.</p>"
        '<label>Show <select id="periodfilter">'
        f'<optgroup label="Years">{"".join(opts["year"])}</optgroup>'
        f'<optgroup label="Months">{"".join(opts["month"])}</optgroup>'
        "</select></label>"
        '<table id="periods"><thead><tr><th>Period</th>'
        # Right-aligned like the figures under them, or each figure sits
        # under the NEXT column's heading (LOTTO-0007 (w)).
        '<th class="money">Spent</th><th class="money">Won</th>'
        '<th>Side by side</th>'
        "</tr></thead><tbody>"
        + "".join(rows["year"] + rows["month"])
        + f"</tbody></table>{residue}</section>"
    )


def _settings_section(model):
    st = model.get("settings", {})

    def sw(key, label):
        on = " checked" if st.get(key) else ""
        # The text is tied to the input with aria-labelledby rather than left
        # loose after the </label>. The <label> wraps only the input and the
        # slider, so without this both switches have an EMPTY accessible name
        # and a screen reader announces "switch, not checked" with no way to
        # tell which one it is. §4.7 justifies the real-checkbox markup on the
        # state a screen reader announces; the state was announced and the
        # name was not.
        return (
            f'<div class="row"><label class="switch">'
            f'<input type="checkbox" role="switch" id="{key}"{on} '
            f'aria-labelledby="{key}-lbl">'
            f'<span class="slider"></span></label> '
            f'<span id="{key}-lbl">{_e(label)}</span></div>'
        )

    # The selected option is the DEFAULT, never the stored choice: the choice
    # lives in the browser and the renderer is pure, so the server cannot know
    # it. The script re-syncs the control on load; marking anything else here
    # would be the page asserting something it has not got.
    opts = "".join(
        f'<option value="{_e(tid)}"'
        + (" selected" if tid == DEFAULT_THEME else "")
        + f">{_e(label)}</option>"
        for tid, label, _colours in THEMES
    )
    # The previews drive the dropdown rather than replace it: with no script the
    # dropdown is what shows, and the script keeps one place that applies a theme.
    # Their colours are the themes' own, so a preview is right under any theme.
    swatches = "".join(
        f'<button type="button" class="swatch" data-pick="{_e(tid)}" aria-pressed="false" '
        f'style="background:{colours["bg"]};color:{colours["fg"]}">'
        '<span class="swatchface"><span class="swatchaa">Aa</span>'
        f'<span class="swatchline" style="background:{colours["panel"]};'
        f'border-color:{colours["line"]}"></span>'
        f'<span class="swatchdot" style="background:{colours["accent"]}"></span></span>'
        f'<span class="swatchname">{_e(label)}</span></button>'
        for tid, label, colours in THEMES
    )
    theme = (
        "<h3>Colour theme</h3>"
        f'<div class="swatches" role="group" aria-label="Colour theme">{swatches}</div>'
        '<div class="row themerow"><label for="theme">Colour theme</label>'
        f'<select id="theme">{opts}</select></div>'
    )

    return (
        "<section><h2>Settings</h2>"
        + theme
        + "<h3>Tray</h3>"
        + sw("autostart", "Start the tray when I log in")
        + sw("open_on_start", "Open this page when the tray starts")
        # role=status + aria-live: the switches write their result here, and
        # without it a screen reader is told nothing at all.
        + '<p class="muted" id="settings-msg" role="status" '
        'aria-live="polite"></p></section>'
    )


# ------------------------------------------------------------------ themes
# Every theme fills the SAME eleven roles. One left unset falls through to
# whatever the browser paints - white, for most of them - which is the blinding
# first paint this feature exists to remove. So the completeness is asserted
# (INV-62), not trusted.
#
# The named palettes take their background, foreground and accent hexes from the
# published palettes they are named after. The two NOTICE surfaces are derived
# tints in every theme, not palette members: no palette publishes a "warning
# background", and inventing one is honest where claiming provenance would not
# be.
THEME_ROLES = (
    "bg", "fg", "dim", "line", "panel",
    "accent", "warn", "warn-bg", "bad", "bad-bg", "on",
)

DEFAULT_THEME = "dark"

# id, dropdown label, palette. Order is the dropdown's order: dark first,
# because that is the default and the reason this exists.
THEMES = [
    ("dark", "Dark", {
        "bg": "#15131f", "fg": "#f3f1f8", "dim": "#b1adc4", "line": "#3a3650",
        "panel": "#242033", "accent": "#f5b92e", "warn": "#ffc857",
        "warn-bg": "#35290d", "bad": "#f0705f", "bad-bg": "#3a1f24",
        "on": "#4fb563"}),
    ("contrast", "High contrast", {
        "bg": "#000000", "fg": "#ffffff", "dim": "#d6d6d6", "line": "#7a7a7a",
        "panel": "#141414", "accent": "#ffd400", "warn": "#ffd400",
        "warn-bg": "#332b00", "bad": "#ff8a80", "bad-bg": "#3d0000",
        "on": "#00e05a"}),
    ("warm", "Warm dark", {
        "bg": "#201b17", "fg": "#f0e6d8", "dim": "#b9a892", "line": "#3a3129",
        "panel": "#2b241e", "accent": "#e0a458", "warn": "#f2be74",
        "warn-bg": "#362a19", "bad": "#e28874", "bad-bg": "#3a241f",
        "on": "#7ea36a"}),
    ("nord", "Nord", {
        "bg": "#2e3440", "fg": "#eceff4", "dim": "#a9b3c4", "line": "#4c566a",
        "panel": "#3b4252", "accent": "#88c0d0", "warn": "#ebcb8b",
        "warn-bg": "#3b3a2e", "bad": "#bf616a", "bad-bg": "#402f33",
        "on": "#a3be8c"}),
    ("dracula", "Dracula", {
        "bg": "#282a36", "fg": "#f8f8f2", "dim": "#9aa4c8", "line": "#44475a",
        "panel": "#343746", "accent": "#bd93f9", "warn": "#f1fa8c",
        "warn-bg": "#3b3a2c", "bad": "#ff5555", "bad-bg": "#40282c",
        "on": "#50fa7b"}),
    ("gruvbox", "Gruvbox", {
        "bg": "#282828", "fg": "#ebdbb2", "dim": "#a89984", "line": "#504945",
        "panel": "#3c3836", "accent": "#d79921", "warn": "#fabd2f",
        "warn-bg": "#3c3423", "bad": "#fb4934", "bad-bg": "#3f2723",
        "on": "#98971a"}),
    ("tokyo", "Tokyo Night", {
        "bg": "#1a1b26", "fg": "#c0caf5", "dim": "#7f88ad", "line": "#2f334d",
        "panel": "#24283b", "accent": "#7aa2f7", "warn": "#e0af68",
        "warn-bg": "#2e2a20", "bad": "#f7768e", "bad-bg": "#33222a",
        "on": "#9ece6a"}),
    ("catppuccin", "Catppuccin Mocha", {
        "bg": "#1e1e2e", "fg": "#cdd6f4", "dim": "#a6adc8", "line": "#313244",
        "panel": "#26263a", "accent": "#cba6f7", "warn": "#f9e2af",
        "warn-bg": "#34301f", "bad": "#f38ba8", "bad-bg": "#372430",
        "on": "#a6e3a1"}),
    ("monokai", "Monokai", {
        "bg": "#272822", "fg": "#f8f8f2", "dim": "#a6a48f", "line": "#49483e",
        "panel": "#32332a", "accent": "#66d9ef", "warn": "#e6db74",
        "warn-bg": "#3a3722", "bad": "#f92672", "bad-bg": "#3b2029",
        "on": "#a6e22e"}),
    ("solarized-dark", "Solarized Dark", {
        "bg": "#002b36", "fg": "#93a1a1", "dim": "#7d9497", "line": "#073642",
        "panel": "#073642", "accent": "#268bd2", "warn": "#b58900",
        "warn-bg": "#1d3320", "bad": "#dc322f", "bad-bg": "#33221f",
        "on": "#859900"}),
    ("light", "Light", {
        "bg": "#fafafa", "fg": "#1a1a1a", "dim": "#555555", "line": "#e0e0e0",
        "panel": "#f0f0f0", "accent": "#b26a00", "warn": "#8a5a00",
        "warn-bg": "#fff8e1", "bad": "#c0392b", "bad-bg": "#fdecea",
        "on": "#2d7a2d"}),
    ("solarized-light", "Solarized Light", {
        "bg": "#fdf6e3", "fg": "#3f5b62", "dim": "#586e75", "line": "#eee8d5",
        "panel": "#eee8d5", "accent": "#268bd2", "warn": "#8a6600",
        "warn-bg": "#f6efd4", "bad": "#dc322f", "bad-bg": "#f7e5df",
        "on": "#657b00"}),
    ("sepia", "Sepia", {
        "bg": "#f4ecd8", "fg": "#3b3228", "dim": "#6d5d49", "line": "#ddd0b4",
        "panel": "#eae0c8", "accent": "#a06a2c", "warn": "#8a5a00",
        "warn-bg": "#f0e2bd", "bad": "#a3402f", "bad-bg": "#f0dcd4",
        "on": "#5f7d3c"}),
]

THEME_IDS = [t[0] for t in THEMES]
_PALETTES = {tid: colours for tid, _label, colours in THEMES}


def _theme_block(selector, colours):
    return selector + "{" + "".join(
        "--%s:%s;" % (role, colours[role]) for role in THEME_ROLES
    ) + "}"


def _themes_css():
    """The default palette on :root, then one override block per theme.

    The default lives on `:root` rather than behind a `data-theme`, so a page
    that never runs a line of JavaScript is still dark. That is the whole
    mechanism: nothing here waits for a script to avoid painting white.
    """
    out = [_theme_block(":root", _PALETTES[DEFAULT_THEME])]
    for tid, _label, colours in THEMES:
        out.append(_theme_block('html[data-theme="%s"]' % tid, colours))
    return "\
".join(out)


# Applied in <head>, before the body exists, so a stored choice is in force at
# the FIRST paint. Reading it after the body has rendered is what produces the
# flash of the default theme this whole feature is about.
# The pattern guard is not decoration: the value is attacker-writable in
# principle (anything running in this origin), and it lands in an attribute.
THEME_BOOT = (
    'document.documentElement.className="js";'
    'try{var t=localStorage.getItem("lotto-theme");'
    'if(t&&/^[a-z0-9-]{1,32}$/.test(t))'
    'document.documentElement.setAttribute("data-theme",t)}catch(e){}'
)
# Colour is stated once, as the eleven roles above; every rule below reads a
# variable rather than a hex. That is what makes a new theme a table row instead
# of a second copy of this stylesheet.
BASE_CSS = """
body{font:1.125rem/1.55 "Atkinson Hyperlegible Next",system-ui,sans-serif;margin:0;
 color:var(--fg);background:var(--bg)}
.column{box-sizing:border-box;width:max(75%,90rem);max-width:100%;margin:0 auto;padding:0 1.25rem}
main.column{padding-top:1.5rem;padding-bottom:3rem}
.topbar{position:sticky;top:0;z-index:10;background:var(--panel);
 background:color-mix(in srgb,var(--panel) 90%,transparent);backdrop-filter:blur(12px);
 border-bottom:1px solid var(--line)}
.bar{display:flex;flex-wrap:wrap;align-items:center;gap:.25rem 2rem;padding-top:.6rem}
.brand{display:flex;align-items:center;gap:.6rem;padding-bottom:.6rem}
.brand img{width:1.75rem;height:1.75rem}
h1{font-size:1.5rem;font-weight:800;margin:0;letter-spacing:-.015em}
.tabs{display:flex;flex:1 1 auto;gap:.25rem;overflow-x:auto;scrollbar-width:none;align-self:flex-end}
.tab{padding:.5rem .9rem .7rem;background:none;border:0;border-bottom:4px solid transparent;
 border-radius:.4rem .4rem 0 0;color:var(--dim);cursor:pointer;white-space:nowrap;font-weight:700;
 transition:color .15s,border-color .15s}
.tab:hover{color:var(--fg);border-bottom-color:var(--line)}
.tab[aria-selected=true]{color:var(--fg);border-bottom-color:var(--accent)}
.baractions{display:flex;align-items:center;gap:.75rem;padding-bottom:.6rem}
#top-msg{color:var(--dim);font-size:.95rem}
.js .tabpanel:not(.on){display:none}
h2{font-size:1.75rem;font-weight:800;line-height:1.25;letter-spacing:-.015em;margin:2rem 0 .6rem}
h3{font-size:1.25rem;font-weight:700;margin:1.5rem 0 .4rem}
table{border-collapse:collapse;width:100%;margin:.5rem 0}
th,td{text-align:left;padding:.6rem .6rem;border-bottom:1px solid var(--line);font-size:1.05rem}
th{font-weight:700;color:var(--dim);border-bottom:2px solid var(--line)}
tbody tr:hover td{background:var(--panel)}
.cards th,.cards td{white-space:nowrap}
.cards td.wrap{white-space:normal;min-width:14rem}
#wins th,#wins td,#paid th,#paid td{padding-left:.4rem;padding-right:.4rem}
.tablewrap{overflow-x:auto}
.money{text-align:right;font-variant-numeric:tabular-nums}
.won{font-weight:700;color:var(--accent)}
td.ref{color:var(--dim)}
td.stack .muted{display:block}
.nil{color:var(--dim)}
#wins td.money,#paid td.money{font-size:1.2rem;font-weight:700}
.pip{display:inline-block;width:.8em;height:.8em;margin-right:.5em;border-radius:50%;background:#4a5568}
.nums{white-space:nowrap}
.ball{display:inline-block;position:relative;min-width:2rem;height:2rem;line-height:2rem;
 margin:.08rem .06rem;border-radius:50%;background:#4a5568;color:#fff;text-align:center;
 font-variant-numeric:tabular-nums;font-size:1.1rem;font-weight:700}
.ball:after{content:"";position:absolute;inset:0;border-radius:50%;pointer-events:none;
 background:radial-gradient(circle at 34% 24%,rgba(255,255,255,.34),rgba(255,255,255,0) 48%);
 box-shadow:inset -1px -3px 5px rgba(0,0,0,.35)}
.ball.special{background:#6a1b9a;color:#fff}
.runname{background:#4a5568}
[data-game="lotto"] .ball,[data-game="lotto"] .runname,[data-game="lotto"] .pip{background:#c62828}
[data-game="lotto"] .ball.special{background:#6a1b9a}
[data-game="powerball"] .ball,[data-game="powerball"] .runname,[data-game="powerball"] .pip{background:#1565c0}
[data-game="powerball"] .ball.special{background:#bf360c}
[data-game="daily"] .ball,[data-game="daily"] .runname,[data-game="daily"] .pip{background:#2e7d32}
[data-game="lotto"]{--g:#c62828;--gs:#6a1b9a}
[data-game="powerball"]{--g:#1565c0;--gs:#bf360c}
[data-game="daily"]{--g:#2e7d32}
/* A number that did not match is a ring, not a dimmer disc: the difference has to
   survive low vision, so it is filled against empty rather than one colour against
   another. Its figure takes the theme's foreground, which INV-62 holds readable. */
.ball.miss,[data-game] .ball.miss{background:none;color:var(--fg);box-shadow:inset 0 0 0 2.5px var(--g,#4a5568)}
.ball.special.miss,[data-game] .ball.special.miss{box-shadow:inset 0 0 0 2.5px var(--gs,#6a1b9a)}
.ball.miss:after{display:none}
.ballkey{display:flex;align-items:center;gap:.5rem;margin:.6rem 0 0;color:var(--dim)}
.ballkey .ball:not(:first-child){margin-left:.9rem}
.notcheckable{color:var(--warn)}
.muted{color:var(--dim);font-size:1rem}
.notice{background:var(--warn-bg);border-left:6px solid var(--accent);border-radius:.5rem;
 padding:.8rem 1.1rem;margin:.9rem 0}
.notice.bad{background:var(--bad-bg);border-left-color:var(--bad)}
/* Above every tab by rule (INV-89), but nothing to act on: it keeps its place and gives
   up its box, so the Overview's headline is the first thing that looks like news. */
.notice.standing{background:none;border-left:3px solid var(--line);border-radius:0;
 padding:.1rem 0 .1rem 1rem;color:var(--dim);font-size:1rem;max-width:90ch}
.notice.standing strong{color:var(--fg)}
.headline{font-size:clamp(2.1rem,4vw,3.25rem);font-weight:800;line-height:1.12;letter-spacing:-.025em;
 margin:1.75rem 0 1.5rem;text-wrap:balance}
/* The running tickets are the page's one flourish: each is a lottery slip, with a stub
   in its game's colour, a perforated tear line, real notches cut by the mask, and one
   ball per draw paid for, punched out once that draw has happened. The outline sits on
   the list rather than the slip because a parent's drop-shadow follows the notches. */
.runs{list-style:none;display:grid;gap:1rem;margin:0 0 2.5rem;padding:0;
 filter:drop-shadow(0 0 1px var(--line)) drop-shadow(0 0 1px var(--line))}
.run{--stub:16rem;--notch:.8rem;display:grid;grid-template-columns:var(--stub) minmax(0,1fr) minmax(15rem,24rem);
 align-items:stretch;border-radius:.9rem;overflow:hidden;background:var(--panel);
 mask:radial-gradient(circle var(--notch) at var(--stub) 0,transparent 97%,#000),
  radial-gradient(circle var(--notch) at var(--stub) 100%,transparent 97%,#000);
 mask-composite:intersect}
.runname{display:flex;flex-direction:column;justify-content:center;align-items:flex-start;gap:.35rem;
 padding:1.25rem 1.4rem;color:#fff;font-size:1.65rem;font-weight:800;line-height:1.15;letter-spacing:-.015em;
 background-image:linear-gradient(135deg,rgba(255,255,255,.13),rgba(255,255,255,0) 65%)}
.runname .muted{color:#fff;font-size:1rem;font-weight:400;letter-spacing:0;line-height:1.3}
.tag{padding:.1rem .7rem;border-radius:1rem;font-size:1.05rem;font-weight:700;letter-spacing:0;
 color:var(--warn);background:var(--warn-bg)}
.burn{display:flex;flex-wrap:wrap;align-content:center;gap:.5rem;padding:1.25rem 1.75rem;
 border-left:5px dotted var(--bg)}
.burn .ball{min-width:2.4rem;height:2.4rem;margin:0}
.burn .ball.used,[data-game] .burn .ball.used{background:var(--bg);
 box-shadow:inset 0 2px 3px rgba(0,0,0,.45),0 0 0 1px var(--line)}
.burn .ball.used:after{display:none}
.runfacts{align-self:center;padding:1.25rem 1.75rem 1.25rem 0}
.runfacts strong{display:block;font-size:1.75rem;font-weight:800;line-height:1.2;letter-spacing:-.01em}
.run:has(.tag){background:var(--warn-bg)}
.run:has(.tag) .runfacts strong{color:var(--warn)}
@keyframes punch{from{background:var(--g,#4a5568);box-shadow:none}}
/* The page's one unprompted movement: on opening, the draws already used are punched
   out in order. Once the reader leaves the Overview it never replays. */
@media(prefers-reduced-motion:no-preference){
 html:not(.seen) .burn .ball.used{animation:punch .45s ease-out backwards;animation-delay:calc(var(--i)*70ms)}
}
.glances{display:flex;flex-wrap:wrap;gap:1rem}
.glance{flex:1 1 22rem;display:flex;flex-direction:column;align-items:flex-start;
 padding:.25rem 1.75rem 1.5rem;border-radius:.9rem;background:var(--panel)}
.glance h3{margin-top:1rem}
.glance p{flex:1;margin:.3rem 0 1.1rem;max-width:60ch;line-height:1.7}
.glance strong{font-size:1.3em;font-weight:800;font-variant-numeric:tabular-nums}
.golink{cursor:pointer;padding:.45rem 1rem;background:none;border:2px solid var(--accent);font-weight:700;
 transition:background-color .15s,color .15s}
.golink:hover{background:var(--accent);color:var(--bg)}
html:not(.js) .golink{display:none}
tr.soon td{background:var(--warn-bg)}tr.today td{background:var(--bad-bg);font-weight:600}
.row{display:flex;flex-wrap:wrap;align-items:center;gap:.6rem 1.25rem;margin:.5rem 0}
section>p.muted{max-width:75ch}
#panel-spending table{max-width:68rem}
#periods td.money{font-size:1.5rem;font-weight:800}
.bars{display:grid;grid-template-columns:auto 1fr;gap:.4rem .7rem;align-items:center;min-width:14rem;
 color:var(--dim);font-size:.95rem}
.track{display:block;height:1.1rem;border-radius:.55rem;background:var(--panel);overflow:hidden}
.fill{display:block;height:100%;border-radius:inherit}
.spent{background:var(--dim)}
.gain{background:var(--accent)}
.swatches{display:grid;grid-template-columns:repeat(auto-fill,minmax(12rem,1fr));gap:.75rem;margin:.5rem 0 1rem}
.swatch{display:block;padding:0;border:2px solid var(--line);border-radius:.7rem;overflow:hidden;cursor:pointer;text-align:left}
.swatch:hover{border-color:var(--dim)}
.swatch[aria-pressed=true]{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent)}
.swatchface{display:flex;align-items:center;gap:.6rem;padding:.55rem .8rem .3rem}
.swatchaa{font-size:1.6rem;font-weight:800;line-height:1.2}
.swatchline{flex:1;height:.75rem;border:1px solid;border-radius:.4rem}
.swatchdot{flex:none;width:1.1rem;height:1.1rem;border-radius:50%}
.swatchname{display:block;padding:0 .8rem .55rem;font-weight:700}
.swatch[aria-pressed=true] .swatchname:after{content:" \\2713"}
html:not(.js) .swatches{display:none}
.js .themerow{display:none}
.switch{position:relative;display:inline-block;width:2.6rem;height:1.4rem;flex:none}
.switch input{position:absolute;opacity:0;width:100%;height:100%;margin:0;cursor:pointer}
.slider{position:absolute;inset:0;background:var(--line);border-radius:1rem;transition:.15s;
 pointer-events:none}
.slider:before{content:"";position:absolute;width:1.1rem;height:1.1rem;left:.15rem;
 top:.15rem;background:var(--fg);border-radius:50%;transition:.15s}
.switch input:checked+.slider{background:var(--on)}
.switch input:checked+.slider:before{transform:translateX(1.2rem)}
.switch input:focus-visible+.slider{outline:2px solid var(--accent);outline-offset:2px}
footer{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--line);color:var(--dim);font-size:1rem}
.disclaimer{margin-top:1rem;color:var(--dim);font-size:1rem;max-width:80ch}
button,select{font:inherit;padding:.35rem .8rem;background:var(--panel);color:var(--fg);
 border:1px solid var(--line);border-radius:.5rem}
/* The arrow is two triangles of the text colour, so each theme gets its own. */
select{cursor:pointer;appearance:none;padding-right:2.2rem;
 background-image:linear-gradient(45deg,transparent 50%,currentColor 50%),
  linear-gradient(135deg,currentColor 50%,transparent 50%);
 background-size:.4rem .4rem;background-repeat:no-repeat;
 background-position:right 1.1rem center,right .7rem center}
select:hover{border-color:var(--dim)}
html{scrollbar-color:var(--line) var(--bg)}
html.seen .tabpanel.on{animation:appear .16s ease-out}
@keyframes appear{from{opacity:0}}
#refresh{cursor:pointer;background:var(--bg);white-space:nowrap}
#refresh:hover{border-color:var(--accent)}
button:focus-visible,select:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.tab:focus-visible{outline-offset:-3px}
.sorthead{font-weight:600;padding:0;background:none;border:0;color:inherit;cursor:pointer}
.sorthead:hover{color:var(--fg);text-decoration:underline}
th[aria-sort=descending] .sorthead:after{content:" \\25BC"}
th[aria-sort=ascending] .sorthead:after{content:" \\25B2"}
/* Narrower than the column's 90rem floor, which is what the widest table needs: each
   row becomes a card, one labelled line per cell. The labels are copied from the
   headings by JS below (INV-86). */
@media(max-width:90rem){
 .cards thead{display:none}
 .cards table,.cards tbody,.cards tr,.cards td{display:block}
 .cards tr{background:var(--panel);border:1px solid var(--line);border-radius:.7rem;margin:.8rem 0;padding:.6rem .5rem}
 .cards td,.cards td.wrap{padding:.35rem .5rem;border:0;white-space:normal;min-width:0;text-align:left}
 .cards td:before{content:attr(data-label);display:block;color:var(--dim);font-size:.9rem;font-weight:600}
 .cards td:empty{display:none}
 tbody tr:hover td{background:none}
 .tabs{order:3;flex-basis:100%}
 .baractions{margin-left:auto}
}
@media(max-width:60rem){
 .run{grid-template-columns:1fr;mask:none}
 .burn{border-left:0;border-top:5px dotted var(--bg)}
 .runfacts{padding:0 1.4rem 1.1rem}
}
/* Room for more than one column: a card lays its fields out across, not one long list. */
@media(min-width:36rem) and (max-width:90rem){
 .cards tr{display:grid;grid-template-columns:repeat(auto-fill,minmax(17rem,1fr));gap:0 1rem}
}
@media(max-width:36rem){
 .burn{padding:.9rem 1.2rem;gap:.25rem}
 .burn .ball{min-width:1.7rem;height:1.7rem}
 #periods tr{display:grid;grid-template-columns:1fr auto auto}
 #periods th:last-child{display:none}
 #periods td:last-child{grid-column:1/-1}
}
@media(prefers-reduced-motion:reduce){
 .slider,.slider:before,.tab,.golink{transition:none}
 html.seen .tabpanel.on{animation:none}
}
"""

CSS = _themes_css() + BASE_CSS

# Seven jobs and no others (LOTTO-0002 §4.1): the two POSTs (custom header, so a
# cross-origin form post cannot forge them), filtering and sorting (must never
# touch the URL - INV-21), the headings copied onto a phone's card rows, switching
# tabs (the same rule, INV-89), applying a colour theme (INV-63), and polling
# /status while a build is in flight.
JS = """
var TOKEN=%s;
function post(path,body,done){
 var x=new XMLHttpRequest();x.open("POST",path,true);
 x.setRequestHeader("X-Lotto-Token",TOKEN);
 x.setRequestHeader("Content-Type","application/json");
 x.onreadystatechange=function(){if(x.readyState===4)done(x.status,x.responseText)};
 x.send(body===null?"":JSON.stringify(body));
}
function msg(t){var e=document.getElementById("settings-msg");if(e)e.textContent=t}
// The result of a refresh goes in the bar. #settings-msg sits in a tab that is
// usually hidden, and a failure said where nobody can see it was not said (INV-89).
function note(t){var e=document.getElementById("top-msg");if(e)e.textContent=t;else msg(t)}
function wire(id){
 var el=document.getElementById(id);if(!el)return;
 el.addEventListener("change",function(){
  var want={};want[id]=el.checked;
  post("/settings",want,function(code,text){
   if(code===403){msg("This page is from an earlier session - reload it.");return}
   if(code!==200){el.checked=!el.checked;msg("Could not save that setting.");return}
   try{var s=JSON.parse(text);
       // Snap back to what is actually stored, never to what was asked for.
       for(var k in s){var n=document.getElementById(k);if(n)n.checked=!!s[k]}
       msg("Saved.")}catch(e){msg("Saved, but the reply was unreadable.")}
  });
 });
}
wire("autostart");wire("open_on_start");
// The theme. It writes a data-theme attribute and one localStorage key holding
// a theme NAME, and nothing else: no query parameter, no fragment, no history
// entry, and no ticket data anywhere (INV-21, INV-63). It deliberately does not
// POST: the two switches above are the tray's business, a colour is this
// browser's, and routing it through /settings would give settings.json a second
// writer for no gain.
var th=document.getElementById("theme");
if(th){
 try{var saved=localStorage.getItem("lotto-theme");
     // Adopt it only if the dropdown offers it. Assigning an unknown value
     // blanks the select, which then disagrees with what is on the screen -
     // and a stored name outlives the release that dropped that theme.
     if(saved){for(var i=0;i<th.options.length;i++){
       if(th.options[i].value===saved){th.value=saved;break}}}
 }catch(e){}
 // A preview only moves the dropdown, so one place still applies a theme.
 var picks=[].slice.call(document.querySelectorAll(".swatch"));
 function markPick(){picks.forEach(function(b){
  b.setAttribute("aria-pressed",b.getAttribute("data-pick")===th.value?"true":"false")})}
 picks.forEach(function(b){b.addEventListener("click",function(){
  th.value=b.getAttribute("data-pick");th.dispatchEvent(new Event("change"))})});
 markPick();
 th.addEventListener("change",function(){
  document.documentElement.setAttribute("data-theme",th.value);
  try{localStorage.setItem("lotto-theme",th.value)}catch(e){}
  markPick();
  msg("Theme applied.");
 });
}
var rb=document.getElementById("refresh");
if(rb)rb.addEventListener("click",function(){
 rb.disabled=true;rb.textContent="Refreshing...";
 post("/refresh",null,function(code){
  if(code===202){poll()}
  else{rb.disabled=false;rb.textContent="Refresh results";
       note(code===409?"A refresh is already running.":"Refresh was declined.")}
 });
});
// Filtering is client-side over rows already in the document. It must not add a
// query parameter, a fragment or a history entry: all three put ticket data
// where the browser syncs it (INV-21).
var gf=document.getElementById("gamefilter");
var plf=document.getElementById("poolfilter");
function applyEntryFilter(){
 var wg=gf?gf.value:"",wp=plf?plf.value:"";
 var rows=document.querySelectorAll("#entries tbody tr");
 for(var i=0;i<rows.length;i++){
  var okg=!wg||rows[i].getAttribute("data-game")===wg;
  var okp=!wp||rows[i].getAttribute("data-pool")===wp;
  rows[i].style.display=(okg&&okp)?"":"none";
 }
}
if(gf)gf.addEventListener("change",applyEntryFilter);
if(plf)plf.addEventListener("change",applyEntryFilter);
// Sorting moves rows already in the document, under the same rule (INV-21). It
// stores nothing: browser storage holds the theme name alone (INV-63), so a
// reload returns to latest first. A cell with no value goes last in BOTH
// directions: "not checkable" must never sort among the zeroes as if it had lost.
function sortKey(row,col,kind){
 var t=row.cells[col]?row.cells[col].textContent.trim():"";
 if(kind==="num"){var n=parseFloat(t.replace(/[R, ]/g,""));return isNaN(n)?null:n}
 if(kind==="date")return row.cells[col]&&row.cells[col].getAttribute("data-sort")||null;
 return t||null;
}
function sortTable(table,col,dir){
 var heads=table.tHead.rows[0].cells,kind=heads[col].getAttribute("data-kind");
 var body=table.tBodies[0],keyed=[];
 for(var i=0;i<body.rows.length;i++){
  keyed.push({row:body.rows[i],key:sortKey(body.rows[i],col,kind)});
 }
 keyed.sort(function(a,b){
  if(a.key===null||b.key===null){return a.key===b.key?0:(a.key===null?1:-1)}
  var c=kind==="num"?a.key-b.key:
   a.key.localeCompare(b.key,undefined,{numeric:true,sensitivity:"base"});
  return dir==="desc"?-c:c;
 });
 for(var j=0;j<keyed.length;j++)body.appendChild(keyed[j].row);
 for(var h=0;h<heads.length;h++)heads[h].removeAttribute("aria-sort");
 heads[col].setAttribute("aria-sort",dir==="desc"?"descending":"ascending");
 var sel=document.querySelector('.sortby[data-table="'+table.id+'"]');
 if(sel)sel.value=col+":"+dir;
}
function wireTable(table){
 var heads=table.tHead.rows[0].cells;
 for(var r=0;r<table.tBodies[0].rows.length;r++){
  var cells=table.tBodies[0].rows[r].cells;
  for(var c=0;c<cells.length;c++){
   cells[c].setAttribute("data-label",heads[c].textContent);
  }
 }
 [].forEach.call(heads,function(head,col){
  var b=head.querySelector(".sorthead");if(!b)return;
  b.addEventListener("click",function(){
   var now=head.getAttribute("aria-sort");
   var first=head.getAttribute("data-kind")==="text"?"asc":"desc";
   sortTable(table,col,now?(now==="descending"?"asc":"desc"):first);
  });
 });
}
[].forEach.call(document.querySelectorAll(".cards table"),wireTable);
[].forEach.call(document.querySelectorAll(".sortby"),function(sel){
 sel.addEventListener("change",function(){
  var want=sel.value.split(":");
  sortTable(document.getElementById(sel.getAttribute("data-table")),+want[0],want[1]);
 });
});
// Tabs show one panel at a time. They add no fragment and store nothing (INV-89):
// a stylesheet hides the other panels only once the head has marked the page as
// running script, so with no script every section is simply on the page.
var tabs=[].slice.call(document.querySelectorAll(".tab"));
function showTab(tab,focus){
 document.documentElement.classList.add("seen");
 tabs.forEach(function(t){
  var on=t===tab;
  t.setAttribute("aria-selected",on?"true":"false");
  t.tabIndex=on?0:-1;
  document.getElementById(t.getAttribute("aria-controls")).classList.toggle("on",on);
 });
 if(focus)tab.focus();
 window.scrollTo(0,0);
}
tabs.forEach(function(tab,i){
 tab.addEventListener("click",function(){showTab(tab)});
 tab.addEventListener("keydown",function(ev){
  var step=ev.key==="ArrowRight"?1:ev.key==="ArrowLeft"?-1:0;
  if(step){ev.preventDefault();showTab(tabs[(i+step+tabs.length)%%tabs.length],true)}
 });
});
[].forEach.call(document.querySelectorAll(".golink"),function(b){
 b.addEventListener("click",function(){
  showTab(document.getElementById("tab-"+b.getAttribute("data-goto")),true);
 });
});
// Same rule for the period selector: rows are already in the document and
// only their visibility changes (INV-21).
var pf=document.getElementById("periodfilter");
if(pf)pf.addEventListener("change",function(){
 var want=pf.value,rows=document.querySelectorAll("#periods tbody tr");
 for(var i=0;i<rows.length;i++){
  rows[i].style.display=(rows[i].getAttribute("data-period")===want)?"":"none";
 }
});
// Poll while a build is in flight. Without this the opening "building" page
// never leaves that state and /status has no consumer at all. It also has to
// terminate on FAILURE: a failed refresh leaves `built` unchanged, so a poll
// watching only `built` would wait for a change that never comes.
var BUILT=%s;
// Write a sentence where the reader will actually see it. #progress exists on
// the opening-build page and #settings-msg on a built one; neither exists on
// both, and msg() targeted only the second.
function say(t){
 var p=document.getElementById("progress");
 if(p){p.textContent=t;return}
 note(t);
}
function poll(){
 var x=new XMLHttpRequest();x.open("GET","/status",true);
 x.onreadystatechange=function(){
  if(x.readyState!==4)return;
  // The STATUS, before the body. status 0 is "the request did not complete"
  // - the server is gone. Without this the empty responseText fell through
  // the catch into s={}, every branch below missed, and the tail re-armed
  // the poll forever under a notice still reading "Checking your tickets..."
  // - a build asserted to be in flight that had already stopped. Saying the
  // connection was lost is the whole point (LOTTO-0002 s6), and nothing
  // mechanical checks this because it is browser-side.
  if(x.status===0||x.status>=500){say("The tracker is no longer running - "+
    "the connection was lost. Nothing below is being updated.");return}
  var s={};try{s=JSON.parse(x.responseText)}catch(e){}
  if(s.building){var p=document.getElementById("progress");
                 if(p)p.textContent=s.requests+(s.requests===1?" lookup":" lookups")+" so far.";
                 setTimeout(poll,2000);return}
  if(s.built&&s.built!==BUILT){location.reload();return}
  if(s.stale){
              // A FIRST build that failed leaves `built` null, so the reload
              // test above never fires and #settings-msg does not exist on
              // this page - msg() silently dropped the sentence and the tab
              // sat on "Checking your tickets..." permanently. Reload once so
              // the server can serve s6's results-unavailable state instead.
              // location.reload() changes no URL, so INV-21 is untouched.
              if(!BUILT){location.reload();return}
              var b=document.getElementById("refresh");
              if(b){b.disabled=false;b.textContent="Refresh results"}
              // A browser open since the bind never re-renders, so a failed
              // OPENING build would leave the counter frozen under a notice
              // that still reads as in-flight. The build stopped; the count is
              // not a result (LOTTO-0019 §6).
              var p=document.getElementById("progress");
              if(p)p.textContent="";
              note("That refresh failed - the figures below are from an earlier fetch.");
              return}
  setTimeout(poll,2000);
 };
 x.send();
}
if(%s)poll();
"""


def render(model, token):
    """The model dict plus the run token -> one HTML string.

    The token is a parameter rather than a model key so that every §7 fixture is
    written to the model alone and no serialised model can ever carry it
    (LOTTO-0014 §4.3).
    """
    built = model.get("built")
    building = bool(model.get("building"))
    # serve.py supplies the icon: this file reads no disk. It is a data: address
    # rather than a route, so the server still answers exactly four (LOTTO-0014).
    icon = model.get("icon")
    logo = f'<img src="{_e(icon)}" alt="">' if icon else ""
    # The same arrangement for the typeface (INV-96). Without it the stack in
    # BASE_CSS falls through to the system's own font and nothing else changes.
    font = model.get("font")
    face = (
        '@font-face{font-family:"Atkinson Hyperlegible Next";font-weight:200 800;'
        f'font-display:swap;src:url({_e(font)}) format("woff2")}}'
        if font else ""
    )
    head = (
        f"<title>{TITLE}</title>"
        + (f'<link rel="icon" type="image/svg+xml" href="{_e(icon)}">' if icon else "")
        + f"<style>{face}{CSS}</style>"
        f"<script>{THEME_BOOT}</script>"
    )
    if building and not built:
        # LOTTO-0019 §4.4. The half-minute estimate is KEPT and qualified, not
        # dropped: a retrying build (LOTTO-0012) overshoots it, and an estimate
        # the build silently exceeds is its own small version of a page that
        # looks broken. Same singular rule as the poll, or a first paint at
        # requests == 1 reads "1 lookups so far" until the next tick.
        n = model.get("requests", 0)
        bar = ""
        body = (
            '<div class="notice"><strong>Checking your tickets…</strong> '
            "This takes about half a minute on the first run, longer if the "
            "operator's site is dropping connections. Nothing below is a "
            "result yet. "
            f'<span id="progress" role="status" aria-live="polite">{n} '
            f'{"lookup" if n == 1 else "lookups"} so far.</span></div>'
        )
    elif model.get("no_dump") or model.get("no_build") or (
            model.get("error") and not built):
        # The three states in which NOTHING was checked and there is no
        # earlier model to fall back on. §6 forbids each of the three things
        # the full body would render here by name - a ticket table, a zero
        # total, and an empty wins list - because all three read as "you have
        # won nothing", which is this project's cardinal failure arriving
        # through the network layer. The notice alone is not a discharge:
        # _spend_section reaches R0.00 three times off an absent record and
        # _wins_section says "No unexpired winning lines" while pointing at a
        # banner that is not there. §6 also records this as the COMMON path -
        # four of seven measured build attempts failed.
        #
        # `and not built` on the error arm is load-bearing: a refresh that
        # fails AFTER a good build must keep showing the previous figures and
        # say they are stale, which is INV-18 and is a different state.
        bar = ""
        body = _notice(model) + _settings_section(model)
    else:
        # The notices stay above the tabs: "no data is not a loss" and "this ticket
        # is not on this page" must not be something a tab can hide (INV-89).
        tabs = [
            ("overview", "Overview", _overview_section(model)),
            ("wins", "Wins", _ball_key(model) + _wins_section(model) + _paid_section(model)),
            ("outstanding", "Still outstanding", _outstanding_section(model)),
            ("entries", "Every entry", _entries_section(model)),
            ("spending", "Spending", _periods_section(model) + _spend_section(model)),
            ("settings", "Settings", _settings_section(model)),
        ]
        bar = (
            '<nav class="tabs" role="tablist" aria-label="Sections">'
            + "".join(
                f'<button type="button" class="tab" role="tab" id="tab-{key}" '
                f'aria-controls="panel-{key}" '
                f'aria-selected="{"true" if i == 0 else "false"}"'
                f'{"" if i == 0 else " tabindex=" + chr(34) + "-1" + chr(34)}>'
                f"{label}</button>"
                for i, (key, label, _html) in enumerate(tabs)
            )
            + '</nav><div class="baractions">'
            '<span id="top-msg" role="status" aria-live="polite"></span>'
            '<button type="button" id="refresh">Refresh results</button></div>'
        )
        body = (
            _notice(model)
            + _sms_quiet_section(model)
            + _senders_section(model)
            + _uncheckable_banner(model.get("uncheckable"))
            + "".join(
                f'<div class="tabpanel{" on" if i == 0 else ""}" id="panel-{key}" '
                f'role="tabpanel" aria-labelledby="tab-{key}">{section}</div>'
                for i, (key, _label, section) in enumerate(tabs)
            )
            + "<footer>"
            + (
                f"Results last checked: {_e(_long_date(str(built)[:10]))} "
                f"at {_e(str(built)[11:16])}."
                if built
                else "No successful build yet."
            )
            + " Expiry is computed at build time, so a prize marked as expiring "
            "today may already have lapsed.</footer>"
        )
    script = JS % (
        _js(token),
        _js(built),
        "true" if building else "false",
    )
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f'{head}</head><body><header class="topbar"><div class="column bar">'
        f'<div class="brand">{logo}<h1>{TITLE}</h1></div>{bar}</div></header>'
        f'<main class="column">{body}<p class="disclaimer">{DISCLAIMER}</p></main>'
        f"<script>{script}</script></body></html>"
    )
