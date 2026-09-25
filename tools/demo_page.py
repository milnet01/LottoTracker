"""Render the real page from an INVENTED model, for the project hub's screenshots.

    python3 tools/demo_page.py demo.html

Then screenshot it headless at 1280 wide and crop into docs/screenshots/.
No real ticket, reference or number is used: every value below is made up,
and ticket names are deliberately not reference-shaped.
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import page  # noqa: E402
import verify_page  # noqa: E402


def entry(ref, game, plus, cost, covered, remaining, won, boards, scorable=True, reason=None):
    return {"ref": ref, "game": game, "plus_flag": plus, "pool_id": 0,
            "cost_cents": cost, "scorable": scorable, "reason": reason,
            "won_cents": won if scorable else None,
            "draws_covered": covered if scorable else None,
            "draws_remaining": remaining if scorable else None, "boards": boards}


L = [{"line": "A", "numbers": [4, 11, 19, 27, 38, 52], "special": None},
     {"line": "B", "numbers": [2, 9, 23, 31, 44, 50], "special": None}]
P = [{"line": "A", "numbers": [7, 14, 22, 35, 41], "special": 12}]
D = [{"line": "A", "numbers": [3, 8, 17, 25, 33], "special": None}]

entries = [
    entry("demo-lotto", "lotto", 0, 2000, 10, 0, 5000, L),
    entry("demo-lotto", "lotto", 1, 1000, 10, 0, 0, L),
    entry("demo-lotto", "lotto", 2, 1000, 10, 0, 0, L),
    entry("demo-powerball", "powerball", 0, 1500, 6, 4, 1500, P),
    entry("demo-powerball", "powerball", 1, 1000, 6, 4, 0, P),
    entry("demo-daily", "daily", 0, 1500, 3, 2, 0, D),
    entry("demo-daily", "daily", 1, 750, 0, 0, 0, D, scorable=False,
          reason="no results source publishes this pool"),
]

wins = [
    {"ref": "demo-lotto", "game": "lotto", "plus_flag": 0, "pool_id": 0,
     "date": "2026-07-18", "division": "Division 7", "matched": "MATCH 3",
     "amount_cents": 5000, "expires": "2027-07-18", "expires_in_days": 296,
     "expired": False, "source": "api",
     "numbers": [4, 11, 19, 27, 38, 52], "drawn_main": [4, 11, 19, 30, 46, 49],
     "drawn_special": 21},
    {"ref": "demo-powerball", "game": "powerball", "plus_flag": 0, "pool_id": 0,
     "date": "2026-09-05", "division": "Division 9", "matched": "MATCH 1 + PB",
     "amount_cents": 1500, "expires": "2027-09-05", "expires_in_days": 345,
     "expired": False, "source": "api",
     "numbers": [7, 14, 22, 35, 41], "special": 12,
     "drawn_main": [5, 14, 28, 39, 48], "drawn_special": 12},
]

model = verify_page.fixture_model()
model.update({
    "wins": wins,
    "entries": entries,
    "tickets": [
        {"ref": "demo-lotto", "game": "lotto", "cost_cents": 4000, "boards": 2,
         "ndraws": 10, "resolved": True, "bought": "2026-06-10"},
        {"ref": "demo-powerball", "game": "powerball", "cost_cents": 2500, "boards": 1,
         "ndraws": 10, "resolved": True, "bought": "2026-08-14"},
        {"ref": "demo-daily", "game": "daily", "cost_cents": 2250, "boards": 1,
         "ndraws": 5, "resolved": True, "bought": "2026-09-21"},
    ],
    "uncheckable": {"entries": 7, "uncheckable": 1, "too_old": 0, "no_pool": 1,
                    "wholly": 0, "partly": 1},
    "spend": {"compared_cents": 8000, "lifetime_cents": 8750,
              "unresolved_cents": 0, "unresolved_tickets": 0},
    "won": {"compared_cents": 6500, "lifetime_cents": 6500, "unexpired_cents": 6500},
    "periods": {"buckets": [
        {"key": "2026", "kind": "year", "label": "2026", "spend_cents": 8000, "won_cents": 6500},
        {"key": "2026-09", "kind": "month", "label": "September 2026", "spend_cents": 3750, "won_cents": 1500},
        {"key": "2026-08", "kind": "month", "label": "August 2026", "spend_cents": 1000, "won_cents": 0},
        {"key": "2026-07", "kind": "month", "label": "July 2026", "spend_cents": 3250, "won_cents": 5000},
    ], "no_result_cents": 0},
    "built": "2026-09-25T09:30:00",
})

out = sys.argv[1]
with open(out, "w") as fh:
    fh.write(page.render(model, "demo-token"))
print("wrote", out)
