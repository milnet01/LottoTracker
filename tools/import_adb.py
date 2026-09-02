#!/usr/bin/env python3
"""Neutralise forged record boundaries in adb's `content query` output.

The dump's record boundary is a line beginning `Row: N address=`, and the
format has no escaping — so an SMS whose own body carries that shape on a line
splits into a second, fabricated record. A fabricated payout is the one that
matters: it would be counted as money the bank paid.

`tickets.py::rows()` cannot close this. After the fact a forged boundary is
byte-identical to a real one, so the guard has to sit on the writing side.
`watch_sms.py::format_row` has had one since LOTTO-0003; the documented adb
bulk import had none until this (LOTTO-0061).

What makes a real boundary knowable HERE is the index. adb numbers its result
set from 0 and every header is exactly one more than the last — measured
2026-09-02 across the 954 records in the live dump: zero non-sequential steps.
So a header carrying any other number is body text, and is given the same
leading space `watch_sms.py` gives it. One guard, in two writers, producing the
same bytes.

Usage — the README's import command pipes through this:

    adb shell "content query ..." | python3 tools/import_adb.py > lotto_sms_raw.txt

Exit 0 clean, 2 if anything was neutralised (the output is still safe to use),
3 if the stream does not start at record 0 — which means the assumption above
no longer holds and nothing in the output should be trusted.

What this does NOT do, stated because it is easy to assume otherwise. It stops
a forged RECORD — one carrying its own address and date. It does not stop
forged payout TEXT: a neutralised line stays in the body it was found in, and
`parse_payout()` searches a whole body, so the sentence still parses as a
payout of the legitimate record it sits in. That is not this tool's hole — any
message whose body carries that wording parses the same way, however it
arrives, because the admission filter reads the body and never the sender.
Measured 2026-09-02 and filed separately.
"""

import re
import sys

HEADER = re.compile(r"^Row: (\d+) address=")


def sanitise(lines):
    """-> (output lines, count neutralised, first index seen or None).

    Pure, and takes its input as a list, so tools/verify_watch.py can drive it
    over a crafted stream with no adb and no phone.
    """
    out, neutralised, expect, first = [], 0, None, None
    for line in lines:
        m = HEADER.match(line)
        if not m:
            out.append(line)
            continue
        n = int(m.group(1))
        if expect is None:
            first = expect = n
        if n == expect:
            out.append(line)
            expect += 1
        else:
            # Right shape, wrong number: this line is inside a body. One
            # leading space is exactly what watch_sms.py::format_row writes.
            out.append(" " + line)
            neutralised += 1
    return out, neutralised, first


def main():
    out, neutralised, first = sanitise(sys.stdin.read().splitlines(keepends=True))
    sys.stdout.writelines(out)

    if first is None:
        print("import_adb: no records in the input.", file=sys.stderr)
        return 0
    if first != 0:
        print(
            f"import_adb: the stream starts at record {first}, not 0. The "
            "boundary guard assumes adb numbers from 0 with no gaps, so it "
            "cannot tell a real boundary from a forged one here. DO NOT trust "
            "this dump.",
            file=sys.stderr,
        )
        return 3
    if neutralised:
        print(
            f"import_adb: {neutralised} line(s) inside a message body claimed "
            "to be a record boundary and were neutralised. The output is safe "
            "to use. A message tried to forge a record — worth a look.",
            file=sys.stderr,
        )
        return 2
    print("import_adb: nothing neutralised.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
