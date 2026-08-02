# LOTTO-0014 — HTTP surface and security boundary for the local page

**Status:** accepted (2026-08-02) — three cold-eyes loops, converged by cap
and by the collateral trigger; 78 verified findings fixed, 0 deferred. See §13.
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
request whose `Host` header is not one this server serves gets a 421 with no
body; a POST that changes anything must carry a secret only the real page was
given; no caller-supplied **string** is ever echoed into a response header or a
written file;
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
   reasoning: exempting `/refresh` (§4.3), adding a CORS header (§4.4), checking
   `Origin` instead of `Host` (§4.2). §4 names each as forbidden rather than
   leaving it to judgement, because each is the *cheap* way out of a real problem
   the implementer will actually hit.

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
INV-13, INV-14 and INV-21; §5 maps the rest.

## 4. Design

### 4.1 The four routes, and the routing floor

Four routes, and nothing else — every other path is 404.

| Method | Path | Returns | Changes state |
|---|---|---|---|
| GET | `/` | the page (HTML) | no |
| GET | `/status` | `{"building": bool, "built": "<ISO>"\|null, "stale": bool}` | no |
| POST | `/refresh` | 202 accepted, or 409 if one is already running | results only |
| POST | `/settings` | 200 + the settings as now stored | writes or removes LOTTO-0002 §4.7's two files |

`POST /settings` takes `{"autostart": bool, "open_on_start": bool}` as JSON and
returns the same shape **re-read from disk after writing**, not the request
echoed back — so a switch that failed to apply snaps back to the truth rather
than showing what was asked for. Both keys are optional; an absent key leaves
that setting alone, and `{}` is valid — a no-op returning 200 with the settings
unchanged. A body that is not an object of those two keys with boolean values is
400, and nothing is written. `POST /refresh` takes no body.

**The body rules below apply to `POST /settings` only.** `POST /refresh` takes
no body and is accepted with `Content-Length: 0` or with the header absent
entirely — which is what a bodiless `urllib` POST sends, and therefore what
LOTTO-0013 §4.1's `post()` sends. A rule that 400'd a missing `Content-Length`
on every route would break the tray's Refresh item: the same failure §4.3's
token channel exists to prevent, arriving through validation instead.

**`POST /settings`'s body is read bounded, never `rfile.read()` to EOF.** At
most `Content-Length` bytes and at most **4 KiB**; a declared length above that
is **413** and nothing is read past the cap, and a missing, non-numeric or
negative `Content-Length` is **400**. **The socket carries a read timeout**
(`timeout` on the handler), because reading exactly `Content-Length` bytes hangs
just as completely when a client declares 4000 and sends 1 — a cap on size is
not a cap on time. A body that under-delivers against its declared length is
closed rather than waited on. The two settings are two booleans, so 4 KiB is
generous by three orders of magnitude — the cap exists because an unbounded read
on a local socket is a hang, and because the obvious implementation
(`self.rfile.read()`) is the one that has it.

**Every response's exact header set is fixed by its shape**, which is what
INV-14's name-set assertion is written against. `Server` and `Date` are emitted
by `BaseHTTPRequestHandler.send_response()` whether or not the handler asks for
them — measured — so they are named here rather than discovered by a failing
test. **`Server` is overridden to the constant `lotto`**: the default is
`BaseHTTP/0.6 Python/3.13.14`, a version fingerprint of both the server and the
interpreter, which is not something a security boundary should volunteer.

| Response | Header set |
|---|---|
| `200` on `GET /` | `Server`, `Date`, `Content-Type: text/html; charset=utf-8`, `Content-Length`, + the three below |
| `200` on `GET /status`, `POST /settings` | `Server`, `Date`, `Content-Type: application/json`, `Content-Length`, + the three below |
| `202` / `409` on `POST /refresh` | `Server`, `Date`, `Content-Length: 0`, + the three below |
| `400` / `403` / `413` / `500` | `Server`, `Date`, `Content-Length: 0`, + the three below |
| `404` | `Server`, `Date`, `Content-Length: 0`, + the three below |
| `405` | as `404`, plus `Allow` from the fixed per-path table |
| `421` | `Server`, `Date`, `Content-Length: 0`, + the three below |

"the three below" is `X-Frame-Options: DENY`,
`Content-Security-Policy: frame-ancestors 'none'` and `Cache-Control: no-store`,
which §4.4 puts on **every** response without exception. No response carries any
header outside its row.

**Checks run in a fixed order, and the first failure answers.** No later check
runs, and no earlier one is skipped:

```text
1. Host allowlist        -> 421   (§4.2)
2. path + method         -> 404 / 405
3. token, on POSTs       -> 403   (§4.3)
4. Origin, on POSTs      -> 403   (§4.2)
5. Content-Length + body -> 400 / 413
```

The order is load-bearing rather than arbitrary, and it was previously stated
only inside a test note. INV-12 fires poisoned hosts at both POST routes and
expects 421; an implementer who checked the token first would answer 403 to
every one of them and fail a case written against a correct server. Host-first
is also what keeps a rebound origin from learning anything about which paths
exist.

**Routing matches the path component only**, with the query string split off and
discarded — `/?game=lotto` routes to `/`, not to 404. Saying so matters for
INV-21, whose case fetches `/` twice, with and without a query, and compares the
bodies: under the other reading both fetches would 404 with an empty body and the
comparison would pass against a server that renders nothing at all.

Any other path is **404**; a known path with the wrong method is **405** with an
`Allow` header **drawn from a fixed per-path table**, never assembled from the
request — it is the one header whose value varies by route, which is exactly the
shape INV-14 forbids building out of anything a caller sent.

`SimpleHTTPRequestHandler` is not used and no path from a request is ever
joined to a filesystem path; the handler subclasses `BaseHTTPRequestHandler`
and every response body is built in memory. That removes path traversal as a
class rather than defending against it. `ThreadingHTTPServer`, because browsers
pre-open sockets they do not send on and a single-threaded server hangs on them.

**`POST /settings` therefore holds a lock across its write and its re-read.**
The server is threaded, the route writes two files and then re-reads them to
build its response (§4.1), and two concurrent toggles without a lock can each
return the other's result — a switch that snaps to a value the user did not
choose, which is the exact failure the re-read was introduced to prevent.
LOTTO-0002 §4.2 puts the model behind one lock for the same reason; this is the
file half of it.

### 4.2 Host allowlist, and why `Origin` is not a substitute

**Host allowlist, exact match, 421 otherwise.** The allowlist is
`{"127.0.0.1:<port>", "localhost:<port>"}`, compared as **whole, lowercased
strings**. Each weaker comparison has its own defeating value, and they are
different values — which is why INV-12's case carries one of each rather than
one representative:

| Weaker comparison an implementer might write | `Host` that defeats it |
|---|---|
| `host.startswith("127.0.0.1")` | `127.0.0.1.evil.example:<port>` |
| `host.endswith("127.0.0.1:<port>")` | `evil.example.127.0.0.1:<port>` |
| `"127.0.0.1" in host` | either of the above |
| `host.endswith(":<port>")` — port-only | `evil.example:<port>` |
| trusting an absent `Host` as "must be local" | no `Host` header at all |

Comparison is on the lowercased header, because `Host: LOCALHOST:4322` is legal
HTTP and a case-sensitive match would 421 a request a user's own browser can
make. A `Host` with no port at all is a non-match and gets 421: the allowlist
entries both carry one. A non-matching `Host` gets `421 Misdirected
Request` and no body. This is exactly the CVE in §2; the Glances fix answers
400, and 421
is used here because it is the status that means "this host is not one I serve",
a distinction that matters when reading a log.

The port in that allowlist is the one `serve.py` bound, read once from
`LOTTO_PORT`. LOTTO-0013 §4.5 owns that variable and states what a disagreement
about it costs.

`localhost:<port>` is allowlisted alongside the numeric form because that is
what a user types, even though the socket binds `127.0.0.1` only; on a host
whose resolver answers `localhost` with `::1` first, the browser fails to
connect at all rather than reaching a server that then rejects it — a broken
link, not a hole. The tray always opens the numeric URL, so its own path is
unaffected.

The response carries **no body**, and it is not a bare status line: like every
other response it carries `X-Frame-Options: DENY`,
`Content-Security-Policy: frame-ancestors 'none'` and `Cache-Control: no-store`.
A 421 is the most-served response in the attack this section is about, and it is
exactly the response a hostile page would frame, so dropping the anti-framing
headers from it would defeat the defence on the one response that most needs
it.

`421` is written as the integer rather than `HTTPStatus.MISDIRECTED_REQUEST`
purely as a style choice. **The constant is not a portability risk** — it has
been in `http.HTTPStatus` since Python 3.5, well below the 3.8 floor README.md
and CLAUDE.md assert — so nothing here turns on avoiding it.

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
built on. LOTTO-0013 §4.2 owns the minting, the spawn and
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
can `<iframe src="http://127.0.0.1:<port>">`, the `Host` header is the
allowlisted value so the frame renders as a fully authorised page. The hostile
page **cannot read** that frame — it is cross-origin to it — and that is not the
attack: it can position it invisibly and let the user click the autostart switch
of LOTTO-0002 §4.7 through an overlay. Every defence above survives, because
every request the frame makes is genuine. Clickjacking is the hole a `Host`
allowlist and a token cannot see. Framing is the hole a `Host`
allowlist and a token cannot see, so it is closed here rather than left to the
implementer to notice. INV-12.

**No `Access-Control-Allow-*` header is ever sent, on any route, including
errors.** One such header hands a hostile origin the ability to *read* the
response, which defeats the `Host` allowlist, the same-origin policy and the
token together. It is a plausible thing to add while debugging the page's own
`fetch()` calls — which are same-origin and need no CORS — so it is named here
as forbidden rather than left to judgement. INV-12.

**The access log is silenced**, which is both why this server writes no
request-derived text anywhere and why it does not spam the terminal it was
launched from. `BaseHTTPRequestHandler.log_request` passes `self.requestline` —
a request-derived string — to `log_message`, which writes it to stderr; under
the tray that stderr is inherited, and under a systemd unit it lands in the
journal. `log_message` is overridden to a no-op. INV-14 is scoped to response
headers and the files §4.1 writes, and this is the paragraph that makes that
scope honest rather than an omission.

**No request-derived string reaches a response header or a written file.** Header
values come from a fixed table of literals; `send_header()` is never called with
anything derived from the request, which removes header injection (Python's
`BaseHTTPRequestHandler` does not validate CRLF in header values). The
`.desktop` file `POST /settings` writes is built entirely from constants and a
path derived from the server's own location; the only thing a request can
influence **about that file** is whether it exists, never its contents.
(`settings.json` is the other file, and a request does influence its contents —
to exactly **one** validated boolean, `open_on_start`. The autostart setting has
no key at all: LOTTO-0002 §4.7 stores it as the *presence* of the `.desktop`
file, precisely so the switch cannot drift from what the desktop actually does.
Writing an `autostart` key into `settings.json` would create the duplicated
state that decision exists to prevent. This is why INV-14 is scoped to
request-derived *strings*.) The only request-derived
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
  or `localhost:<port>` (lowercased, whole-string) is answered 421 and served no
  body; a request with a correct `Host` is answered normally. **Every response,
  including that 421, carries `X-Frame-Options: DENY` and
  `Content-Security-Policy: frame-ancestors 'none'`, and no response on any
  route ever carries an `Access-Control-Allow-*` header.** The framing and CORS
  rules are part of this invariant rather than free-floating prose in §4.4,
  because §11 assigns them to its case and an implementer building from §5 alone
  would otherwise ship neither.
  *Test:* `tools/verify_page.py`, case `host_allowlist` — **five** `Host`
  values — seven, once the good ones below are counted — with every host string
  built from **the port the case actually bound**, never the literal 4322. The case binds an ephemeral free port like every other
  case, so hard-coded values would silently stop being poison: against a server
  on port 5000, `evil.example.127.0.0.1:4322` does not satisfy
  `endswith("127.0.0.1:5000")`, the prescribed §7 breakage stays green, and the
  case proves nothing. **Three of the values are good ones, not one** —
  `127.0.0.1:<port>`, `localhost:<port>` and `LOCALHOST:<port>`. The allowlist
  has two entries and §4.2 requires a lowercased comparison, so a case carrying
  only the numeric lowercase form passes against a server that allowlists
  `127.0.0.1` alone, case-sensitively — which 421s the URL a user actually
  types. That makes seven values in all. The four poisons must each draw
  421 — `evil.example:<port>` (defeats a port-only check),
  `127.0.0.1.evil.example:<port>` (defeats `startswith`),
  `evil.example.127.0.0.1:<port>` (defeats `endswith`), and **no `Host` header at
  all** (defeats trusting absence). §4.2's table maps each to the comparison it catches; without all four,
  a weakened check passes. Sending no `Host` needs a raw socket or
  `http.client.HTTPConnection(..., skip_host=1)` — `urllib` supplies one
  automatically, so a case written the obvious way silently tests nothing here.
  The good request is what stops the case passing against a server that answers
  421 to everything.
  **Each of the five is fired at `GET /`, `GET /status`, `POST /refresh` and
  `POST /settings`**, because a `Host` check written into `do_GET` alone passes a
  `GET /`-only case while leaving both write routes reachable from a rebound
  origin. **The good-`Host` expectation is per route, not a blanket 200**: 200
  for `GET /` and `GET /status`, 200 for a tokened `POST /settings`, and 202 for
  a tokened `POST /refresh` — after `wait_idle(5)`, since a refresh still running
  from the opening build draws §4.1's 409, and the case would then flake on
  timing rather than fail on the allowlist (the same guard INV-13's case needs). A single "expect 200" is unsatisfiable
  against a correct server, and the natural repair — "anything but 421" — throws
  away the positive control.
  The same case asserts, on every one of the responses including the 421s, that
  no `Access-Control-Allow-*` header is present and that
  `X-Frame-Options: DENY`, `Content-Security-Policy: frame-ancestors 'none'` and
  `Cache-Control: no-store` are.
  *Breaks when:* the check becomes a substring, prefix or suffix test (§4.2's
  table pairs each with the host that defeats it); the header is absent and
  treated as trusted; or a CORS header is added, which §4.4 explains would let a
  hostile origin read what the allowlist stopped it reaching.

- **INV-13** — A POST to `/settings` or `/refresh` without the run's exact
  token returns 403 and changes nothing: no file is written and no rebuild is
  started. ("Nothing on disk" alone is unfalsifiable for `/refresh`, which
  writes nothing even when it succeeds.)
  *Test:* `tools/verify_page.py`, case `token_required` — five POSTs, all with
  a valid `Host`: no token (403), a wrong token (403), a wrong `Origin` with the
  right token (403, §4.2's table), the right token with no `Origin` (accepted —
  the tray's own case), and the right token with `Origin: http://127.0.0.1:<port>`
  (accepted — the browser's own case, and the row that stops a handler which
  403s *every* present `Origin` from passing while every in-page toggle fails).
  **The wrong token is a proper prefix of the real one**, so `startswith` is
  actually caught; a random wrong token passes a `startswith` implementation.
  The case also asserts the rendered page contains the run token, since a
  renderer that never embeds it (§4.3) 403s every toggle while all eleven cases
  otherwise pass.
  **Every one of them is fired at both `/settings` and `/refresh`.** The
  *Breaks when* below names exempting `/refresh` as the likeliest breach, so a
  case that only ever POSTs to `/settings` cannot catch the very failure it is
  written for.
  **The `/settings` POSTs carry `{"autostart": true}`, never `{}`.** An empty
  object is a valid no-op returning 200 (§4.1), so with it the autostart file is
  byte-identical *whether or not a token check exists* and the rejection
  assertion passes against a server with no defence. **Every rejected POST runs
  before any accepted one**, from a fresh config directory in which the file does
  not yet exist: the rejections are asserted by the file still being **absent**,
  and the accepted ones by it being **present** afterwards. The order is the
  assertion — run the other way round, "still present" holds whether or not the
  rejection did anything. Each case in the script gets its own temporary config
  directory and its own server instance, so no case inherits another's file or
  another's in-flight build.
  For `/refresh`, "changes nothing" is the stub builder's call count being
  unchanged; the case calls `wait_idle(5)` **before the first** accepted refresh and again
  between the two — the opening build is a refresh like any other, so without the
  first wait even the first accepted POST can draw §4.1's 409 for concurrency
  rather than for anything this
  invariant is about, and the case flakes on timing.
  The valid `Host` is what isolates this rule: with a bad one INV-12 answers 421
  first and the case passes without the token check existing at all.
  The same case spawns a child with `LOTTO_TOKEN` in its environment and
  asserts that token is accepted — the §4.3 channel the tray depends on, which
  would otherwise be the one link in the chain nothing exercises. **The child is POSTed at
  `/refresh`**, which under `LOTTO_NO_BUILD` answers **202 and rebuilds
  nothing** — the flag suppresses every build, not merely the opening one, or
  this case would trigger the real builder through the very request it is making.
  **The child is spawned with `LOTTO_NO_BUILD` set, its own free `LOTTO_PORT`,
  and `cwd` at the repository root**, and all three are load-bearing: a plain
  `python3 serve.py` runs the *real* builder, which is 27 requests against a
  third-party API (LOTTO-0002 §4.2) — pulling the network into a suite whose
  first constraint (LOTTO-0002 §7) is that it needs none, and reading the real
  `lotto_sms_raw.txt` from that `cwd`, which its second constraint forbids. The second port keeps it
  off the one the rest of the case is using. LOTTO-0002 §4.1's environment table names
  this case alongside LOTTO-0013's INV-20 as the only two callers of
  `LOTTO_NO_BUILD`.
  *Breaks when:* the token is compared with `startswith`, read from a query
  string (where it lands in browser history), or checked on `/settings` only.
  (`==` instead of `secrets.compare_digest` is a real defect and **not** one
  this or any black-box case can observe — the two agree on every input and
  differ only in timing. It is a code-review item, and §11 records that nothing
  mechanical catches it.) The likeliest breach is not a coding slip at all but
  §4.3's tray problem resolved the wrong way; that section states why.

- **INV-14** — No request-derived **string** reaches a response header or a
  written file. The only request-derived values ever written are §4.1's two
  validated booleans; the `.desktop` file's contents are constant.
  *Test:* `tools/verify_page.py`, case `no_reflected_headers` — the poison is
  **percent-encoded** (`/a%0d%0aX-Injected:+yes`), not raw, and the `Host`
  header is valid on every request. The case **first issues a valid
  `POST /settings {"autostart": true}` with the run token**, so the `.desktop`
  file exists to be asserted about — a poisoned path is not `/settings`, it
  404s, and nothing would be written for the assertion to have a subject.
  It then asserts, on every response, that **the set of header names is exactly
  the set that response shape is supposed to carry** and that **no header value
  contains the requested path, or any percent-decoded form of it** — not merely
  that no header called `X-Injected` appeared.
  Both halves need stating that precisely. "No header value contains any
  *substring* of the path" is unsatisfiable — the path shares single characters
  with `application/json` and `no-store`, so the assertion could never pass. And
  the expected name set is **per response shape**, not one fixed list, because
  §4.1 gives a 421, a 404 and a 405 no `Content-Type` and gives a 405 an `Allow`
  header the others do not have.
  **Asserting the absence of that one name is the tautology this case exists to
  avoid**, and it is the shape an implementer naturally writes: a handler that
  reflects `self.path` *raw* into a header — the likelier defect, since it
  involves no `unquote` at all — emits one header whose value is the literal
  `/a%0d%0aX-Injected:+yes`, no header named `X-Injected` exists anywhere, and
  the case goes green against exactly the bug it was written for. §7's own
  prescribed breakage ("reflect `self.path` into a response header") would not
  turn it red. It also asserts the `.desktop` file is byte-identical afterwards.
  **The same case covers §4.1's body validation**, because that rule is what
  keeps this invariant's "the only request-derived values ever written are two
  validated booleans" true: a body with a non-boolean value, a body with an
  unknown key, and a body that is not an object each return **400**; a declared
  `Content-Length` over 4 KiB returns **413**; and after all of them
  `settings.json` still parses to exactly the single boolean key
  (`open_on_start`) it held before, with the `.desktop` file's presence
  unchanged. **One key, not two** — §4.4 explains why `autostart` has no key.
  It asserts the `.desktop` file's content outright
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
  byte-equality there would be flaky rather than strict). **Both `GET /` fetches
  are made against a settled fixture model with no rebuild in flight** — the page
  stamps its build time (LOTTO-0002 §4.5), so two renders taken across a rebuild
  differ for a reason that has nothing to do with the query string. It asserts
  the `<title>` is exactly `<title>Lotto Tracker</title>`, that `no-store` is on
  all four responses, and — over the **whole rendered page, not just its inline
  script** — that it contains no `pushState`, no `replaceState`, no assignment to
  `location.hash`, `location.search` or `location.href`, no call to
  `location.assign`, no
  `href="?`, no `href="#` and no `<form` element.
  **The script-only version of this assertion cannot see the breach the
  invariant names.** *Breaks when* below calls `/?game=lotto&ref=…` "the natural
  first implementation" — and the natural way to write it is a plain link or a
  GET form, which is markup, not script. A case grepping the script alone goes
  green against precisely that. It also asserts §4.1's routing floor — an unknown
  path is 404 and a known path with the wrong method is 405 — since both are
  responses that must name nothing from the request.
  *Breaks when:* filtering is implemented as `/?game=lotto&ref=…`, the natural
  first implementation, which writes a ticket reference into browser history —
  or as a `#ref=…` fragment, which looks safer and is not: the fragment is in
  the URL the browser stores and syncs, it is merely not sent to the server.

## 6. Failure modes

- **A tab left open across a server restart holds a stale token.** The token is
  per server run, not per page — so every tab of one run shares one token, and a
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

LOTTO-0002 §7 holds the three constraints that bind all eleven cases — no network,
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

**Each case is observed failing before the invariant is accepted**, per
LOTTO-0002 §7, which owns that rule and the reasoning for it. The four
breakages, each stated precisely enough to actually go red:

- **Replace the `Host` check with `host.endswith(allowlisted_value)`** and
  confirm `host_allowlist` fails on `evil.example.<port-suffixed allowlist
  value>` — verified: that host satisfies `endswith` while the other three
  poison values do not, which is why §4.2's table pairs one host with each weaker comparison.
  Also try the port-only form, `host.endswith(":" + str(port))`, which
  `evil.example:<port>` defeats.
- **Drop the token check on `/refresh` alone**, leaving `/settings` guarded, and
  confirm `token_required` fails. This is the breach the invariant names as
  likeliest, and a case POSTing only to `/settings` survives it.
- **Reflect `self.path` raw into a response header** — no decoding — and confirm
  `no_reflected_headers` fails on the header-name-set assertion. Against the
  older "no `X-Injected` header" assertion this breakage went green, which is
  why the case now compares the whole name set.
- **Render the ticket filter as `<a href="?game=lotto">`** and confirm
  `nothing_in_the_url` fails. A `pushState` breakage would also go red, but it
  is not the one *Breaks when* calls the natural first implementation.

## 8. Alternatives considered (and rejected)

- **`Origin` checking instead of `Host`.** Rejected on evidence: a top-level
  navigation sends no `Origin`, so the rebinding case passes a check that trusts
  its absence. Kept as an additional check on POSTs (§4.2).
- **`SimpleHTTPRequestHandler` serving a directory.** Rejected: it reintroduces
  path traversal as a class, for the convenience of not writing four routes.
- **A localhost bind and nothing else**, which is what most local dev servers
  do. Rejected on the CVE in §2 — it is the precise shape of this design without
  a `Host` check, and it was exploited.
- **Exempting the tray's `POST /refresh` from the token.** Rejected — §4.3
  states the reasoning and specifies the channel that makes the shortcut
  unnecessary.
- **A token in a query string or a cookie** rather than a custom header.
  Rejected: a query string lands in browser history, which INV-21 forbids; a
  cookie was historically sent automatically on a cross-origin form post, and
  still is wherever `SameSite` is not enforced — which is exactly the property
  the custom header is chosen for, and it does not depend on a browser default
  staying where it is.

## 9. Out of scope

- The model, the refresh lifecycle and what the page renders — LOTTO-0002.
- The tray, the supervisor and the headless contract — LOTTO-0013.
- Authentication of any kind beyond the per-run token. The server has one user,
  the one who owns the process.
- Serving to any host but the loopback interface, now or later.
- TLS. A loopback socket has no transport to protect, and a self-signed
  certificate would train the user to click through a warning.

## 10. Resource cost

- **Memory:** the allowlist is two strings and the token is 43 characters, so
  the boundary itself costs nothing. The *server* costs one thread per open
  connection (`ThreadingHTTPServer`, §4.1), including the sockets browsers
  pre-open and never send on — which is the reason for that choice, and its
  price. **No connection or thread cap is set, and that is a deliberate
  acceptance rather than an oversight.** A browser bounds itself to roughly six
  connections per host, but §2's threat model is a hostile page — which can open
  tabs and workers — and a non-browser client on this machine has no limit at
  all, so thread exhaustion is reachable. It is accepted because anyone who can
  reach this port can already run processes as this user, and a cap would add a
  failure mode (a legitimate request refused) to defend against a denial of
  service the user ends by closing the tab. If this port ever became reachable by
  another user on the machine, that calculation changes. The one request-sized
  allocation is `POST /settings`'s body, capped at 4 KiB (§4.1).
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
| §4.1 body validation — 400 on a bad body, 413 over 4 KiB, nothing written | `tools/verify_page.py::no_reflected_headers` |
| §4.2 the lowercased, whole-string `Host` comparison | `tools/verify_page.py::host_allowlist` — one poison per weaker comparison (§4.2's table) |
| §4.4 the access log silenced, so no request line reaches stderr | **nothing** — no case reads the server's stderr. The exposure is bounded by INV-21 anyway, since a request line can carry no ticket data; code review only |
| §4.1 the fixed check order (Host before token before body) | `tools/verify_page.py::host_allowlist` — its poisoned POSTs expect 421, which only a Host-first implementation returns |
| §4.1 the write lock on `POST /settings` | **nothing** — two concurrent toggles need two clients racing; observable only as a switch snapping to a value nobody chose |
| §4.1 no request path ever joined to a filesystem path | **nothing** — the class is removed by construction (`BaseHTTPRequestHandler`, bodies built in memory) rather than defended, so there is nothing to probe; code review only |
| §4.1 the per-route `Content-Type` | **nothing** — no case asserts it; a wrong one is visible immediately in a browser rather than silent |
| §4.4 anti-framing headers on every response | `tools/verify_page.py::host_allowlist` |
| §4.4 the `.desktop` `Exec` naming `tray.py`, not the writing module | `tools/verify_page.py::no_reflected_headers` — LOTTO-0002 §4.7's body is asserted byte-for-byte |
| §4.3 `secrets.compare_digest` rather than `==` | **nothing** — the two agree on every input and differ only in timing, so no black-box case can tell them apart; code review only |
| §4.3 the token surviving a browser that strips custom headers | **nothing** — no such browser is known, and the failure is visible (403 on every toggle) rather than silent |

Eighteen rows, six `nothing`.

## 12. Cross-doc impact

- `docs/specs/LOTTO-0002-local-web-page.md` — the parent of this split; its
  §4.3 and §4.4 became pointers here, and it lost INV-12, 13, 14 and 21. **Three
  further edits were made to it alongside this document's, in the same change,
  and are recorded here rather than left implicit:** its §6's stale-token bullet
  and its §4.5's client-side-filtering rule had both been left stated in full in
  *both* documents by the split, and are now stated here and pointed at there;
  and its §4.1 environment table, which had described `LOTTO_NO_BUILD` as
  existing "for LOTTO-0013's INV-20 case only", now names INV-13's spawned child
  as its second caller.
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
| 1 | 2026-08-02 | 2 | 4 | 5 | 6 | 10 | All 25 verified findings fixed; 0 unverified, 0 deferred. **Two CRITICALs were security cases that pass against a server with no defence at all** — the shape this document's own §2 says it was written to avoid. `no_reflected_headers` asserted only that no header named `X-Injected` appeared, so a handler reflecting `self.path` **raw** into a header — the likelier defect, involving no decoding — emits a header whose value is the literal poison, no `X-Injected` exists, and the case goes green. §7's own prescribed breakage would not have turned it red. It now compares the whole response header **name set** against a fixed list and asserts no header value contains any substring of the request path. And INV-13's token-channel clause spawned `python3 serve.py` to prove the tray's `LOTTO_TOKEN` is accepted — which runs the real builder, dragging 27 network requests and ~40 s into a suite whose first stated constraint is that it needs none; the child now gets `LOTTO_NO_BUILD`, its own free port and an explicit `cwd`. **A third CRITICAL made a case unbuildable:** INV-12 fired four `Host` values at three routes expecting 200, while §4.1 answers 202 on `POST /refresh` and §4.3 answers 403 without a token, so the case fails against a correct server and the obvious repair — "anything but 421" — deletes the positive control. Expectations are now per route. **The fourth: §4.2 specified a 421 as "the bare status line with no body" while §4.4 required every response to carry the anti-framing headers and INV-12 asserted them on all four responses, three of which are 421s.** Two sections specifying opposite implementations of the most-served response in the document. **One HIGH was arithmetic, and measured rather than argued:** §4.2 claimed its two poison hosts defeat "a prefix, suffix or substring test", but `evil.example:4322` defeats none of them and `127.0.0.1.evil.example:4322` defeats only `startswith` — neither has `endswith(allowlist)` true, so §7's red-test ("widen the comparison to `endswith`") left the case green. §4.2 now carries a table mapping each weaker comparison to the one host that defeats it, and the case fires a fifth value, `evil.example.127.0.0.1:4322`. INV-21's assertion could not see the breach its own *Breaks when* calls the natural first implementation: it grepped the inline script for `pushState`, while a `href="?game=…"` link or a GET form is markup. Also fixed: two paragraphs stated verbatim in both this document and LOTTO-0002 after the split (the stale-token failure mode and the client-side-filtering rule) — stated here, pointed at there, deleting the copies rather than reconciling them; `POST /settings` had no body cap, so the obvious `rfile.read()` is an unbounded read on a local socket (now 4 KiB, 413 above, 400 on a missing or non-numeric `Content-Length`); `BaseHTTPRequestHandler` writes the request line to stderr via `log_request`, which is a request-derived string leaving the process, so the access log is silenced and INV-14's scope is stated rather than left as an omission; and §4.2's justification for writing `421` as an integer was simply false — `HTTPStatus.MISDIRECTED_REQUEST` has existed since Python 3.5, well below the asserted 3.8 floor. §11 grew from eleven rows and two `nothing` to fifteen and four. Doc grew 475 -> 603 lines. |
| 2 | 2026-08-02 | 2 | 1 | 8 | 11 | 12 | All 32 verified findings fixed; 0 unverified, 0 deferred. **Origin split: roughly 12 fix collateral against 4 draft defects**, so the batch was answered by re-sweeping wholesale. Loop 1 fixed four security cases that could pass against an undefended server; loop 2 found that three of those fixes were themselves wrong. **The CRITICAL was loop 1's own poison list.** It specified five `Host` values hard-coded to port 4322, while every case binds an ephemeral port — so against a server on any other port `evil.example.127.0.0.1:4322` stops satisfying `endswith("127.0.0.1:<bound port>")`, the prescribed §7 breakage stays green, and the case proves nothing. The values are now built from the port the case actually bound. **Loop 1's header-injection fix was literally unsatisfiable:** it required that no response header value contain "any substring of the requested path", and the path shares single characters with `application/json` and `no-store` — computed, 7 and 5 shared substrings respectively — so the assertion could never pass. Restated as the whole path or a percent-decoded form of it. Its companion clause, a "fixed expected list" of header names on every response, could not hold either: §4.1 gives 421/404/405 no `Content-Type` and gives 405 an `Allow` the others lack, so the expected set is now per response shape. **And loop 1's own red-test disclaimer was wrong** — it warned that `host.endswith(allowlisted_value)` might leave the case green, when that string IS the allowlisted value and `evil.example.127.0.0.1:4322` does satisfy it; verified, and the disclaimer deleted. One collateral finding was a genuine functional risk: loop 1 added "a missing, non-numeric or negative `Content-Length` is 400" without scoping it, and a bodiless `urllib` POST — which is exactly what LOTTO-0013's `post()` sends to `/refresh` — omits that header, so the rule as written 400s the tray's Refresh item. The body rules are now scoped to `/settings`. Genuine draft defects: §1 promised a "bare 421" and "nothing a caller sends is ever echoed into a written file", contradicting §4.2's headers-on-every-response and §4.4's two validated booleans in `settings.json`; §4.1 never said routing matches the path component only, under which reading INV-21's `GET /?x=1` comparison would 404 twice and pass vacuously against a server that renders nothing; and §10 claimed the browser's six-connection limit as a bound while §2's threat model is a hostile page that can open tabs and workers — now an explicit acceptance with its reasoning rather than a false bound. Two duplicated words and two review-history asides in the contract body were removed, and the CORS-while-debugging rationale went from three statements to one. Doc grew 603 -> 648 lines. |
| 3 | 2026-08-02 | 2 | 1 | 4 | 8 | 8 | **Converged by cap, and by the collateral trigger — both fired together.** All 21 verified findings fixed; 0 unverified, 0 deferred. Origin split: roughly 8 fix collateral against 4 draft defects, after loop 2's 12-against-4 — two loops running, which is the stop-and-consolidate signal, reached on the same pass as the cap. **Both lanes led on the same CRITICAL, and loop 1 had created it.** Loop 1 wrote that `POST /settings` writes "exactly two validated booleans" into `settings.json`. It writes **one**: LOTTO-0002 §4.7 stores autostart as the *presence* of the `.desktop` file and says so explicitly — "The autostart setting has no separate record — the file *is* the state, so the switch cannot drift". An implementer satisfying INV-14 as written would have added an `autostart` key and built exactly the duplicated state that decision exists to forbid. Corrected in both places, with the reason stated so it is not reintroduced. **A HIGH that only an implementer would have hit:** INV-14's central assertion — the response header name set is "exactly the set that response shape is supposed to carry" — had no referent anywhere in the document, and `BaseHTTPRequestHandler.send_response()` emits `Server` and `Date` whether or not the handler asks for them (measured: a minimal handler returns `Server: BaseHTTP/0.6 Python/3.13.14`, `Date`, `Content-Type`). §4.1 now carries a per-shape header table naming every header on every status, and `Server` is overridden to a constant — the default volunteers both the server and the interpreter version from a security boundary. **The check order was load-bearing and lived only in a test note**: INV-12 fires poisoned hosts at both POST routes expecting 421, which only a Host-before-token implementation returns, so an implementer ordering them the other way fails a case written against a correct server. §4.1 now states the ladder. And `host_allowlist` never exercised `localhost` or case-folding at all, while §11 claimed it covered "the lowercased, whole-string comparison" — the allowlist's second entry was shipping untested; the case now carries three good hosts including a mixed-case one. Genuine draft defects: `ThreadingHTTPServer` plus two files and a read-back with no lock, so concurrent toggles can each return the other's result — the exact failure the read-back was added to prevent; no socket read timeout, so a client declaring 4000 bytes and sending 1 hangs a thread just as completely as an unbounded read; and §4.4's anti-framing rationale claimed the framing page obtains the token, which it cannot — the attack is clickjacking, and a wrong mechanism in a security rationale invites wrong reasoning elsewhere. §11 grew to eighteen rows and six `nothing`. Doc grew 648 -> 722 lines. |
| 0-split | 2026-08-02 | — | — | — | — | — | **Provenance row — no reviewer was dispatched, and this is not a review loop.** Second cut of `docs/specs/LOTTO-0002-local-web-page.md`, taken by the user on 2026-08-02 after the first cut (LOTTO-0013, the tray) removed only 66 of 1,161 lines and left the page half at 1,095. The seam here is subject rather than invariant count: this document is the web-security boundary — the routes, the `Host` allowlist, the token and the response-header rules — and what remains in LOTTO-0002 is the lottery-data honesty rules. They need different expertise to review, which is the argument for the cut. Carried over unchanged in substance: the parent's §4.3 (now §4.1) and §4.4 (now §4.2–§4.4), and INV-12, INV-13, INV-14 and INV-21 with their test clauses. **The parent's three cold-eyes loops confer nothing on this document** — they were run against 1,161 lines that no longer exist, and this file starts at loop 1 on its own bytes. Their record is archived at `docs/specs/LOTTO-0002-pre-split-review-log.md`. Two edits were made rather than copied: INV-13's test clause said "four POSTs" while listing five, corrected here to five; and the parent's §4.4 carried three bare references to "§4.7", a section that now lives in another document, all three of which are qualified here. The last of them survived the first qualifying pass and was caught by a mechanical cross-reference sweep rather than by reading. |
