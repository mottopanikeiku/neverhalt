"""NEVERHALT command line. `python3 -m neverhalt --help`"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .hunt import ROOT, hunt, verify
from .llm import LLMError, doctor, load_config
from .server import Store, replay, serve


def run_dir(arg: str) -> Path:
    path = Path(arg)
    return path if path.exists() else ROOT / "runs" / arg


def main() -> int:
    parser = argparse.ArgumentParser(prog="neverhalt", description="Proof of never: an LLM proves Busy Beaver values.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hunt", help="prove BB(n): the model writes the deciders, the kernel checks them")
    h.add_argument("--n", type=int, default=3, help="states (default 3)")
    h.add_argument("--k", type=int, default=2, help="symbols (default 2)")
    h.add_argument("--offline", action="store_true", help="bundled reference deciders instead of the model")
    h.add_argument("--name", help="run name under runs/ (default: generated)")
    h.add_argument("--rounds", type=int, default=12)
    h.add_argument("--enter", action="store_true", help="wait for Enter before starting (open the page first)")
    h.add_argument("--no-hints", action="store_true", help="never hint the model after a round that proved nothing")
    h.add_argument("--exit", action="store_true", help="quit when the run ends instead of keeping the gallery up")
    h.add_argument("--round-budget", type=float, default=300.0,
                   help="seconds of decider runtime per round; holdouts not reached wait for the next round (default 300)")
    h.add_argument("--resume", metavar="RUN", help="first re-run the deciders that proved machines in RUN (no model calls)")
    r = sub.add_parser("replay", help="replay a recorded run in the gallery")
    r.add_argument("run")
    r.add_argument("--speed", type=float, default=1.0)
    r.add_argument("--loop", action="store_true")
    for p in (h, r):
        p.add_argument("--port", type=int, default=8765)
        p.add_argument("--host", default="127.0.0.1")
    c = sub.add_parser("check", help="re-verify a finished run with the enumerator and the kernel alone")
    c.add_argument("run")
    sub.add_parser("doctor", help="test the model endpoint configured in .env")
    s = sub.add_parser("scale", help="test-time scaling: many parallel Ripple samples on the holdouts a run left")
    s.add_argument("--n", type=int, default=3)
    s.add_argument("--k", type=int, default=2)
    s.add_argument("--base", required=True, help="finished run(s), comma-separated, whose certificates are kept")
    s.add_argument("--hint", default="", help="comma-separated hint keys added to every prompt (tcycle, cps, automata, far)")
    s.add_argument("--limit", type=float, default=None, help="seconds per machine (default: 2400 / holdouts, max 20)")
    s.add_argument("--helpers", action="store_true", help="document neverhalt.helpers.closure in the prompt")
    s.add_argument("--samples", type=int, default=32)
    s.add_argument("--concurrency", type=int, default=8)
    a = sub.add_parser("apply", help="run one existing decider on the holdouts left by run(s); writes a checkable run")
    a.add_argument("--n", type=int, default=4)
    a.add_argument("--k", type=int, default=2)
    a.add_argument("--base", required=True, help="run(s), comma-separated, whose certificates are kept")
    a.add_argument("--decider", required=True)
    a.add_argument("--limit", type=float, default=0.5, help="seconds per machine")
    a.add_argument("--name", required=True)
    s.add_argument("--minutes", type=float, default=25.0, help="time box; samples still running are dropped")
    s.add_argument("--name", required=True)
    args = parser.parse_args()

    if args.cmd == "doctor":
        return 0 if doctor(load_config(ROOT)) else 1
    if args.cmd == "check":
        return 0 if verify(run_dir(args.run)) else 1
    if args.cmd == "scale":
        from .scale import scale
        scale(args.n, args.k, [run_dir(b) for b in args.base.split(",")], args.name, args.samples, args.concurrency,
              args.minutes, hints=tuple(h for h in args.hint.split(",") if h), limit=args.limit, helpers=args.helpers)
    if args.cmd == "apply":
        from .scale import apply
        apply(args.n, args.k, [run_dir(b) for b in args.base.split(",")], Path(args.decider), args.name, args.limit)
        return 0

    store = Store()
    cfg = None if args.cmd == "replay" or args.offline else load_config(ROOT)
    serve(store, args.host, args.port)
    print(f"gallery: http://{args.host}:{args.port}/")
    if args.cmd == "replay":
        replay(store, run_dir(args.run) / "journal.jsonl", args.speed, loop=args.loop)
    else:
        if args.enter:
            input("open the gallery, then press Enter to start the hunt … ")
        name = args.name or (f"bb{args.n}" + (f"x{args.k}" if args.k != 2 else "") + time.strftime("-%H%M%S")
                             + ("-offline" if args.offline else ""))
        summary = hunt(store, args.n, args.k, name, cfg, max_rounds=args.rounds, hints=not args.no_hints,
                       round_budget=args.round_budget, resume=run_dir(args.resume) if args.resume else None)
        print(f"{summary['theorem'] or 'no theorem'} · rounds: "
              + ", ".join(f"{t['name']} ({t['proved']})" for t in summary["rounds"])
              + f" · unproven: {len(summary['unproven'])} · recorded in runs/{name}")
    if args.cmd == "hunt" and args.exit:
        return 0 if summary["theorem"] else 2
    print("run finished; the gallery stays up until Ctrl-C")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LLMError as e:
        sys.exit(f"neverhalt: {e}")
