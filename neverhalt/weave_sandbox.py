"""Isolated weave search entrypoint; the parent owns scoring and all verdicts."""
from __future__ import annotations

import contextlib
import io
import json
import re
import resource
import runpy
import sys
import traceback
from pathlib import Path

PIXEL_BITS = str.maketrans(".#", "01")


def trace(tm: str, height: int) -> dict:
    from neverhalt.tm import parse
    table, n, k = parse(tm)
    if k != 2:
        raise ValueError("expected a binary machine")
    # Reject malformed tokens instead of silently treating arbitrary text as halt.
    for row in tm.strip().split("_"):
        for i in (0, 3):
            token = row[i:i + 3]
            if token != "---" and not re.fullmatch(r"[01][LR][A-Z]", token):
                raise ValueError(f"malformed transition {token!r}")
    tape, q, pos, lo, hi, halted = set(), 0, 0, 0, 0, False
    snapshots = []
    visited_states = set()
    for t in range(height):
        lo, hi = min(lo, pos), max(hi, pos)
        visited_states.add(q)
        snapshots.append(tape.copy())
        if t == height - 1 or halted:
            continue
        tr = table.get((q, int(pos in tape)))
        if tr is None:
            halted = True
            continue
        w, d, q = tr
        if w:
            tape.add(pos)
        else:
            tape.discard(pos)
        pos += d
    rows = ["".join("#" if x in tape else "." for x in range(lo, hi + 1)) for tape in snapshots]
    return {"rows": rows, "lo": lo, "width": hi - lo + 1, "states": n,
            "transitions": len(table), "halted": halted, "visited_states": len(visited_states)}


def score_rows(target: list[str], rows: list[str]) -> dict:
    h, w, c = len(target), len(target[0]), len(rows[0])
    target_bits = [int(row[::-1].translate(PIXEL_BITS), 2) for row in target]
    candidate_bits = [int(row[::-1].translate(PIXEL_BITS), 2) for row in rows]
    best = None
    for offset in range(1 - c, w):
        left, right = max(0, offset), min(w, offset + c)
        overlap = right - left
        mask = (1 << overlap) - 1
        wrong = sum((((a >> left) ^ (b >> (left - offset))) & mask).bit_count()
                    for a, b in zip(target_bits, candidate_bits))
        correct = h * overlap - wrong
        total = h * (w + c - overlap)
        if best is None or correct * best[1] > best[0] * total:
            best = correct, total, offset
    correct, total, offset = best
    mismatches = []
    for t, (a, b) in enumerate(zip(target, rows)):
        if c != w or offset != 0 or a != b:
            mismatches.append({"t": t, "target": a, "candidate": b, "offset": offset})
            if len(mismatches) == 6:
                break
    return {"accuracy": correct / total, "correct": correct, "total": total,
            "exact": correct == total, "offset": offset, "mismatches": mismatches}


def evaluate(tm: str, target: list[str]) -> dict:
    result = trace(tm, len(target))
    result.update(score_rows(target, result["rows"]))
    result["tm"] = tm
    return result


def render(tm: str, height: int) -> list[str]:
    """Binary rows with exactly the harness crop; no head letters."""
    return trace(tm, height)["rows"]


def score(tm: str, target: list[str]) -> tuple[float, int]:
    """Exact harness pixel accuracy (best alignment), declared state count."""
    result = evaluate(tm, target)
    return result["accuracy"], result["states"]


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (90, 91))
    resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024,) * 2)
    # Main search plus at most four child processes; the host may be stricter.
    resource.setrlimit(resource.RLIMIT_NPROC, (5, 5))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    target = json.loads(sys.stdin.read())
    log = io.StringIO()
    try:
        with contextlib.redirect_stdout(log):
            namespace = runpy.run_path(sys.argv[1])
            result = namespace["search"](target)
        certificate = None
        if isinstance(result, dict):
            certificate = result.get("certificate", result.get("cert"))
            machine = result["tm"]
        elif isinstance(result, (tuple, list)) and len(result) == 2:
            machine, certificate = result
        else:
            machine = result
        if not isinstance(machine, str) or len(machine) > 256:
            raise ValueError("search must return a machine string (at most 256 characters)")
        print(json.dumps({"tm": machine.strip(), "certificate": certificate,
                          "log": log.getvalue()[-4000:]}))
    except BaseException as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-2000:],
                          "log": log.getvalue()[-4000:]}))


if __name__ == "__main__":
    main()
