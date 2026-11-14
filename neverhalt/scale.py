"""Test-time scaling: many independent Ripple samples attack the same holdouts in parallel.

Every sample is a fresh conversation (no hints, no history beyond the toolbox names) that writes one decider.
The kernel checks every certificate, so taking the union over samples is sound: one valid proof per machine is
enough. The output is the curve "holdouts still unproven" vs "number of samples", plus a certificate file
covering base + new proofs that `python3 -m neverhalt check <name>` re-verifies from scratch.
"""
from __future__ import annotations

import gzip
import json
import multiprocessing
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as Timeout, as_completed
from pathlib import Path

from . import tm as tmlib
from .helpers import closure
from .hunt import HINTS, ROOT, extract_code, system_prompt
from .llm import LLMError, chat, load_config
from .runner import Runner
from .tnf import enumerate_tnf

REPAIR = "Your reply has no usable decider. Send it again: notes, and code = the complete module defining NAME and decide(tm)."
# Constrained decoding: the reply must be this JSON object from its first token. Without it, Ripple's replies on
# the hardest holdouts were 6000 tokens of thinking with no code at all.
FORMAT = {"type": "json_schema", "json_schema": {"name": "decider", "strict": True, "schema": {
    "type": "object", "additionalProperties": False, "required": ["notes", "code"],
    "properties": {"notes": {"type": "string"}, "code": {"type": "string"}}}}}


def code_of(content: str) -> str | None:
    """The decider source from a JSON reply; falls back to a fenced block if the provider ignored the format."""
    try:
        code = json.loads(content).get("code") or ""
    except (ValueError, AttributeError):
        return extract_code(content)
    code = extract_code(code) or code
    return code if "def decide" in code else None


def curve_svg(points: list[tuple[int, int]], start: int, title: str) -> str:
    w, h, pad = 720, 360, 56
    last = max([k for k, _ in points] + [1])
    x = lambda k: pad + (w - 2 * pad) * k / last
    y = lambda v: h - pad - (h - 2 * pad) * v / max(start, 1)
    path = f"M{x(0):.1f},{y(start):.1f}" + "".join(f" H{x(k):.1f} V{y(v):.1f}" for k, v in points)
    marks = {1, 2, 4, 8, 16, 32, 64, last}
    labels = "".join(f'<text x="{x(k):.1f}" y="{y(v) - 8:.1f}" fill="#7CFFB2" text-anchor="middle">{v}</text>'
                     f'<text x="{x(k):.1f}" y="{h - pad + 18}" fill="#888" text-anchor="middle">{k}</text>'
                     for k, v in points if k in marks)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="monospace" font-size="13">'
            f'<rect width="{w}" height="{h}" fill="#0b0f14"/>'
            f'<line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{h - pad}" stroke="#444"/>'
            f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{h - pad}" stroke="#444"/>'
            f'<path d="{path}" fill="none" stroke="#7CFFB2" stroke-width="2.5"/>{labels}'
            f'<text x="{pad - 8}" y="{y(start) + 4:.1f}" fill="#888" text-anchor="end">{start}</text>'
            f'<text x="{pad - 8}" y="{y(0) + 4:.1f}" fill="#888" text-anchor="end">0</text>'
            f'<text x="{w / 2}" y="28" fill="#eee" text-anchor="middle">{title}</text>'
            f'<text x="{w / 2}" y="{h - 14}" fill="#aaa" text-anchor="middle">independent Ripple samples (each writes one decider)</text>'
            f'<text x="18" y="{h / 2}" fill="#aaa" text-anchor="middle" transform="rotate(-90 18 {h / 2})">holdouts still unproven</text>'
            "</svg>")


def scale(n: int, k: int, bases: list[Path], name: str, samples: int, concurrency: int, minutes: float, seed: int = 0,
          hints: tuple[str, ...] = (), limit: float | None = None, helpers: bool = False) -> dict:
    """bases: finished runs whose certificates are kept (their union); hints: keys of hunt.HINTS added to every prompt."""
    out = ROOT / "runs" / name
    (out / "deciders").mkdir(parents=True, exist_ok=True)
    e = enumerate_tnf(n, k, 300, ROOT / "cache")
    label = f"BB({n})" if k == 2 else f"BB({n},{k})"
    certs: dict[str, dict] = {}
    rounds = []
    for base in bases:
        rounds += json.loads((base / "summary.json").read_text()).get("rounds", [])
        with gzip.open(base / "certs.jsonl.gz", "rt") as lines:
            for line in lines:
                entry = json.loads(line)
                certs.setdefault(entry["tm"], entry["cert"])
    holdouts = [m for m in e["holdouts"] if m not in certs]
    start = len(holdouts)
    limit = limit or min(20.0, max(0.05, 2400.0 / max(start, 1)))
    cfg = load_config(ROOT)
    system = system_prompt(label, n, k, e) + (
        "\n\nTHIS RUN: reply with a JSON object {\"notes\": ..., \"code\": ...} instead of the format above: notes = two "
        "to four sentences, code = the complete Python module (no markdown fences). Many independent attempts run in "
        "parallel, so a bold, different idea is worth more than a cautious repeat of the earlier deciders.")
    if helpers:
        system += ("\n\nHELPER in the sandbox (untrusted like your code; the kernel still checks everything):\n"
                   "    from neverhalt.helpers import closure\n    closure.__doc__: " + closure.__doc__.strip())
    toolbox = "; ".join(f'"{t["name"]}" proved {t["proved"]}' for t in rounds if t["proved"])
    hint_text = "".join(f"\n\nHINT: {HINTS[h]}" for h in hints)
    runner, lock, union, t0 = Runner(), threading.Lock(), {}, time.time()
    log = (out / "samples.jsonl").open("w")
    quiet = lambda *_: None
    print(f"{label}: {start} holdouts left after {', '.join(b.name for b in bases)}; {samples} samples, "
          f"{concurrency} in parallel, {int(limit * 1000)} ms per machine, hints: {', '.join(hints) or 'none'}", flush=True)

    def one(i: int) -> dict:
        rng = random.Random(seed * 100_003 + i)
        shown = rng.sample(holdouts, min(5, start))
        user = (f"Holdouts remaining: {start} of {len(e['holdouts'])}, after earlier deciders: {toolbox}. "
                f"Time budget: {int(limit * 1000)} ms per machine.\n\nSample of the remaining holdouts:\n\n"
                + "\n\n".join(f"--- {m}\n{tmlib.diagram(m, 36, 44)}" for m in shown) + hint_text + "\n\nWrite the next decider.")
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        rec = {"sample": i, "calls": [], "status": "no code", "proved": 0}
        try:
            reply = chat(cfg, msgs, quiet, quiet, quiet, extra={"response_format": FORMAT})
            rec["calls"].append({key: reply[key] for key in ("provider", "prompt_tokens", "completion_tokens", "cost", "seconds", "finish")})
            source = code_of(reply["content"])
            if not source:
                msgs += [{"role": "assistant", "content": reply["content"] or "(no visible reply)"},
                         {"role": "user", "content": REPAIR}]
                reply = chat(cfg, msgs, quiet, quiet, quiet, extra={"response_format": FORMAT})
                rec["calls"].append({key: reply[key] for key in ("provider", "prompt_tokens", "completion_tokens", "cost", "seconds", "finish")})
                source = code_of(reply["content"])
        except LLMError as err:
            rec["status"] = f"api error: {str(err)[:200]}"
            return rec
        if not source:
            return rec
        if "neverhalt.reference" in source:  # the bundled reference deciders are not Ripple's work
            rec["status"] = "skipped: imports neverhalt.reference"
            return rec
        path = out / "deciders" / f"s{i:03d}.py"
        path.write_text(source)
        found = re.search(r"""^NAME\s*=\s*["'](.+?)["']""", source, re.M)
        rec["name"], rec["status"], rec["tally"], new = (found[1] if found else f"sample {i}"), "ran", {}, {}
        for chunk, results in runner.run(path, holdouts, limit):
            for m, (status, payload) in zip(chunk, results):
                rec["tally"][status] = rec["tally"].get(status, 0) + 1
                if status == "proved":
                    new[m] = payload["cert"]
        rec["proved"], rec["machines"] = len(new), new
        return rec

    curve, done, cost, recent = [], 0, 0.0, []
    title = f"{label}: test-time scaling on the {start} hardest holdouts"
    with gzip.open(out / "certs.jsonl.gz", "wt") as f:  # base proofs now; new ones are appended as gzip members
        for m, c in certs.items():
            f.write(json.dumps({"tm": m, "cert": c}, separators=(",", ":")) + "\n")

    def checkpoint() -> dict:
        """summary.json, curve.svg and an auto-refreshing live.html, rewritten after every sample."""
        unproven = [m for m in holdouts if m not in union]
        summary = {"name": name, "n": n, "k": k, "max_steps": 300, "model": cfg.model,
                   "base": ",".join(b.name for b in bases), "hints": list(hints),
                   "theorem": None if unproven else f"{label} = {e['champion']['steps']}", "champion": e["champion"],
                   "holdouts_start": start, "unproven": unproven, "samples_done": done, "cost_usd": round(cost, 4),
                   "seconds": round(time.time() - t0), "curve": curve, "rounds": []}
        (out / "summary.json").write_text(json.dumps(summary, indent=1))
        svg = curve_svg(curve, start, title)
        (out / "curve.svg").write_text(svg)
        rows = "".join(f"<tr><td>{r['sample']}</td><td>{r.get('name', '')}</td><td>{r['status'][:40]}</td>"
                       f"<td>{r['proved']}</td><td>+{r['new_in_union']}</td></tr>" for r in reversed(recent[-15:]))
        (out / "live.html").write_text(
            "<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=10><title>NEVERHALT scaling</title>"
            "<body style='background:#0b0f14;color:#ddd;font:14px monospace;margin:24px'>"
            f"<h2>{title}</h2><p>{done} Ripple samples · {start - len(unproven)}/{start} proven · ${cost:.3f} · "
            f"{round(time.time() - t0)} s · {summary['theorem'] or 'no theorem yet'}</p><div style='max-width:900px'>{svg}</div>"
            "<table cellpadding=6><tr><th>sample</th><th>decider</th><th>status</th><th>proved</th><th>new</th></tr>"
            f"{rows}</table>")
        return summary

    pool = ThreadPoolExecutor(concurrency)
    futures = [pool.submit(one, i) for i in range(samples)]
    try:
        for future in as_completed(futures, timeout=minutes * 60):
            rec = future.result()
            with lock:
                done += 1
                cost += sum(c["cost"] for c in rec["calls"])
                fresh = {m: c for m, c in rec.pop("machines", {}).items() if m not in union}
                union.update(fresh)
                curve.append((done, start - len(union)))
                rec["new_in_union"] = len(fresh)
                recent.append(rec)
                log.write(json.dumps(rec) + "\n")
                log.flush()
                if fresh:
                    with gzip.open(out / "certs.jsonl.gz", "at") as f:
                        for m, c in fresh.items():
                            f.write(json.dumps({"tm": m, "cert": c}, separators=(",", ":")) + "\n")
                summary = checkpoint()
            print(f"[{time.time() - t0:5.0f}s] {done}/{samples} · sample {rec['sample']} {rec.get('name', '')!r} "
                  f"{rec['status']} · proved {rec['proved']} (+{len(fresh)} new) · unproven {start - len(union)} · "
                  f"${cost:.3f}", flush=True)
            if len(union) == start:
                break
    except Timeout:
        print(f"time box of {minutes} min reached after {done} samples", flush=True)

    summary = checkpoint()
    print(f"{summary['theorem'] or 'no theorem'} · {len(union)}/{start} proven by {done} samples · ${cost:.3f} · "
          f"runs/{name}/live.html", flush=True)
    log.close()
    for child in multiprocessing.active_children():  # decider workers would otherwise outlive os._exit
        child.terminate()
    os._exit(0)  # do not wait for model calls still in flight


def apply(n: int, k: int, bases: list[Path], decider: Path, name: str, limit: float) -> None:
    """Run one existing (Ripple-written) decider on the holdouts the bases left; write a checkable run directory."""
    out = ROOT / "runs" / name
    (out / "deciders").mkdir(parents=True, exist_ok=True)
    e = enumerate_tnf(n, k, 300, ROOT / "cache")
    certs: dict[str, dict] = {}
    for base in bases:
        with gzip.open(base / "certs.jsonl.gz", "rt") as lines:
            for line in lines:
                entry = json.loads(line)
                certs.setdefault(entry["tm"], entry["cert"])
    holdouts = [m for m in e["holdouts"] if m not in certs]
    copy = out / "deciders" / decider.name
    copy.write_text(decider.read_text())
    print(f"applying {decider} to {len(holdouts)} holdouts, {int(limit * 1000)} ms per machine", flush=True)
    tally, new, t0 = {}, {}, time.time()
    runner = Runner()
    for chunk, results in runner.run(copy, holdouts, limit):
        for m, (status, payload) in zip(chunk, results):
            tally[status] = tally.get(status, 0) + 1
            if status == "proved":
                new[m] = payload["cert"]
    runner.close()
    with gzip.open(out / "certs.jsonl.gz", "wt") as f:
        for m, c in {**certs, **new}.items():
            f.write(json.dumps({"tm": m, "cert": c}, separators=(",", ":")) + "\n")
    unproven = [m for m in holdouts if m not in new]
    label = f"BB({n})" if k == 2 else f"BB({n},{k})"
    (out / "summary.json").write_text(json.dumps({
        "name": name, "n": n, "k": k, "max_steps": 300, "base": ",".join(b.name for b in bases),
        "decider": str(decider), "tally": tally, "holdouts_start": len(holdouts), "unproven": unproven,
        "theorem": None if unproven else f"{label} = {e['champion']['steps']}", "rounds": [
            {"round": 1, "name": f"{decider.parent.parent.name}/{decider.name}", "proved": len(new)}]}, indent=1))
    print(f"{decider.name}: {tally} · {len(new)} new proofs · {len(unproven)} left · {time.time() - t0:.0f} s", flush=True)
