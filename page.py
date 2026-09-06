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

TITLE = "Lotto Tracker"  # constant: INV-21 forbids ticket data in the title


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
        return '<td class="notcheckable">not checkable</td>'
    return f'<td class="money">{_e(_rands(won_cents))}</td>'


def _draws_cell(value):
    """draws_covered / draws_remaining are None for an unscorable entry.

    Rendering 0 here would be the cardinal error one column left: "0 draws
    checked" on a 2019 ticket reads as a result rather than as an absence.
    """
    if value is None:
        return '<td class="notcheckable">unknown &mdash; not checkable</td>'
    return f"<td>{_e(value)}</td>"


def _balls(numbers, special=None):
    """One set of numbers as markup, main numbers then any special (LOTTO-0035).

    The cardinal rule reaches here too: an absent set is said in words, never
    rendered as an empty cell. An empty list is absence, not "no numbers" - a
    board always has numbers, so nothing to show means nothing was known.
    """
    if not numbers:
        return '<span class="notcheckable">not recorded</span>'
    out = " ".join(f'<span class="ball">{_e(n)}</span>' for n in numbers)
    if special is not None:
        out += f' <span class="ball special">{_e(special)}</span>'
    return out


def _numbers_cell(numbers, special=None):
    return f"<td class=\"nums\">{_balls(numbers, special)}</td>"


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


def _uncheckable_banner(u):
    """Renders above the wins, never below, and is not collapsible (§4.5)."""
    if not u or not u.get("uncheckable"):
        return ""
    bits = []
    if u.get("too_old"):
        bits.append(f"{u['too_old']:,} predate all draw data for their pool")
    if u.get("no_pool"):
        bits.append(f"{u['no_pool']:,} are in a pool no results source carries")
    detail = "; ".join(bits)
    return (
        '<div class="notice"><strong>'
        f"{u['uncheckable']:,} of {u['entries']:,} entries cannot be checked."
        "</strong> They are <strong>not losses</strong> &mdash; nothing exists "
        f"to score them against. {_e(detail)}. This affects "
        f"{u.get('wholly', 0):,} tickets wholly and {u.get('partly', 0):,} "
        "partly; a partly-checkable ticket is still scored on its other pools."
        "</div>"
    )


def _wins_section(model):
    live = [w for w in model.get("wins", []) if not w.get("expired")]
    # A win with no expiry date sorts LAST, not first: "" compares below every
    # real date, so an absent value was reading as the most urgent line here.
    live.sort(key=lambda w: (not w.get("expires"), w.get("expires") or ""))
    if not live:
        body = (
            '<p class="muted">No unexpired winning lines. This counts only the '
            "entries that could be checked &mdash; see the banner above.</p>"
        )
    else:
        rows = []
        for w in live:
            d = w.get("expires_in_days")
            cls = "soon" if d is not None and d <= 30 else ""
            if d == 0:
                cls, when = "today", "today"
            elif d is not None and d < 0:
                # Past its claim date. Not "today" - and s4.5 requires every
                # win to name its date, which the old `d <= 0` branch threw
                # away along with the distinction.
                cls = "today"
                when = (
                    f'{_e(w.get("expires"))} '
                    '<span class="muted">(claim date passed)</span>'
                )
            else:
                when = f"{_e(w.get('expires'))}"
                if d is not None:
                    when += f' <span class="muted">({d} days)</span>'
            rows.append(
                f'<tr class="{cls}" data-game="{_e(w["game"])}">'
                f'<td>{_e(w["game"])}/{_e(w["plus_flag"])}</td>'
                + _numbers_cell(w.get("numbers"), w.get("special"))
                + _numbers_cell(w.get("drawn_main"), w.get("drawn_special"))
                + f'<td>{_e(w.get("division"))}</td><td>{_e(w.get("matched"))}</td>'
                f'<td>{_e(w.get("date"))}</td>'
                f'<td class="money">{_e(_rands(w["amount_cents"]))}</td>'
                f"<td>{when}</td></tr>"
            )
        body = (
            "<table><thead><tr><th>Pool</th><th>Your numbers</th><th>Drawn</th>"
            "<th>Division</th><th>Matched</th>"
            "<th>Draw</th><th>Amount</th><th>Expires</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
    return f"<section><h2>Claimable now</h2>{body}</section>"


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
        for e in entries:
            out.append(
                f'<tr data-game="{_e(e["game"])}"><td>{_e(e["ref"])}</td>'
                f'<td>{_e(e["game"])}/{_e(e["plus_flag"])}</td>'
                + _boards_cell(e.get("boards"))
                + (
                    f"<td>{e['draws_remaining']}</td>"
                    if remaining_col
                    else f'<td class="notcheckable">{_e(e.get("reason") or "not checkable")}</td>'
                )
                + "</tr>"
            )
        return "".join(out)

    parts = []
    if coming:
        parts.append(
            "<h3>Draws still to come</h3><table><thead><tr><th>Ticket</th>"
            "<th>Pool</th><th>Your numbers</th><th>Draws remaining</th>"
            "</tr></thead><tbody>"
            + rows(coming, True)
            + "</tbody></table>"
        )
    if unchecked:
        parts.append(
            f"<h3>Not checkable ({len(unchecked):,} entries)</h3>"
            '<p class="muted">Draws remaining is unknown for these: there is '
            "nothing to measure a window against. They are not losses.</p>"
            "<table><thead><tr><th>Ticket</th><th>Pool</th>"
            "<th>Your numbers</th><th>Why not</th>"
            "</tr></thead><tbody>" + rows(unchecked, False) + "</tbody></table>"
        )
    if not parts:
        parts.append('<p class="muted">Nothing outstanding.</p>')
    return "<section><h2>Still outstanding</h2>" + "".join(parts) + "</section>"


def _entries_section(model):
    """Every entry, filterable client-side only (INV-21: the URL never changes)."""
    rows = []
    for e in model.get("entries", []):
        pool = f"{e['game']}/{e['plus_flag']}"
        rows.append(
            f'<tr data-game="{_e(e["game"])}" data-pool="{_e(pool)}">'
            f'<td>{_e(e["ref"])}</td><td>{_e(pool)}</td>'
            f'<td class="money">{_e(_rands(e["cost_cents"]))}</td>'
            + _draws_cell(e.get("draws_covered"))
            + _money_cell(e.get("won_cents"))
            + f'<td class="notcheckable">{_e(e.get("reason") or "")}</td></tr>'
        )
    games = sorted({e["game"] for e in model.get("entries", [])})
    opts = "".join(f'<option value="{_e(g)}">{_e(g)}</option>' for g in games)
    # §4.5 item 3 promises the table is filterable by game AND pool. Every row
    # has carried data-pool since it was written, with nothing reading it -
    # the attribute looked wired and had no consumer at all. Same client-side
    # shape as the game filter, so INV-21 is untouched: no query parameter, no
    # fragment, no history entry, only visibility on rows already present.
    pools = sorted({f"{e['game']}/{e['plus_flag']}"
                    for e in model.get("entries", [])})
    popts = "".join(f'<option value="{_e(p)}">{_e(p)}</option>' for p in pools)
    return (
        "<section><h2>Every entry</h2>"
        '<label>Filter by game <select id="gamefilter">'
        f'<option value="">all</option>{opts}</select></label> '
        '<label>Filter by pool <select id="poolfilter">'
        f'<option value="">all</option>{popts}</select></label>'
        "<table id=\"entries\"><thead><tr><th>Ticket</th><th>Pool</th>"
        "<th>Cost</th><th>Draws checked</th><th>Won</th><th>Why not</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></section>"
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
        f'{_e(_rands(s.get("compared_cents", 0)))}</td><td>the comparison</td></tr>'
        f'<tr><td>Won on those same entries</td><td class="money">'
        f'{_e(_rands(w.get("compared_cents", 0)))}</td><td>the comparison</td></tr>'
        f'<tr><td>Lifetime spend, every entry</td><td class="money">'
        f'{_e(_rands(s.get("lifetime_cents", 0)))}</td>'
        "<td>separate figure &mdash; never subtracted from the line above</td></tr>"
        f"{unresolved}</tbody></table></section>"
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
    rows, opts = [], {"year": [], "month": []}
    for i, b in enumerate(buckets):
        hide = "" if i == 0 else ' style="display:none"'
        rows.append(
            f'<tr data-period="{_e(b["key"])}"{hide}>'
            f'<td>{_e(b["label"])}</td>'
            f'<td class="money">{_e(_rands(b["spend_cents"]))}</td>'
            f'<td class="money">{_e(_rands(b["won_cents"]))}</td></tr>'
        )
        opts[b["kind"]].append(
            f'<option value="{_e(b["key"])}">{_e(b["label"])}</option>'
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
        '<p class="muted">By the date of the DRAW, not of the purchase: a '
        "ticket's price is spread over the draws it paid for, so a period's "
        "two figures describe the same draws. Drawn over the same entries as "
        "the comparison below, which is why it starts where the results do "
        "&mdash; earlier periods have nothing that can be scored.</p>"
        '<label>Show <select id="periodfilter">'
        f'<optgroup label="Years">{"".join(opts["year"])}</optgroup>'
        f'<optgroup label="Months">{"".join(opts["month"])}</optgroup>'
        "</select></label>"
        '<table id="periods"><thead><tr><th>Period</th><th>Spent</th>'
        "<th>Won</th></tr></thead><tbody>"
        + "".join(rows)
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
    theme = (
        '<div class="row"><label for="theme">Colour theme</label>'
        f'<select id="theme">{opts}</select></div>'
    )

    return (
        "<section><h2>Settings</h2>"
        + theme
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
        "bg": "#16181d", "fg": "#e8e9ec", "dim": "#9aa0aa", "line": "#2c3038",
        "panel": "#21242b", "accent": "#d8a13a", "warn": "#f0b45a",
        "warn-bg": "#2e2716", "bad": "#e8705f", "bad-bg": "#33201d",
        "on": "#4caf50"}),
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
    'try{var t=localStorage.getItem("lotto-theme");'
    'if(t&&/^[a-z0-9-]{1,32}$/.test(t))'
    'document.documentElement.setAttribute("data-theme",t)}catch(e){}'
)
# Colour is stated once, as the eleven roles above; every rule below reads a
# variable rather than a hex. That is what makes a new theme a table row instead
# of a second copy of this stylesheet.
BASE_CSS = """
body{font:15px/1.5 system-ui,sans-serif;margin:0 auto;padding:1.5rem;max-width:64rem;
 color:var(--fg);background:var(--bg)}
h1{font-size:1.4rem;margin:0 0 .25rem}h2{font-size:1.1rem;margin:2rem 0 .5rem}
h3{font-size:.95rem;margin:1.25rem 0 .4rem;color:var(--dim)}
table{border-collapse:collapse;width:100%;margin:.5rem 0}
th,td{text-align:left;padding:.3rem .5rem;border-bottom:1px solid var(--line)}
th{font-weight:600;font-size:.85rem;color:var(--dim)}
.money{text-align:right;font-variant-numeric:tabular-nums}
.nums{white-space:nowrap}
.ball{display:inline-block;min-width:1.6rem;padding:.1rem .3rem;margin:.05rem .1rem;
 border-radius:.8rem;background:#4a5568;color:#fff;text-align:center;
 font-variant-numeric:tabular-nums;font-size:1rem}
.ball.special{background:#6a1b9a;color:#fff;font-weight:600}
tr[data-game="lotto"] .ball{background:#c62828}
tr[data-game="lotto"] .ball.special{background:#6a1b9a}
tr[data-game="powerball"] .ball{background:#1565c0}
tr[data-game="powerball"] .ball.special{background:#bf360c}
tr[data-game="daily"] .ball{background:#2e7d32}
.notcheckable{color:var(--warn);font-style:italic}
.muted{color:var(--dim);font-size:.9rem}
.notice{background:var(--warn-bg);border-left:4px solid var(--accent);padding:.6rem .8rem;margin:.8rem 0}
.notice.bad{background:var(--bad-bg);border-left-color:var(--bad)}
tr.soon td{background:var(--warn-bg)}tr.today td{background:var(--bad-bg);font-weight:600}
.row{display:flex;align-items:center;gap:.6rem;margin:.4rem 0}
.switch{position:relative;display:inline-block;width:2.6rem;height:1.4rem;flex:none}
.switch input{position:absolute;opacity:0;width:100%;height:100%;margin:0;cursor:pointer}
.slider{position:absolute;inset:0;background:var(--line);border-radius:1rem;transition:.15s;
 pointer-events:none}
.slider:before{content:"";position:absolute;width:1.1rem;height:1.1rem;left:.15rem;
 top:.15rem;background:var(--fg);border-radius:50%;transition:.15s}
.switch input:checked+.slider{background:var(--on)}
.switch input:checked+.slider:before{transform:translateX(1.2rem)}
.switch input:focus-visible+.slider{outline:2px solid var(--accent);outline-offset:2px}
footer{margin-top:2.5rem;color:var(--dim);font-size:.85rem}
button,select{font:inherit;padding:.3rem .7rem;background:var(--panel);color:var(--fg);
 border:1px solid var(--line);border-radius:.25rem}
button:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""

CSS = _themes_css() + BASE_CSS

# Four jobs and no others (LOTTO-0002 §4.1): the two POSTs (custom header, so a
# cross-origin form post cannot forge them), filtering (must never touch the
# URL - INV-21), and polling /status while a build is in flight.
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
 th.addEventListener("change",function(){
  document.documentElement.setAttribute("data-theme",th.value);
  try{localStorage.setItem("lotto-theme",th.value)}catch(e){}
  msg("Theme applied.");
 });
}
var rb=document.getElementById("refresh");
if(rb)rb.addEventListener("click",function(){
 rb.disabled=true;rb.textContent="Refreshing...";
 post("/refresh",null,function(code){
  if(code===202){poll()}
  else{rb.disabled=false;rb.textContent="Refresh results";
       msg(code===409?"A refresh is already running.":"Refresh was declined.")}
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
 msg(t);
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
              msg("That refresh failed - the figures below are from an earlier fetch.");
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
    head = (
        f"<title>{TITLE}</title><style>{CSS}</style>"
        f"<script>{THEME_BOOT}</script>"
    )
    if building and not built:
        # LOTTO-0019 §4.4. The half-minute estimate is KEPT and qualified, not
        # dropped: a retrying build (LOTTO-0012) overshoots it, and an estimate
        # the build silently exceeds is its own small version of a page that
        # looks broken. Same singular rule as the poll, or a first paint at
        # requests == 1 reads "1 lookups so far" until the next tick.
        n = model.get("requests", 0)
        body = (
            f"<h1>{TITLE}</h1>"
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
        body = (
            f"<h1>{TITLE}</h1>"
            + _notice(model)
            + _settings_section(model)
        )
    else:
        body = (
            f"<h1>{TITLE}</h1>"
            + _notice(model)
            + _uncheckable_banner(model.get("uncheckable"))
            + _wins_section(model)
            + _outstanding_section(model)
            + _entries_section(model)
            + _periods_section(model)
            + _spend_section(model)
            + _settings_section(model)
            + "<footer><button id=\"refresh\">Refresh results</button> "
            + (
                f"Last successful build: {_e(built)}."
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
        f"{head}</head><body>{body}<script>{script}</script></body></html>"
    )
