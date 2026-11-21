# LottoTracker

**LottoTracker keeps one list of every South African lottery ticket you have
bought.** It shows what you chose, what came up, what each ticket won, and
what it cost. It builds that list from the text messages your bank already
sends you.

**Its main job is to warn you when a ticket is about to run out**, so you can
buy the next one in time. It also adds up what you spent against what you won,
for any year or month you pick.

It runs entirely on your own computer. There is no account, no subscription,
and nothing to pay.

> LottoTracker is an independent app. It is not affiliated with or endorsed by
> the South African National Lottery, its operator, or Standard Bank. Always
> check results and claim prizes through the official lottery before relying
> on what the app shows.

## What it does for you

- **Warns you before a ticket runs out.** A small icon by the clock tells you
  two draws before your last one, naming the game and the date.
- **Shows your numbers beside the numbers drawn**, for every draw you paid for.
- **Shows what each ticket won**, in one place instead of one text message at a
  time.
- **Adds up spending against winnings** for a year or a month you choose.
- **Checks its sums against the bank.** When the bank pays a prize, it texts
  you. The app compares those messages with its own working, and shows you
  both figures whenever they differ.
- **Checks for new results every evening** at 22:00, and tells you only when
  you have won.
- **Shows each prize's claim deadline.** A prize expires 365 days after its
  draw. The bank pays most prizes into your account by itself.

## Is this for you?

You need all four of these:

- **You play the South African National Lottery** — Lotto, Lotto Plus 1,
  Lotto 5 Max, PowerBall, PowerBall XTRA, Daily Lotto and, until it ended on
  31 May 2026, Daily Lotto Plus.
- **You buy through Standard Bank**, which texts you each ticket. Other banks
  word their messages differently, and the app cannot read them yet. You can
  help with that: see [Adding your bank](#adding-your-bank).
- **Your phone is an Android phone.** Any make works: Samsung, Motorola,
  Huawei and others. The app gets your messages off the phone by USB cable or
  over Wi-Fi with KDE Connect, and both are Android-only.
  **It does not work with an iPhone**: Apple does not let other apps read an
  iPhone's text messages.
- **Your computer runs Linux.** A Windows version is planned but not started.

## Getting started

### 1. Download the app

Download the `.AppImage` file from the
[latest release](https://github.com/milnet01/LottoTracker/releases/latest).
It is one file that contains everything the app needs.

**It needs Ubuntu 22.04, Linux Mint 21, Debian 12 or newer** — version 2.35 or
newer of the GNU C library. Release 1.1.0 and earlier need 2.44 or newer. To
see yours, open a terminal and type `ldd --version`. If yours is older, the
file will not start; run the app from source instead (see
[For developers](#for-developers)).

Make the file runnable: right-click it, open **Properties**, then
**Permissions**, and tick the box that lets it run as a program. Then
double-click it.

If it does not start and mentions FUSE, open a terminal in its folder and run
it with `--appimage-extract-and-run` after the file name.

### 2. Connect your phone with KDE Connect

1. Install **KDE Connect** on your computer, from your Linux system's software
   centre.
2. Install **KDE Connect** on your Android phone, from the Play Store or
   F-Droid.
3. Put both on the same Wi-Fi network, and pair them from either app.
4. On the phone, give KDE Connect permission to read SMS: Settings → Apps →
   KDE Connect → Permissions → SMS. Pairing alone is not enough.
5. **On a Huawei phone**, two extra steps. Newer Huawei phones have no Play
   Store, so get KDE Connect from F-Droid. Then switch off battery saving for
   KDE Connect in the phone's battery settings; otherwise the phone may close
   it, and new messages stop arriving.

From then on, each new lottery message reaches the app by itself.

### 3. Fetch your older tickets and results

When it starts, the app also reads the lottery messages already on your phone.
To check tickets from before June 2026, choose **Fetch older results** in the
tray icon's menu once.

The app keeps your messages and results in `~/.local/share/LottoTracker`. On
the first run that folder is empty, and the page names it.

## The page and the tray icon

The app puts an icon by the clock. Click it to open the page in your web
browser.

The page opens on an overview: when to buy next, each ticket still running,
the wins still waiting on the bank, and this year's money. Other tabs show
every win, every entry with its cost and winnings, your spending against your
winnings by period, and the bank's own record beside the app's.
On the Wins tab, **Accept** moves a win the bank has not fully paid out of the
waiting count, and **Undo** brings it back.

A settings panel has two switches. One starts the icon when you log in. The
other opens the page when the icon starts.

**Leave the log-in switch on if you rely on the warnings.** The app can only
warn you while the icon is running. If no lottery message arrives for 14 days,
the page says so and the icon reminds you once a day, in case your phone has
stopped reaching the computer.

Things worth knowing:

- **"Not checkable" does not mean "did not win".** Some tickets cannot be
  checked, because no results exist for them. The page says so in words and
  never shows them as R0.00.
- **The bank's figure is shown beside the app's, never instead of it.** Where
  they differ, you see both, and the reason where one is known.
- **Spending is compared only with what could be checked.** Your lifetime
  spending is shown too, on its own line, so unchecked tickets never count as
  losses.
- **The text is set in Atkinson Hyperlegible**, a typeface made for low
  vision. It ships in `fonts/` under its own licence.

## Your messages stay yours

The code for this app is public. Your messages are not:

- **Nothing is uploaded anywhere.** The app only downloads public lottery
  results.
- **The page is for your computer alone.** It cannot be reached from your
  network, and it will not show your tickets to a website you are visiting.
- **No ticket details appear in desktop notifications.** The one exception is
  the warning to buy again, which names the game, the last draw's date and the
  draws left.
- **Only lottery messages are kept.** The app keeps messages that mention
  `lotto`, `powerball` or `VAS00` (the bank's prize reference), and skips
  electricity-token messages. It filters by words, not by sender, so a personal
  message mentioning the lottery would be kept too.

## Adding your bank

**Do you buy South African lottery tickets through a bank other than Standard
Bank?** Please send us its messages, so the app can learn to read them. Only
South African banks can be added, because the app only knows South Africa's
lottery.

We need two kinds of message:

- **a ticket you bought**, and
- **a prize the bank paid you**, if you have one.

If your bank changed its wording on 1 June 2026, when the lottery changed
operator, send one of each from before and after that date too.

**Change your personal details before you send anything.** These messages are
posted in public:

- Replace the ticket reference with `VAS00000000000`, or with zeros in the
  same shape if your bank uses a different style.
- Change every number you chose, every date and every amount.
- Remove any account or card digits.
- **Keep everything else exactly as it arrived** — the words, the spacing, the
  punctuation and the line breaks. That layout is what the app learns to read.

Then [open an issue](https://github.com/milnet01/LottoTracker/issues/new?template=new-bank.md)
using the **Add my bank** form. It asks for the bank's name and the samples.

For whoever writes the reader: **the special ball is a trap.** In Standard
Bank's older format, a PowerBall line ends with the PowerBall itself, and
nothing marks it as different from the five main numbers. Read it as a main
number and every PowerBall ticket scores one match too many and never matches
the PowerBall. Check that case first, whatever the bank.

## How you would know it works

The five things the app is judged against:

1. **It tells you when to buy again, before you have to think about it.** A
   ticket bought for ten draws is used up after the tenth. You are told while
   there is still time to buy the next one, without opening anything. This is
   the main job.
2. **It shows the numbers you chose beside the numbers that came up**, for each
   entry, whether you picked them or took a quick pick.
3. **It shows what each ticket won**, in one place, rather than in one bank
   message per prize.
4. **It totals cost against winnings over a period you choose** — a year, a
   month, or so far this year or month. Money counts in the period of the
   **draw**, not of the purchase, so both figures describe the same draws.
5. **Every disagreement with the bank's own record is explained.** Where the
   app and the bank differ, each case has a named reason. The app may count
   less than the bank paid; it must never claim a win that was not paid.

**Where it stands against those today:** all five are done, with one limit on
5. On a few draws the app works out a win and no bank message exists for it.
That may be a lost message or a prize not paid, and only a bank statement can
tell which.

Sign 4 has a limit too. The periods on offer begin where the results do, so
a period with nothing checkable is not offered at all, rather than shown as
R0.00.

## For developers

The rest of this page is for running the app from source, or changing it.

### Running from source

Needs Python 3.9+ and a Linux desktop. Everything below is free software from
your distribution's repositories. The tray icon additionally needs PySide6 —
that is the *only* thing that does, so the page still works headless without
it.

```bash
sudo zypper install android-tools kdeconnect-kde python313-dbus-python  # openSUSE
sudo apt install android-tools-adb kdeconnect python3-dbus              # Debian/Ubuntu
```

On openSUSE the D-Bus binding is named for your Python version — `python313-`
for Python 3.13, `python314-` for 3.14. It is what the Wi-Fi path talks to KDE
Connect through; without it that path fails at import. The USB path does not
need it.

```bash
python3 tray.py     # an icon by the clock; click it to open the page
python3 serve.py    # or just the page, no icon, no PySide6 needed
```

A source checkout keeps its data in the repository folder.

### Importing history by USB cable

**Best for importing years of history at once.** On the phone: Settings →
About phone → Software information → tap **Build number** seven times, then
Settings → Developer options → **USB debugging** on. Plug in the cable and
**set the USB mode to File Transfer** — on Samsung One UI the debugging prompt
does not appear while the connection is charge-only. Approve the dialog, then:

```bash
adb devices          # should say "device", not "unauthorized"
adb shell "content query --uri content://sms \
  --projection address:date:body \
  --where \"(body LIKE '%lotto%' OR body LIKE '%powerball%' \
             OR body LIKE '%VAS00%') \
            AND body NOT LIKE '%kWh%' \
            AND body NOT LIKE '%Enter tokens%'\"" \
  | python3 tools/import_adb.py > lotto_sms_raw.txt
```

The filter runs **on the phone**, so other messages never reach the computer.

**The pipe is not optional.** A record begins with a line reading
`Row: N address=`, and nothing escapes it — so a message whose own body
contains that line would split into a second, forged record, and
`tickets.py::rows()` cannot tell it from a real one afterwards.
`tools/import_adb.py` neutralises the shape on the way in, which is what
`watch_sms.py` already does on the wireless path. It prints what it found and
exits non-zero if it neutralised anything.

### Importing over KDE Connect by hand

```bash
python3 watch_sms.py --once   # catch up on what the phone already has, then exit
python3 watch_sms.py          # or stay listening, and append each new one as it arrives
```

The tray icon starts the listening form for you.

There is also `python3 find_lotto_sms.py`, which **prints and writes nothing**.
It casts a deliberately wider net than the importer, so it is the thing to run
when you want to see whether a message is reaching the PC at all. It will not
import anything, however long you leave it.

### Checking tickets in a terminal

```bash
python3 backfill.py    # one-off: fetch pre-June-2026 results
                       # (one request per pool per year); the tray's
                       # "Fetch older results" does the same
python3 check.py       # score every ticket
```

```
2 of 1246 ENTRIES CANNOT BE CHECKED. They are not counted below, and are NOT losses.
  2 predate all draw data for their pool (earliest: 2025-09-26)
  affecting 0 tickets wholly and 2 tickets partly
    a partly-checkable ticket IS scored on its remaining pools, below

123 winning lines total; 1 not yet paid
NOT YET PAID - wins the bank has no record of paying in full, soonest deadline first:
  2026-05-04  VAS00000000000  lotto/0  line A2  DIV 7 (match 2 + Bonus)  R18.30  unpaid  expires 2027-05-04
(lifetime total incl. expired: R1,234.56)
```

(The ticket reference and the win line above are made up. The counts are real.)

**One ticket is usually several entries.** A "plus" game cannot be bought on
its own — the lottery requires the base game, and runs a *separate draw with
its own prizes* for each level. So a Lotto Plus 2 ticket is three entries with
three chances, not one, and all three are checked. Which levels you paid for
is worked out from the ticket price, because the game name printed in the SMS
only ever names the highest one — and since June 2026 it doesn't name it at
all.

A win counts as paid only when the bank says so, from its own sender. Every
other win is listed as **not yet paid** — unpaid, partly paid, or payment
unknown when there is no payment message to check — with its deadline. There
is no total: for a partly paid ticket, what is still owed is not known.

### Building the AppImage

It needs `podman`. The script builds an Ubuntu 22.04 container
(`packaging/Containerfile`) and runs PyInstaller inside it:

```bash
tools/build_appimage.sh                       # writes dist/LottoTracker-<version>-x86_64.AppImage
./dist/LottoTracker-*-x86_64.AppImage         # starts the tray, the page and the watcher
```

It runs on systems at least as new as Ubuntu 22.04, whatever system built it.

### Privacy checks

`.gitignore` excludes the SMS dump and the results cache. Verify with
`python3 tools/verify_privacy.py`. It compares every tracked file against the
dump's own text, and also runs identifying patterns — so it catches a real
message pasted into a doc as an "example", not just a stray file. Without the
dump only the pattern half runs. Once `git config core.hooksPath .githooks`
is set, `.githooks/pre-commit` runs it on the staged files of every commit.
It catches copied content, not inferred identity: a figure that pins one
real ticket without quoting it, such as an exact win amount beside its
draw date, passes. That still needs a human read.

Sample ticket references in this repo are deliberately fake
(`VAS00000000000`). Never paste a real one into a doc or an issue — it is
the one leak path `.gitignore` cannot cover.

The page server listens only on `127.0.0.1:4322` and refuses any request that
does not name that address. That stops a website you are visiting from reading
your tickets through it, and it is why the page will not load through any other
hostname. Nothing about a ticket appears in the address bar or the page title,
because browsers sync those.

### How it fits together

| File | Does |
|------|------|
| `results.py` | Official results feed, 2026-06-01 onward |
| `backfill.py` | Scrapes earlier results and per-draw payouts |
| `history.py` | Merges both sources into one view |
| `tickets.py` | Parses SMSes into tickets and into the bank's payout messages; expands Multiplay |
| `check.py` | Scores tickets, prices wins, flags expiry, and reconciles against what the bank actually paid |
| `watch_sms.py` | Imports new SMSes over KDE Connect, no cable |
| `find_lotto_sms.py` | Prints lottery threads seen over KDE Connect; adds nothing to the dump |
| `serve.py` | Serves the local page, and does all of its I/O |
| `page.py` | Turns what `check.py` worked out into the page's HTML |
| `supervise.py` | Starts, watches and stops the server and the SMS listener |
| `tray.py` | The icon by the clock; the only file that needs PySide6 |
| `VERSION` | The release number; nothing in the app reads it |
| `tools/verify_*.py` | Checks the contracts in `docs/specs/`, including that no real message content is tracked |

The design contract, including why each source is used and where the traps
are, is in [`docs/specs/LOTTO-0001-lottery-ticket-tracker.md`](docs/specs/LOTTO-0001-lottery-ticket-tracker.md).

### Caveats

- The official feed's endpoints are the ones the operator's own website calls.
  They are public and unauthenticated, but carry no compatibility promise and
  could change without notice.
- The archive is scraped from `backfill.FIRST_YEAR` onward — the year of the
  earliest ticket in the dump. Anything older is reported as uncheckable
  rather than scored against the wrong draws.
- This is a personal tool, not a licensed service.
