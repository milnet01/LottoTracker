# LOTTO-0014 — HTTP surface and security boundary for the local page

**Status:** spec draft (2026-08-02).
**Kind:** security.
**Source:** ROADMAP LOTTO-0014 — split out of LOTTO-0002 on 2026-08-02, second
cut. The security constraints were researched with the user on 2026-08-01 and
recorded on the LOTTO-0002 roadmap bullet; §3 records what was decided rather
than deduced.

**Pairs with:** LOTTO-0002 (the model, the build lifecycle and what the page
shows) and LOTTO-0013 (the tray and supervisor). All three ship together and
share one test script.

*Layman: the rules that stop a website you happen to be visiting from reading
your lottery tickets off the page running on your own machine.*

## 1. Goal

After this ships, `serve.py` answers exactly four routes and nothing else; a
request whose `Host` header is not one this server serves gets a bare 421; a
POST that changes anything must carry a secret only the real page was given;
nothing a caller sends is ever echoed into a response header or a written file;
and no ticket detail leaves the machine through a URL, a page title or a cache.

## 2. Problem

`serve.py` holds every ticket the user owns, in memory, on a TCP port. A
`127.0.0.1` bind stops the *network* reaching it. It does not stop the user's
own browser being aimed at that port by a page they are merely visiting, and the
browser is inside the loopback boundary.

Three consequences, and the first is not hypothetical:

1. **DNS rebinding turns a localhost bind into an open door.** A hostile site
   resolves its own name to 127.0.0.1 after the page loads, then issues requests
   the browser regards as same-origin. This is CVE-2026-46611 — Glances, a
   localhost XML-RPC server with no `Host` validation, exfiltrated exactly this
   way: hostname, the full process list with credentials visible in argv, and
   open ports. (Called *the CVE* below.)
   *Source: https://github.com/nicolargo/glances/security/advisories/GHSA-w856-8p3r-p338*
2. **The page has write routes, so read-only reasoning does not apply.**
   LOTTO-0002 §4.7's settings panel gives the server a state-changing endpoint
   that writes a file into `~/.config/autostart/`. A design that only had to
   protect *reads* could stop at the `Host` check; this one cannot.
3. **Each defence here has a plausible-looking way to be weakened during
   implementation**, and each was found that way in review rather than by
   reasoning: exempting `/refresh` so the tray's menu item works, adding a CORS
   header while debugging the page's own `fetch()`, checking `Origin` instead of
   `Host` because it reads like the modern answer. §4 names each as forbidden
   rather than leaving it to judgement.

## 3. Scope decisions

**Researched and agreed with the user 2026-08-01, recorded on the LOTTO-0002
roadmap bullet — not re-litigated here:** bind `127.0.0.1` and validate `Host`
against an exact allowlist, rejecting anything else with 421; subclass
`BaseHTTPRequestHandler` and render in memory rather than serving files;
`ThreadingHTTPServer`; `Cache-Control: no-store`; a generic `<title>` and no
ticket data in the URL; and never pass request-derived data to `send_header()`.

**Taken with the user 2026-08-02:** the start-at-login toggle lives on the page
rather than in the tray menu, which is what gives this server a write endpoint
at all and therefore what makes §4.3's token necessary. The tray-menu
alternative would have left the HTTP surface read-only; the user chose the panel
knowing that (LOTTO-0002 §3 records the same decision from the page's side).

**Taken as part of the second split, 2026-08-02:** this document owns INV-12,
INV-13, INV-14 and INV-21. LOTTO-0002 keeps INV-15 to INV-18; LOTTO-0013 holds
INV-19 and INV-20.

## 4. Design

### 4.1 The four routes, and the routing floor

Four routes, and nothing else — every other path is 404.

| Method | Path | Returns | Changes state |
|---|---|---|---|
| GET | `/` | the page (HTML) | no |
| GET | `/status` | `{"building": bool, "built": "<ISO>"\|null, "stale": bool}` | no |
| POST | `/refresh` | 202 accepted, or 409 if one is already running | results only |
| POST | `/settings` | 200 + the settings as now stored | writes LOTTO-0002 §4.7's two files |

`POST /settings` takes `{"autostart": bool, "open_on_start": bool}` as JSON and
returns the same shape **re-read from disk after writing**, not the request
echoed back — so a switch that failed to apply snaps back to the truth rather
than showing what was asked for. Both keys are optional; an absent key leaves
that setting alone, and `{}` is valid — a no-op returning 200 with the settings
unchanged. A body that is not an object of those two keys with boolean values is
400, and nothing is written. `POST /refresh` takes no body.

Any other path is **404**; a known path with the wrong method is **405** with an
`Allow` header **drawn from a fixed per-path table**, never assembled from the
request — it is the one header whose value varies by route, which is exactly the
shape INV-14 forbids building out of anything a caller sent.

`SimpleHTTPRequestHandler` is not used and no path from a request is ever
joined to a filesystem path; the handler subclasses `BaseHTTPRequestHandler`
and every response body is built in memory. That removes path traversal as a
class rather than defending against it. `ThreadingHTTPServer`, because browsers
pre-open sockets they do not send on and a single-threaded server hangs on them.

### 4.2 Host allowlist, and why `Origin` is not a substitute

**Host allowlist, exact match, 421 otherwise.** The allowlist is
`{"127.0.0.1:<port>", "localhost:<port>"}`, compared as whole strings — not a
prefix, suffix or substring test, each of which `evil.example:4322` or
`127.0.0.1.evil.example` defeats. A non-matching `Host` gets `421 Misdirected
Request` and no body. This is exactly the CVE in §2; Glances answers 400, and 421
is used here because it is the status that means "this host is not one I serve",
a distinction that matters when reading a log.

The port in that allowlist is the one `serve.py` bound, read once from
`LOTTO_PORT` (LOTTO-0013 §4.5 owns the variable). A server and a caller
disagreeing about the port fail as a 421 on every request — the allowlist
rejecting the very URL that was just opened.

`localhost:<port>` is allowlisted alongside the numeric form because that is
what a user types, even though the socket binds `127.0.0.1` only; on a host
whose resolver answers `localhost` with `::1` first, the browser fails to
connect at all rather than reaching a server that then rejects it — a broken
link, not a hole. The tray always opens the numeric URL, so its own path is
unaffected.

The response is the bare status line with no body. `421` is sent as the integer
rather than through `HTTPStatus.MISDIRECTED_REQUEST`, so the code does not
depend on when that constant entered the standard library — README.md claims a
Python 3.8 floor and this is not the place to test it.

**`Origin` is not a substitute and is not accepted as one.** A top-level
navigation carries no `Origin` header, so any rule that trusts its absence
admits the rebinding case unchanged. `Origin` is checked *in addition* on the
two POST routes and never instead, with an explicit rule for absence:

| `Origin` on a POST | Result |
|---|---|
| exactly `http://127.0.0.1:<port>` or `http://localhost:<port>` | allowed |
| present, any other value | 403 |
| **absent** | **allowed** — §4.3's token is what covers this case |

Absent must be allowed or the tray's own `urllib` POST is rejected, and a rule
that broke the Refresh menu item would be quietly deleted by the first person
to hit it. That is why the token, not `Origin`, is the load-bearing defence.

### 4.3 The per-run token on every state-changing request

`secrets.token_urlsafe(32)`, embedded in the page and required back in an
`X-Lotto-Token` header. Two properties: a custom header cannot be set by a
cross-origin form post, and a page that never received the token cannot guess
it. A POST without the exact token returns 403 and changes nothing, and the
comparison is `secrets.compare_digest`, not `==`. INV-13.

**A caller that spawns the server passes the token in, and `serve.py` accepts it
from exactly one place:**

```python
# serve.py
token = os.environ.get("LOTTO_TOKEN") or secrets.token_urlsafe(32)
```

This is not optional, and it is not a convenience. LOTTO-0013 §4.3 gives the
tray a *Refresh results now* item, which is a `POST /refresh`, and the token is
generated inside a process the tray only spawns. Left unstated, an implementer
resolves it by exempting the tray — which deletes the defence this section is
built on. That was one of three CRITICALs both lanes found in the parent
document's first review loop. LOTTO-0013 §4.2 owns the minting, the spawn and
the reasoning for the environment rather than argv or a file; what belongs here
is the line above, and the rule that a standalone `serve.py` with no
`LOTTO_TOKEN` mints its own so the headless case is unchanged.

**The token is not a model key.** `page.py`'s signature is `render(model,
token)`: the model is what the test fixtures are built to (LOTTO-0002 §4.1), and
a token living in it would be copied into every fixture and would leak into
anything that serialises a model. The renderer embeds it; INV-13's case asserts
the rendered page carries it, because a page without it 403s on every toggle
while every other case still passes.

### 4.4 Response headers, and what may never appear in one

**Every response carries `X-Frame-Options: DENY` and
`Content-Security-Policy: frame-ancestors 'none'`.** Without them the token
defends against a *forged* request and not against a real one: a hostile page
can `<iframe src="http://127.0.0.1:4322">`, the `Host` header is the allowlisted
value so the frame renders, and the framed page carries the token in its own
DOM. Every defence above survives that, and the user still clicks the autostart
switch of LOTTO-0002 §4.7 through an invisible overlay. Framing is the hole a `Host`
allowlist and a token cannot see, so it is closed here rather than left to the
implementer to notice. INV-12.

**No `Access-Control-Allow-*` header is ever sent, on any route, including
errors.** One such header hands a hostile origin the ability to *read* the
response, which defeats the `Host` allowlist, the same-origin policy and the
token together. It is a plausible thing to add while debugging the page's own
`fetch()` calls — which are same-origin and need no CORS — so it is named here
as forbidden rather than left to judgement. INV-12.

**No request-derived data reaches a response header or a written file.** Header
values come from a fixed table of literals; `send_header()` is never called with
anything derived from the request, which removes header injection (Python's
`BaseHTTPRequestHandler` does not validate CRLF in header values). The
`.desktop` file `POST /settings` writes is built entirely from constants and a
path derived from the server's own location; the only thing a request can
influence is **whether it exists**, never its contents. The only request-derived
values ever written are §4.1's two validated booleans. INV-14.

**That file names `tray.py`, not the module that writes it.** The writer is
`serve.py` — `POST /settings` is a server route — so `os.path.abspath(__file__)`
resolves to the *server*, while the setting is "start the **tray** at login".
Built from `__file__` directly, the switch would autostart a headless server and
no icon would ever appear, and §11 records that nothing mechanical catches a
wrong autostart. **LOTTO-0002 §4.7 gives the file's bytes verbatim and is the
only place that does** — INV-14 asserts them byte-for-byte, so a second copy
here would be a second contract to disagree with.

**Nothing about a ticket leaves in a URL, a title or a cache.** No ticket
reference, number, amount or date appears in a URL or a query string, the
`<title>` is the constant `Lotto Tracker`, and every response carries
`Cache-Control: no-store`. Browsers sync history and titles to a vendor account
and offer them to search suggestions; a URL is the one part of a local page that
routinely escapes the machine. INV-21. This is the same rule
`tools/verify_privacy.py` enforces for the repository, applied to the other
exit.

That rule binds the renderer as well as the server: LOTTO-0002 §4.5's ticket
filtering is client-side over rows already in the document, and must not add a
query parameter, a fragment or a `history.pushState()` entry. The URL is the
same string before and after every interaction with the page.

## 5. Invariants

This document holds INV-12, INV-13, INV-14 and INV-21. LOTTO-0001 holds INV-1
to INV-6, LOTTO-0009 INV-7 to INV-11, LOTTO-0002 INV-15 to INV-18, and
LOTTO-0013 INV-19 and INV-20. The numbers did not move in either split —
CHANGELOG.md and sibling specs cite them unqualified.

- **INV-12** — A request whose `Host` header is not exactly `127.0.0.1:<port>`
  or `localhost:<port>` is answered 421 and served no body; a request with a
  correct `Host` is answered normally.
  *Test:* `tools/verify_page.py`, case `host_allowlist` — four `Host` values: a
  good one (expect 200), `evil.example:4322` (421),
  `127.0.0.1.evil.example:4322` (421, the suffix-test trap), and **no `Host`
  header at all** (421). The good request is what stops the case passing
  against a server that answers 421 to everything.
  **Each of the four is fired at `GET /`, at `GET /status` and at a POST route**,
  because a `Host` check written into `do_GET` alone passes a `GET /`-only case
  while leaving both write routes reachable from a rebound origin. The allowlist
  is the stated first line of defence; a case that only proves it for one method
  has not proved it. The same case asserts, on every one of the four responses,
  that no `Access-Control-Allow-*` header is present and that both
  `X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'`
  are.
  *Breaks when:* the check becomes a substring or suffix test, admitting
  `127.0.0.1.evil.example`; the header is absent and treated as trusted; or a
  CORS header is added while debugging the page's own `fetch()` calls, which
  would let a hostile origin read what the allowlist stopped it reaching.

- **INV-13** — A POST to `/settings` or `/refresh` without the run's exact
  token returns 403 and changes nothing on disk.
  *Test:* `tools/verify_page.py`, case `token_required` — five POSTs, all with
  a valid `Host`: no token (403), a wrong token (403), a wrong `Origin` with the
  right token (403, §4.2's table), the right token with no `Origin` (accepted —
  the tray's own case), and the right token with `Origin: http://127.0.0.1:<port>`
  (accepted — the browser's own case, and the row that stops a handler which
  403s *every* present `Origin` from passing while every in-page toggle fails).
  **The wrong token is a proper prefix of the real one**, so `startswith` is
  actually caught; a random wrong token passes a `startswith` implementation.
  The case also asserts the rendered page contains the run token, since a
  renderer that never embeds it (§4.3) 403s every toggle while all ten cases
  otherwise pass.
  **Every one of them is fired at both `/settings` and `/refresh`.** The
  *Breaks when* below names exempting `/refresh` as the likeliest breach, so a
  case that only ever POSTs to `/settings` cannot catch the very failure it is
  written for. "Changes nothing" is observed per route: for `/settings`, the
  autostart file is byte-identical; for `/refresh`, the stub builder's call
  count is unchanged.
  The valid `Host` is what isolates this rule: with a bad one INV-12 answers 421
  first and the case passes without the token check existing at all.
  The same case spawns a child with `LOTTO_TOKEN` in its environment and
  asserts that token is accepted — the §4.3 channel the tray depends on, which
  would otherwise be the one link in the chain nothing exercises.
  *Breaks when:* the token is compared with `startswith`, read from a query
  string (where it lands in browser history), or checked on `/settings` only.
  (`==` instead of `secrets.compare_digest` is a real defect and **not** one
  this or any black-box case can observe — the two agree on every input and
  differ only in timing. It is a code-review item, and §11 records that nothing
  mechanical catches it.) The likeliest breach is not a coding slip but §4.3's
  tray problem resolved the wrong way — exempting `/refresh` so the tray's menu
  item works, which removes the defence for the one route that re-fetches.

- **INV-14** — No request-derived **string** reaches a response header or a
  written file. The only request-derived values ever written are §4.1's two
  validated booleans; the `.desktop` file's contents are constant.
  *Test:* `tools/verify_page.py`, case `no_reflected_headers` — the poison is
  **percent-encoded** (`/a%0d%0aX-Injected:+yes`), not raw, and the `Host`
  header is valid on every request. The case **first issues a valid
  `POST /settings {"autostart": true}` with the run token**, so the `.desktop`
  file exists to be asserted about — a poisoned path is not `/settings`, it
  404s, and nothing would be written for the assertion to have a subject. It
  then asserts no `X-Injected` header appears in any response, and that the
  file is byte-identical afterwards. It asserts the file's content outright
  against LOTTO-0002 §4.7's listing, not merely that it did not change: the
  `Exec` line must name `tray.py`. Byte-equality alone passes a file that has
  been wrong since it was first written — which is exactly §4.4's `__file__`
  trap, where the constant content is the bug.
  Two ways this case can test nothing, both measured on Python 3.13 rather than
  reasoned about: put the payload in `Host` and INV-12 answers 421 first, so it
  passes against a server with no header hygiene at all. Send **raw** CRLF and
  the request line is simply truncated — the handler receives path `/a`, the
  injected line is swallowed as a malformed header, and the response is a
  perfectly ordinary `200`. Nothing reaches the code under test, and the case
  passes for that reason. Only the percent-encoded form arrives intact:
  `self.path` is literally `/a%0d%0aX-Injected:+yes`, which is what a handler
  that decodes and reflects would turn into a header.
  *Breaks when:* an error page echoes the requested path into a header, or the
  `.desktop` file gains a field built from a request.

The gap between INV-14 and INV-21 is the split, not an omission:

- **INV-15** — *moved to LOTTO-0002*
- **INV-16** — *moved to LOTTO-0002*
- **INV-17** — *moved to LOTTO-0002*
- **INV-18** — *moved to LOTTO-0002*
- **INV-19** — *moved to LOTTO-0013*
- **INV-20** — *moved to LOTTO-0013*

- **INV-21** — No ticket data appears in any URL, fragment or page `<title>`,
  and every response carries `Cache-Control: no-store`.
  *Test:* `tools/verify_page.py`, case `nothing_in_the_url` — asserts `GET /`
  serves a byte-identical body with and without a query string appended, and
  that `GET /status` returns the same JSON key set and the same `stale` value
  either way (its `built` and `building` legitimately move between calls, so
  byte-equality there would be flaky rather than strict). It asserts the
  constant `Lotto Tracker`, that `no-store` is on all four responses, and that
  the page's inline script contains no `pushState`, `replaceState` or
  `location.hash` assignment. It also asserts §4.1's routing floor — an unknown
  path is 404 and a known path with the wrong method is 405 — since both are
  responses that must name nothing from the request.
  *Breaks when:* filtering is implemented as `/?game=lotto&ref=…`, the natural
  first implementation, which writes a ticket reference into browser history —
  or as a `#ref=…` fragment, which looks safer and is not: the fragment is in
  the URL the browser stores and syncs, it is merely not sent to the server.

## 6. Failure modes

- **A tab left open across a server restart holds a stale token.** The token is
  per process, not per page — so every tab of one run shares one token, and a
  tab that outlives the run holds one nothing will accept. Its next toggle gets
  a 403, which renders as "this page is from an earlier session — reload it",
  not as a failure of the setting. LOTTO-0013 §4.1 mints a fresh token per
  server start, which is what makes this the behaviour rather than an accident.
- **A write fails after the request validated.** `POST /settings` returns 500
  with the reason and leaves the switch showing its true state, not the
  requested one — which is the same rule as the success path's re-read from
  disk (§4.1).
- **A request arrives with no `Host` header at all.** Treated as a non-match:
  421. HTTP/1.1 requires the header, and the absent case is the one a hand-rolled
  client or a rebinding proxy produces; trusting absence is the failure INV-12's
  fourth `Host` value exists to catch.
- **A browser strips the custom header.** No such browser is known. The failure
  would be a 403 on every toggle — loud and immediate, not silent — and §11
  records that nothing checks it.

## 7. Tests

This document's four cases live in `tools/verify_page.py`, the script
LOTTO-0002 §7 introduces — **one script for all three parts of the split**,
joining `tools/verify_privacy.py`, `tools/verify_sources.py`,
`tools/verify_coverage.py` and `tools/verify_pools.py`. Exit code is the signal,
as with the other four.

| Case | Locks |
|---|---|
| `host_allowlist` | INV-12 |
| `token_required` | INV-13 |
| `no_reflected_headers` | INV-14 |
| `nothing_in_the_url` | INV-21 |

LOTTO-0002 §7 holds the three constraints that bind all ten cases — no network,
no real data, and recomputing rather than importing the judgement under test.
Two of them bear on these four specifically:

- **All four run against a real socket**, because every one of them asserts on
  request or response framing that only an HTTP server produces. They use the
  stub-builder seam so the model behind the page costs nothing to build, but the
  server itself is real.
- **`$HOME` and `$XDG_CONFIG_HOME` both point at a temporary directory.**
  `no_reflected_headers` writes a real `.desktop` file and asserts its bytes;
  without both variables redirected it writes into the developer's own
  `~/.config/autostart/`, which is a test that changes the system it measures.

**Each case is observed failing before the invariant is accepted.** There is no
pre-fix code here — this is greenfield — so the equivalent of LOTTO-0009 §7's
red-test is to break the rule deliberately, confirm the case fails, then
restore. For these four: widen the `Host` comparison to `endswith`; drop the
token check on `/refresh` alone; reflect `self.path` into a response header;
serve the page with a `<title>` built from a query parameter. A case never seen
failing is a case that proves nothing, and on a greenfield spec that is the
*only* way to know it can fail at all.

## 8. Alternatives considered (and rejected)

- **`Origin` checking instead of `Host`.** Rejected on evidence: a top-level
  navigation sends no `Origin`, so the rebinding case passes a check that trusts
  its absence. Kept as an additional check on POSTs (§4.2).
- **`SimpleHTTPRequestHandler` serving a directory.** Rejected: it reintroduces
  path traversal as a class, for the convenience of not writing four routes.
- **A localhost bind and nothing else**, which is what most local dev servers
  do. Rejected on the CVE in §2 — it is the precise shape of this design without
  a `Host` check, and it was exploited.
- **Exempting the tray's `POST /refresh` from the token**, the shape an
  implementer reaches for when the tray cannot obtain the token. Rejected: it
  removes the defence for the one route that re-fetches, and §4.3 specifies the
  channel instead so the shortcut is never needed.
- **A token in a query string or a cookie** rather than a custom header.
  Rejected: a query string lands in browser history, which INV-21 forbids; a
  cookie is sent automatically by the browser on a cross-origin form post, which
  is exactly the property the custom header is chosen for.

## 9. Out of scope

- The model, the refresh lifecycle and what the page renders — LOTTO-0002.
- The tray, the supervisor and the headless contract — LOTTO-0013.
- Authentication of any kind beyond the per-run token. The server has one user,
  the one who owns the process.
- Serving to any host but the loopback interface, now or later.
- TLS. A loopback socket has no transport to protect, and a self-signed
  certificate would train the user to click through a warning.

## 10. Resource cost

- **Memory:** none of its own. The allowlist is two strings; the token is 43
  characters.
- **Network:** none. Every rule here is applied to requests that already
  arrived.
- **Disk:** the `.desktop` file and `settings.json`, both written by
  LOTTO-0002 §4.7 and counted there.
- **Dependencies:** none — `http.server` and `secrets`, both standard library.

## 11. What checks this

| Rule | What catches a breach |
|------|----------------------|
| INV-12 Host allowlist | `tools/verify_page.py::host_allowlist` |
| INV-13 token on writes | `tools/verify_page.py::token_required` |
| INV-14 no reflected data | `tools/verify_page.py::no_reflected_headers` |
| INV-21 nothing in the URL | `tools/verify_page.py::nothing_in_the_url` |
| §4.2 `Origin` rule on POSTs, incl. absent-is-allowed | `tools/verify_page.py::token_required` |
| §4.3 the tray's `LOTTO_TOKEN` channel | `tools/verify_page.py::token_required` — a child spawned with the variable accepts that token |
| §4.1 404 / 405 routing floor | `tools/verify_page.py::nothing_in_the_url` |
| §4.4 anti-framing headers on every response | `tools/verify_page.py::host_allowlist` |
| §4.4 the `.desktop` `Exec` naming `tray.py`, not the writing module | `tools/verify_page.py::no_reflected_headers` — LOTTO-0002 §4.7's body is asserted byte-for-byte |
| §4.3 `secrets.compare_digest` rather than `==` | **nothing** — the two agree on every input and differ only in timing, so no black-box case can tell them apart; code review only |
| §4.3 the token surviving a browser that strips custom headers | **nothing** — no such browser is known, and the failure is visible (403 on every toggle) rather than silent |

Eleven rows, two `nothing`.

## 12. Cross-doc impact

- `docs/specs/LOTTO-0002-local-web-page.md` — the parent of this split; its
  §4.3 and §4.4 became pointers here, and it lost INV-12, 13, 14 and 21.
- `docs/specs/LOTTO-0013-tray-and-supervisor.md` — unchanged by this cut. Its
  §4.2 owns the token's minting and the environment channel this document's
  §4.3 receives.
- `README.md` — the page section notes the port and that the server answers
  only the loopback interface. Written once, with LOTTO-0002.
- `CHANGELOG.md` — a `Security` entry citing LOTTO-0014, separate from
  LOTTO-0002's `Added` entry, because Keep a Changelog separates the two and
  this half is the security surface.
- `ROADMAP.md` — LOTTO-0014's bullet flips to shipped.

## 13. Cold-eyes loop log

| Loop | Date | Lanes | CRIT | HIGH | MED | LOW | Outcome |
|------|------|-------|------|------|-----|-----|---------|
| 0-split | 2026-08-02 | — | — | — | — | — | **Provenance row — no reviewer was dispatched, and this is not a review loop.** Second cut of `docs/specs/LOTTO-0002-local-web-page.md`, taken by the user on 2026-08-02 after the first cut (LOTTO-0013, the tray) removed only 66 of 1,161 lines and left the page half at 1,095. The seam here is subject rather than invariant count: this document is the web-security boundary — the routes, the `Host` allowlist, the token and the response-header rules — and what remains in LOTTO-0002 is the lottery-data honesty rules. They need different expertise to review, which is the argument for the cut. Carried over unchanged in substance: the parent's §4.3 (now §4.1) and §4.4 (now §4.2–§4.4), and INV-12, INV-13, INV-14 and INV-21 with their test clauses. **The parent's three cold-eyes loops confer nothing on this document** — they were run against 1,161 lines that no longer exist, and this file starts at loop 1 on its own bytes. Their record is archived at `docs/specs/LOTTO-0002-pre-split-review-log.md`. Two edits were made rather than copied: INV-13's test clause said "four POSTs" while listing five, corrected here to five; and the parent's §4.4 carried three bare references to "§4.7", a section that now lives in another document, all three of which are qualified here. The last of them survived the first qualifying pass and was caught by a mechanical cross-reference sweep rather than by reading. |
