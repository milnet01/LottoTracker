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
    return f"<td>{value}</td>"


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
    live.sort(key=lambda w: w.get("expires") or "")
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
            if d is not None and d <= 0:
                cls, when = "today", "today"
            else:
                when = f"{_e(w.get('expires'))}"
                if d is not None:
                    when += f' <span class="muted">({d} days)</span>'
            rows.append(
                f'<tr class="{cls}"><td>{_e(w["game"])}/{_e(w["plus_flag"])}</td>'
                f'<td>{_e(w.get("division"))}</td><td>{_e(w.get("matched"))}</td>'
                f'<td>{_e(w.get("date"))}</td>'
                f'<td class="money">{_e(_rands(w["amount_cents"]))}</td>'
                f"<td>{when}</td></tr>"
            )
        body = (
            "<table><thead><tr><th>Pool</th><th>Division</th><th>Matched</th>"
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
                f'<tr><td>{_e(e["ref"])}</td>'
                f'<td>{_e(e["game"])}/{_e(e["plus_flag"])}</td>'
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
            "<th>Pool</th><th>Draws remaining</th></tr></thead><tbody>"
            + rows(coming, True)
            + "</tbody></table>"
        )
    if unchecked:
        parts.append(
            f"<h3>Not checkable ({len(unchecked):,} entries)</h3>"
            '<p class="muted">Draws remaining is unknown for these: there is '
            "nothing to measure a window against. They are not losses.</p>"
            "<table><thead><tr><th>Ticket</th><th>Pool</th><th>Why not</th>"
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
    return (
        "<section><h2>Every entry</h2>"
        '<label>Filter by game <select id="gamefilter">'
        f'<option value="">all</option>{opts}</select></label>'
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


def _settings_section(model):
    st = model.get("settings", {})

    def sw(key, label):
        on = " checked" if st.get(key) else ""
        return (
            f'<div class="row"><label class="switch">'
            f'<input type="checkbox" role="switch" id="{key}"{on}>'
            f'<span class="slider"></span></label> {_e(label)}</div>'
        )

    return (
        "<section><h2>Settings</h2>"
        + sw("autostart", "Start the tray when I log in")
        + sw("open_on_start", "Open this page when the tray starts")
        + '<p class="muted" id="settings-msg"></p></section>'
    )


CSS = """
body{font:15px/1.5 system-ui,sans-serif;margin:0 auto;padding:1.5rem;max-width:64rem;
 color:#1a1a1a;background:#fafafa}
h1{font-size:1.4rem;margin:0 0 .25rem}h2{font-size:1.1rem;margin:2rem 0 .5rem}
h3{font-size:.95rem;margin:1.25rem 0 .4rem;color:#444}
table{border-collapse:collapse;width:100%;margin:.5rem 0}
th,td{text-align:left;padding:.3rem .5rem;border-bottom:1px solid #e4e4e4}
th{font-weight:600;font-size:.85rem;color:#555}
.money{text-align:right;font-variant-numeric:tabular-nums}
.notcheckable{color:#8a5a00;font-style:italic}
.muted{color:#666;font-size:.9rem}
.notice{background:#fff8e1;border-left:4px solid #e0a800;padding:.6rem .8rem;margin:.8rem 0}
.notice.bad{background:#fdecea;border-left-color:#c0392b}
tr.soon td{background:#fff8e1}tr.today td{background:#fdecea;font-weight:600}
.row{display:flex;align-items:center;gap:.6rem;margin:.4rem 0}
.switch{position:relative;display:inline-block;width:2.6rem;height:1.4rem;flex:none}
.switch input{position:absolute;opacity:0;width:100%;height:100%;margin:0;cursor:pointer}
.slider{position:absolute;inset:0;background:#bbb;border-radius:1rem;transition:.15s;
 pointer-events:none}
.slider:before{content:"";position:absolute;width:1.1rem;height:1.1rem;left:.15rem;
 top:.15rem;background:#fff;border-radius:50%;transition:.15s}
.switch input:checked+.slider{background:#2d7a2d}
.switch input:checked+.slider:before{transform:translateX(1.2rem)}
.switch input:focus-visible+.slider{outline:2px solid #05f;outline-offset:2px}
footer{margin-top:2.5rem;color:#666;font-size:.85rem}
button{font:inherit;padding:.3rem .7rem}
"""

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
if(gf)gf.addEventListener("change",function(){
 var want=gf.value,rows=document.querySelectorAll("#entries tbody tr");
 for(var i=0;i<rows.length;i++){
  rows[i].style.display=(!want||rows[i].getAttribute("data-game")===want)?"":"none";
 }
});
// Poll while a build is in flight. Without this the opening "building" page
// never leaves that state and /status has no consumer at all. It also has to
// terminate on FAILURE: a failed refresh leaves `built` unchanged, so a poll
// watching only `built` would wait for a change that never comes.
var BUILT=%s;
function poll(){
 var x=new XMLHttpRequest();x.open("GET","/status",true);
 x.onreadystatechange=function(){
  if(x.readyState!==4)return;
  var s={};try{s=JSON.parse(x.responseText)}catch(e){}
  if(s.building){var p=document.getElementById("progress");
                 if(p)p.textContent=s.requests+(s.requests===1?" lookup":" lookups")+" so far.";
                 setTimeout(poll,2000);return}
  if(s.built&&s.built!==BUILT){location.reload();return}
  if(s.stale){var b=document.getElementById("refresh");
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
        if True
        else ""
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
            f'<span id="progress">{n} {"lookup" if n == 1 else "lookups"} '
            "so far.</span></div>"
        )
    else:
        body = (
            f"<h1>{TITLE}</h1>"
            + _notice(model)
            + _uncheckable_banner(model.get("uncheckable"))
            + _wins_section(model)
            + _outstanding_section(model)
            + _entries_section(model)
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
        json.dumps(token),
        json.dumps(built),
        "true" if building else "false",
    )
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"{head}</head><body>{body}<script>{script}</script></body></html>"
    )
