# LottoTracker

Reads the lottery ticket confirmations your bank sends by SMS, remembers every
ticket, and checks them against the real draw results — so a small win doesn't
sit unnoticed until it expires.

Runs entirely on your own machine. No account, no API key, no subscription,
nothing paid.

## Is this for you?

**It is specific to South Africa, and currently to Standard Bank.** Two
separate assumptions are baked in:

- **The lottery** is the South African National Lottery — Lotto, Lotto Plus 1,
  Lotto 5 Max, PowerBall, PowerBall XTRA and Daily Lotto. Results come from
  the operator's own public feed.
- **The SMS format** is Standard Bank's. The parser understands both the
  wording used before the 2026-06-01 operator handover and the wording used
  after it.

If you bank elsewhere, the results half works unchanged and only the parser
needs teaching. See [Adding your bank](#adding-your-bank).

## What it does

- Pulls lottery SMSes off an Android phone — by USB, or over Wi-Fi
- Parses ticket reference, numbers, game, start date, draw count and price
- Fetches draw results, including for draws before the 2026 handover
- Works out every draw you paid to enter, from the price, and checks them all
- Scores every line, expands Multiplay entries correctly, and prices each win
- Flags what is still claimable, and when each prize expires

## Your messages stay yours

This matters enough to be explicit, because the repository is public:

- The USB path filters **on the phone**. Only messages whose text contains
  `lotto` or `powerball` cross to the PC; everything else is never read. Note
  this is a keyword filter, not a sender filter — a personal message
  mentioning the lottery would come across too, so glance at the dump before
  sharing it.
- `.gitignore` excludes the SMS dump and the results cache. Verify with
  `python3 tools/verify_privacy.py`, which compares every tracked file
  against the dump itself rather than against a guessed pattern — it catches
  a real message pasted into a doc as an "example", not just a stray file.
- Nothing is uploaded anywhere. The only outbound requests are to public
  lottery results pages.
- Sample ticket references in this repo are deliberately fake
  (`VAS00000000000`). Never paste a real one into a doc or an issue — it is
  the one leak path `.gitignore` cannot cover.

## Setup

Needs Python 3.8+ and a Linux desktop. Everything below is free software from
your distribution's repositories. The tray icon additionally needs PySide6 —
that is the *only* thing that does, so the page still works headless without
it.

```bash
sudo zypper install android-tools kdeconnect-kde   # openSUSE
sudo apt install android-tools-adb kdeconnect      # Debian/Ubuntu
```

### Getting your messages (pick either)

**USB — best for importing history.** On the phone: Settings → About phone →
Software information → tap **Build number** seven times, then Settings →
Developer options → **USB debugging** on. Plug in the cable and **set the USB
mode to File Transfer** — on Samsung One UI the debugging prompt does not
appear while the connection is charge-only. Approve the dialog, then:

```bash
adb devices          # should say "device", not "unauthorized"
adb shell "content query --uri content://sms \
  --projection address:date:body \
  --where \"(body LIKE '%lotto%' OR body LIKE '%powerball%' \
             OR body LIKE '%VAS00%') \
            AND body NOT LIKE '%kWh%' \
            AND body NOT LIKE '%Enter tokens%'\"" > lotto_sms_raw.txt
```

**KDE Connect — best for picking up new tickets.** Install the KDE Connect app
on the phone, pair it with the PC over the same Wi-Fi, then grant it **SMS
permission** (Settings → Apps → KDE Connect → Permissions → SMS). Pairing and
SMS access are separate grants; pairing alone is not enough.

```bash
python3 find_lotto_sms.py
```

### Checking your tickets

```bash
python3 backfill.py    # one-off: fetch pre-June-2026 results (12 requests)
python3 check.py       # score every ticket
```

```
974 of 1233 ENTRIES CANNOT BE CHECKED. They are not counted below, and are NOT losses.
  963 predate all draw data for their pool (earliest: 2025-01-01)
  11 in a pool no results source carries: daily/1
  affecting 426 tickets wholly and 11 tickets partly
    a partly-checkable ticket IS scored on its remaining pools, below

2026-05-04  VAS00000000000  lotto/0  line A2  DIV 7 (match 2 + Bonus)  R18.30  expires 2027-05-04
...
STILL CLAIMABLE: R123.45
```

(The ticket reference and the win line above are made up. The counts are real.)

**One ticket is usually several entries.** A "plus" game cannot be bought on
its own — the lottery requires the base game, and runs a *separate draw with
its own prizes* for each level. So a Lotto Plus 2 ticket is three entries with
three chances, not one, and all three are checked. Which levels you paid for
is worked out from the ticket price, because the game name printed in the SMS
only ever names the highest one — and since June 2026 it doesn't name it at
all.

Entries are reported as **uncheckable** rather than as losses when nothing
can score them — either they predate the results data (before 2025-01-01), or
they are in a pool no source publishes. That distinction is deliberate and
load-bearing: a ticket nobody can check is not a ticket that lost. It works
per entry, so a ticket that can be checked in one draw and not another is
still scored on the one that can — it is never written off whole.

Prizes expire **365 days** after the draw, which is why the output leads with
what is still claimable rather than a lifetime total.

Small winnings are often paid straight back into the account by the bank, so
treat the total as "check your statement for this", not "this is owed to you".

## The page and the tray icon

The terminal output is a flat list, and there are 1,233 entries. For something
you can read, there is a small page:

```bash
python3 tray.py     # an icon by the clock; click it to open the page
python3 serve.py    # or just the page, no icon, no PySide6 needed
```

The icon starts the server, opens the page, refreshes the results on demand and
shuts the server down when you quit. The page shows what is claimable now with
the soonest expiry first, what is still outstanding, every entry with what it
cost and what it won, and what you have spent against what you have won. A
settings panel has two switches: start the icon when you log in, and open the
page when it starts.

Three things worth knowing:

- **It is yours alone.** The server listens only on `127.0.0.1:4322`, so nothing
  on your network can reach it. It also refuses any request that does not name
  that address, which is what stops a website you happen to be visiting from
  quietly reading your tickets out of it — that is a real attack, not a
  hypothetical one, and it is why the page will not load through any other
  hostname. Nothing about a ticket ever appears in the address bar or the page
  title, because browsers sync those.
- **"Not checkable" is not "did not win".** Entries with no results to check
  against say exactly that, in words, everywhere they appear. They are never
  shown as a blank, a dash or R0.00.
- **The bank's own record is shown beside ours, and never instead of it.** Your
  bank texts you the amount every time it pays a prize in. Those messages are
  read and matched to your tickets, and where the bank's figure and this app's
  disagree you are shown **both** — the app never quietly adopts the bank's
  number. A figure that agreed with the bank by construction would tell you
  nothing, and would hide the cases where this app has got the maths wrong.
  Right now it under-counts: the bank has paid more than this app works out,
  and you can see exactly which tickets that is.
- **The comparison is honest about what it covers.** Spend is compared against
  winnings only over the entries that could actually be checked. Lifetime spend
  is shown too, on its own line, and the two are never subtracted from each
  other — that would turn 974 unchecked entries into losses.

To have the icon start automatically, use the switch on the page rather than
editing anything: it writes `~/.config/autostart/lotto-tracker-tray.desktop`,
and turning it off deletes the file again.

## Adding your bank

The results side is bank-independent; only `tickets.py::parse()` knows about
message wording. To add a bank, you need one real ticket SMS with the personal
details scrambled — the reference number changed to gibberish is fine, but keep
the layout, spacing and punctuation exactly as they arrive.

Open an issue with that sample and the bank's name. What the parser must
extract: the game, the numbers per board, the start date, the number of draws,
and the ticket reference.

One warning for anyone writing a parser: **the special ball is a trap.** In
Standard Bank's older format a PowerBall line ends with the PowerBall itself
and nothing marks it as different from the five main numbers. Treat it as a
main number and every PowerBall ticket scores one match too high and never
matches the PowerBall. Whatever your bank does, check that case first.

## How it fits together

| File | Does |
|------|------|
| `results.py` | Official results feed, 2026-06-01 onward |
| `backfill.py` | Scrapes earlier results and per-draw payouts |
| `history.py` | Merges both sources into one view |
| `tickets.py` | Parses SMSes into tickets and into the bank's payout messages; expands Multiplay |
| `check.py` | Scores tickets, prices wins, flags expiry, and reconciles against what the bank actually paid |
| `find_lotto_sms.py` | Finds lottery threads via KDE Connect |
| `tools/verify_*.py` | Checks the contracts in `docs/specs/`, including that no real message content is tracked |

The design contract, including why each source is used and where the traps
are, is in [`docs/specs/LOTTO-0001-lottery-ticket-tracker.md`](docs/specs/LOTTO-0001-lottery-ticket-tracker.md).

## Caveats

- The official feed's endpoints are the ones the operator's own website calls.
  They are public and unauthenticated, but carry no compatibility promise and
  could change without notice.
- Results before 2025-01-01 are not available from either source.
- This is a personal tool, not a licensed service. Always confirm a win
  against the official result before acting on it.
