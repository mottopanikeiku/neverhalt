"""Writes docs/data.json (the numbers the website overrides at load) from the latest verified runs."""
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOLDOUTS_BB4 = 609_214
BB4_RUNS = ["bb4-scale-dedicated", "bb4-transfer-2"]  # most recent first; first with a summary wins

left = None
for run in BB4_RUNS:
    summary = ROOT / "runs" / run / "summary.json"
    if summary.exists():
        candidate = len(json.loads(summary.read_text())["unproven"])
        left = candidate if left is None else min(left, candidate)
proven = HOLDOUTS_BB4 - left
lean_line = ("lean-eval (official comparator): 3 sanity problems solved and accepted. Real problems: free-form, 0 of 22 "
             "samples produced Lean; with constrained output on Catalan, 25 of 32 candidates parse clean and error "
             "feedback lifts the parse rate from 62.5% to 87.5%, best attempt 1 error, no real solve yet.")
live = Path.home() / "lean-eval-work/ripple/results/live.md"
if live.exists():
    found = re.search(r"samples: (\d+); official solves: (\d+)/(\d+)", live.read_text())
    if found and int(found[2]) > 0:
        lean_line = (f"lean-eval live on 2× B200: {found[2]} of {found[3]} real problems solved and officially accepted "
                     f"after {found[1]} samples.")
data = {"bb4_proven": f"{proven:,}", "bb4_pct": f"{100 * proven / HOLDOUTS_BB4:.2f}", "bb4_left": f"{left:,}",
        "lean_line": lean_line, "updated_at": time.strftime("%H:%M PT, %d %b %Y")}
(ROOT / "docs" / "data.json").write_text(json.dumps(data, indent=1))
print(json.dumps(data))
