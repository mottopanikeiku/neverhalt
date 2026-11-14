"""The agent loop: the model writes deciders, the kernel judges, the wall lights up."""
from __future__ import annotations

import gzip
import itertools
import json
import random
import re
import time
from pathlib import Path

from . import kernel, tm as tmlib
from .llm import Config, LLMError, chat
from .runner import BWRAP, Runner
from .tnf import enumerate_tnf

ROOT = Path(__file__).resolve().parent.parent
WALL = 1400  # tiles on the gallery wall
SAMPLES = 5  # holdouts shown to the model each round
REFERENCE = ["r1_cyclers", "r2_translated", "r3_cps", "r4_automata", "r5_far"]
HINTS = {  # given only after a round that proved nothing, and always shown on the wall
    "tcycle": "machines that drift can repeat their local picture: compare the configuration at successive moments "
              "when the head reaches a new leftmost or rightmost cell (same state, same tape near the head). A match "
              "gives a cycle certificate with t = the earlier moment and p = the time between them.",
    "cps": "for cps certificates, let each automaton remember the last n cells of its half-tape and compute the "
           "smallest closed context set by fixpoint iteration from the blank context: create automaton states and "
           "transitions only when a context needs them (null elsewhere), give up when a halting context shows up, "
           "then retry with a larger n.",
    "automata": "the survivors are counters and bouncers: no window of recent cells is enough. Search over small "
                "automata instead: enumerate every transition table with 1, 2, then 3 states per side (state 0 loops "
                "on symbol 0), compute the smallest closed context set for each pair, and stop at the first pair "
                "whose closure has no halting context. Keep only the transitions the closure used (null elsewhere).",
    "far": "what is left needs automata found by search rather than designed (finite automata reduction): enumerate "
           "DFAs for one half-tape in BFS-canonical order with growing size, up to about 10 states, and prune a "
           "partial table as soon as the tapes that can lead to a halt (computed backwards from the halting "
           "transitions) are forced to include the blank tape. For a surviving DFA the other half-tape's language "
           "is an NFA: reverse-determinize it into a far-to-head DFA, then run the closed-context fixpoint to emit "
           "the certificate.",
}


def system_prompt(label: str, n: int, k: int, e: dict) -> str:
    steps = e["champion"]["steps"]
    return f"""You are NEVERHALT, an automated mathematician. Goal: prove the Busy Beaver value {label}, the largest number of steps any halting {n}-state, {k}-symbol Turing machine takes from a blank tape.

HOW THE PROOF WORKS
- Every such machine (up to symmetry) was enumerated and simulated for {e['max_steps']} steps. {e['halting']} of {e['enumerated']} halted; the longest took {steps} steps. The other {len(e['holdouts'])} were still running: the HOLDOUTS.
- If every holdout provably never halts, then {label} = {steps}. One unproven holdout and there is no theorem.
- You prove non-halting by writing DECIDERS: Python programs that inspect one machine and return a CERTIFICATE. A small trusted kernel checks every certificate. You are not trusted; the kernel is. A wrong certificate is simply rejected and costs nothing, so any search strategy is allowed. Only the certificate has to be right.

MACHINES
{tmlib.__doc__.strip()}
Helpers:
    from neverhalt.tm import parse, run
    parse(tm) -> (table, n_states, n_symbols)   # table[(state, symbol)] = (write, move, next_state); move is +1 or -1; states are ints, A = 0; halting transitions are absent
    run(tm, max_steps) -> (halted, steps, state, pos, tape)   # tape: dict position -> non-zero symbol
    from neverhalt.kernel import check, Reject   # check(tm, cert) returns the kind or raises Reject: test a certificate before returning it

CERTIFICATES: the exact rules of the kernel
{kernel.__doc__.split(chr(10) * 2, 1)[1].strip()}
Kernel limits: t + p <= {kernel.MAX_STEPS}; at most {kernel.MAX_STATES} states per automaton and {kernel.MAX_CONTEXTS} contexts.

DECIDER CONTRACT
    NAME = "two or three words"
    def decide(tm: str) -> dict | None    # a certificate, or None when this decider has nothing for the machine
- Python standard library only; no files, network, threads or subprocesses. It runs sandboxed with a time budget per machine (stated each round, it grows as the holdouts shrink), then it is killed.
- It runs on every remaining holdout. Returning None is free. Never guess: return a certificate only when your search found one.
- The sandbox and the kernel are known to work: every round must be a real attempt to prove machines, never a placeholder or a test.

EACH ROUND you get the kernel's verdict on your last decider and a sample of the remaining holdouts as space-time diagrams: one line per step, time flows down, '.' is 0, '#' is 1, and the head is drawn as its state letter (lowercase on a 0, uppercase on a non-zero cell).

REPLY FORMAT, every round:
1. Two to four plain sentences, lab-notebook style: what you see in the holdouts and what you will try. This text is projected on a wall for an audience.
2. Exactly one ```python fenced block with the complete decider module.
Nothing after the code block."""


def extract_code(reply: str) -> str | None:
    """The last fenced block; tolerates a missing closing fence (reply cut at the token limit)."""
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)(?:```|\Z)", reply, re.S)
    blocks = [b for b in blocks if "def decide" in b]
    return blocks[-1].rstrip() + "\n" if blocks else None


def cert_summary(kind: str, cert: dict) -> dict:
    if cert["kind"] == "cycle":
        return {"kind": kind, "t": cert["t"], "p": cert["p"]}
    return {"kind": kind, "nl": len(cert["left"]), "nr": len(cert["right"]), "contexts": len(cert["contexts"])}


class Journal:
    """Applies events to the live store and records them, timestamped, for replay."""

    def __init__(self, store, path: Path):
        self.store, self.t0, self.file = store, time.time(), path.open("w")

    def emit(self, event: dict):
        self.store.apply(event)
        self.file.write(json.dumps({"t": round(time.time() - self.t0, 3), **event}) + "\n")
        self.file.flush()


class Notebook:
    """Log lines for the page. Streamed model text is coalesced into ~10 events per second."""

    def __init__(self, journal: Journal):
        self.journal, self.ids = journal, itertools.count(1)
        self.kind, self.sid, self.buf, self.last = None, None, "", 0.0

    def say(self, kind: str, text: str):
        self.flush()
        self.journal.emit({"type": "log", "kind": kind, "text": text, "stream": None})

    def stream(self, kind: str, text: str):
        if kind != self.kind:
            self.flush()
            self.kind, self.sid = kind, next(self.ids)
        self.buf += text
        if len(self.buf) >= 40 or time.time() - self.last > 0.1:
            self._send()

    def _send(self):
        if self.buf:
            self.journal.emit({"type": "log", "kind": self.kind, "text": self.buf, "stream": self.sid})
            self.buf, self.last = "", time.time()

    def flush(self):
        self._send()
        self.kind = None


def productive_rounds(journal: Path) -> list[int]:
    """Rounds of a recorded run whose decider got at least one certificate accepted by the kernel."""
    rounds, current = [], 0
    with journal.open() as lines:
        for line in lines:
            event = json.loads(line)
            if event["type"] == "state" and "round" in event["patch"]:
                current = event["patch"]["round"]
            elif event["type"] == "log" and event["kind"] == "kernel":
                found = re.search(r": accepted (\d+) ·", event["text"])
                if found and int(found[1]) > 0:
                    rounds.append(current)
    return rounds


def hunt(store, n: int, k: int, name: str, cfg: Config | None, max_rounds: int = 12, max_steps: int = 300,
         seed: int = 0, hints: bool = True, round_budget: float = 300.0, resume: Path | None = None) -> dict:
    """cfg=None runs the bundled reference deciders instead of the model (offline mode)."""
    run_dir = ROOT / "runs" / name
    (run_dir / "deciders").mkdir(parents=True, exist_ok=True)
    journal = Journal(store, run_dir / "journal.jsonl")
    note = Notebook(journal)
    label = f"BB({n})" if k == 2 else f"BB({n},{k})"
    model = cfg.model if cfg else "offline reference deciders (no model)"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "seconds": 0.0, "calls": 0}
    journal.emit({"type": "reset", "state": {"problem": {"name": label, "states": n, "symbols": k},
                                             "phase": "enumerating", "model": model}})
    note.say("system", f"Enumerating every {n}-state, {k}-symbol Turing machine in tree normal form, "
                       f"{max_steps} steps each.")
    e = enumerate_tnf(n, k, max_steps, ROOT / "cache")
    holdouts, champion = list(e["holdouts"]), e["champion"]
    n0 = len(holdouts)
    rng = random.Random(seed)
    wall = {m: i for i, m in enumerate(holdouts if n0 <= WALL else sorted(rng.sample(holdouts, WALL)))}
    kinds: dict[str, int] = {}
    history = [{"round": 0, "holdouts": n0, "label": "simulation"}]
    proved = 0

    def patch(**extra):
        journal.emit({"type": "state", "patch": {
            "counts": {"enumerated": e["enumerated"], "halting": e["halting"], "holdouts_initial": n0,
                       "holdouts": n0 - proved, "proved": proved},
            "by_kind": dict(kinds), **extra}})

    journal.emit({"type": "machines", "items": [
        {"id": i, "tm": m, "status": "holdout", "round": None, "decider": None, "cert": None} for m, i in wall.items()]})
    patch(phase="hunting", champion=champion, history=history)
    note.say("system", f"{e['enumerated']} machines. {e['halting']} halt; the longest runs {champion['steps']} steps. "
                       f"{n0} are still running after {max_steps} steps: the holdouts. "
                       f"If none of them ever halts, {label} = {champion['steps']}.")
    if not BWRAP:
        note.say("error", "bubblewrap not found: deciders run with resource limits only, not in a sandbox")

    runner = Runner()
    certs = gzip.open(run_dir / "certs.jsonl.gz", "wt")
    messages = [{"role": "system", "content": system_prompt(label, n, k, e)}] if cfg else []
    toolbox: list[dict] = []
    hinted: set[str] = set()
    verdict, stalls, failures, r, hint_due = "", 0, 0, 0, False

    def call(msgs: list[dict]) -> dict:
        """One model call: stream into the notebook, account usage, log which provider served it."""
        reply = chat(cfg, msgs, lambda t: note.stream("model", t), lambda t: note.stream("reasoning", t),
                     lambda delay, err: note.say("system", f"Ripple endpoint busy ({err}); retrying in {delay:.0f} s"))
        note.flush()
        note.say("system", f"Ripple replied via {reply['provider'] or 'unknown provider'} · "
                           f"{reply['prompt_tokens']} tokens in, {reply['completion_tokens']} out · "
                           f"{reply['seconds']:.0f} s · ${reply['cost']:.4f}")
        usage["prompt_tokens"] += reply["prompt_tokens"]
        usage["completion_tokens"] += reply["completion_tokens"]
        usage["seconds"] = round(usage["seconds"] + reply["seconds"], 1)
        usage["calls"] += 1
        usage["cost_usd"] = round(usage["cost_usd"] + reply["cost"], 4)
        journal.emit({"type": "state", "patch": {"usage": dict(usage)}})
        return reply

    replay: list[Path] = []  # deciders Ripple wrote in an earlier run, re-run without model calls
    if resume is not None:
        replay = [p for r_ in productive_rounds(resume / "journal.jsonl")
                  if (p := resume / "deciders" / f"r{r_:02d}.py").exists()]
        note.say("system", f"Resuming from run {resume.name}: re-running the {len(replay)} deciders Ripple wrote there "
                           "that proved machines, then continuing live.")
    n_replay = len(replay)

    try:
        while holdouts and r < max_rounds + n_replay and stalls < 4 and failures < 3:
            r += 1
            journal.emit({"type": "state", "patch": {"round": r}})
            # seconds per machine: about 2400 CPU-seconds per round, so the budget grows as the holdouts shrink
            limit = min(20.0, max(0.05, 2400.0 / len(holdouts)))
            replayed = bool(replay)
            if replayed:
                earlier = replay.pop(0)
                source = earlier.read_text()
                note.say("system", f"Re-running Ripple's decider {earlier.parent.parent.name}/{earlier.name} (no model call).")
            elif cfg is None:
                if r > len(REFERENCE):
                    break
                source = (ROOT / "neverhalt" / "reference" / f"{REFERENCE[r - 1]}.py").read_text()
                note.say("model", f"(offline: bundled reference decider, no model call)\n\n```python\n{source}```")
            else:
                head = [f"ROUND {r}. Holdouts remaining: {len(holdouts)} of {n0}. "
                        f"Time budget this round: {int(limit * 1000)} ms per machine."]
                if verdict:
                    head.append(verdict)
                if toolbox:
                    head.append("Toolbox so far: " + "; ".join(
                        f'round {t["round"]} "{t["name"]}" proved {t["proved"]}' for t in toolbox))
                if hint_due and hints:  # only after a decider ran and proved nothing
                    hint_due = False
                    order = [h for h in ("tcycle", "cps") if h not in kinds] + ["automata", "far"]
                    key = next((h for h in order if h not in hinted), "far")
                    hinted.add(key)
                    hint = HINTS[key]
                    head.append("HINT: " + hint)
                    note.say("system", f"hint given to the model: {hint}")
                sample = rng.sample(holdouts, min(SAMPLES, len(holdouts)))
                diagrams = "\n\n".join(f"--- {m}\n{tmlib.diagram(m, 36, 44)}" for m in sample)
                ask = (f"Sample of the remaining holdouts ({len(sample)} of {len(holdouts)}):\n\n{diagrams}\n\n"
                       "Write the next decider.")
                note.say("system", f"Round {r}: {len(holdouts)} holdouts left. Asking {model.split('/')[-1]} for a decider.")
                turn = [{"role": "user", "content": "\n".join(head + [ask])}]
                try:
                    reply = call(messages + turn)
                    turn.append({"role": "assistant", "content": reply["content"] or "(no visible reply)"})
                    source = extract_code(reply["content"])
                    if not source:  # one repair turn: Ripple sometimes stops after its notes or thinks past the limit
                        note.say("system", "no python block in the reply; asking Ripple for the code")
                        turn.append({"role": "user", "content": "Your reply has no ```python block. Send the complete "
                                     "decider module now: exactly one ```python block defining NAME and decide(tm), "
                                     "no other text."})
                        reply = call(messages + turn)
                        turn.append({"role": "assistant", "content": reply["content"] or "(no visible reply)"})
                        source = extract_code(reply["content"])
                except LLMError as err:
                    note.say("error", str(err))
                    failures += 1
                    r -= 1
                    time.sleep(3)
                    continue
                # history keeps the verdicts but not the diagrams: the model only needs the newest sample
                turn[0] = {"role": "user", "content": "\n".join(head + ["(sample diagrams omitted)"])}
                messages += turn
                if not source:
                    cut = " It was cut off at the token limit: be briefer." if reply["finish"] == "length" else ""
                    verdict = ("Your last reply contained no ```python block defining decide()." + cut
                               + " Reply with the notebook sentences, then exactly one complete ```python block.")
                    note.say("error", "no decider in the reply" + cut)
                    stalls += 1
                    continue
                for _ in range(2):  # smoke test on a few holdouts: crashes and timeouts go straight back to Ripple
                    probe = rng.sample(holdouts, min(24, len(holdouts)))
                    smoke = run_dir / "deciders" / f"r{r:02d}-smoke.py"
                    smoke.write_text(source)
                    bad = [(m, p) for chunk, results in runner.run(smoke, probe, limit)
                           for m, (status, p) in zip(chunk, results) if status in ("error", "fatal")]
                    smoke.unlink()
                    if len(bad) * 2 < len(probe):
                        break
                    note.say("system", f"smoke test: {len(bad)} of {len(probe)} sample machines crashed or timed out; "
                                       "sending the errors back to Ripple")
                    fix = [{"role": "user", "content": f"Smoke test of that decider on {len(probe)} holdouts: {len(bad)} "
                            f"crashed or timed out ({int(limit * 1000)} ms per machine). Examples:\n"
                            + "\n".join(f"  {m}: {str(p)[-400:]}" for m, p in bad[:3])
                            + "\nFix it and send the complete module again in one ```python block."}]
                    try:
                        reply = call(messages + fix)
                    except LLMError as err:
                        note.say("error", str(err))
                        break
                    messages += fix + [{"role": "assistant", "content": reply["content"] or "(no visible reply)"}]
                    fixed = extract_code(reply["content"])
                    if not fixed:
                        break
                    source = fixed
            path = run_dir / "deciders" / f"r{r:02d}.py"
            path.write_text(source)
            found = re.search(r"""^NAME\s*=\s*["'](.+?)["']""", source, re.M)
            decider = (found[1] if found else f"round {r}") + (" (replayed)" if replayed else "")

            tally = {"proved": 0, "none": 0, "rejected": 0, "error": 0, "fatal": 0}
            round_kinds: dict[str, int] = {}
            rejects, errors, fatal, done, t0 = [], [], None, set(), time.time()
            for machines, results in runner.run(path, holdouts, limit, t0 + round_budget):
                items = []
                for m, (status, payload) in zip(machines, results):
                    tally[status] += 1
                    if status == "proved":
                        kind = payload["kind"]
                        done.add(m)
                        proved += 1
                        kinds[kind] = kinds.get(kind, 0) + 1
                        round_kinds[kind] = round_kinds.get(kind, 0) + 1
                        certs.write(json.dumps({"tm": m, "cert": payload["cert"]}, separators=(",", ":")) + "\n")
                        if m in wall:
                            items.append({"id": wall[m], "tm": m, "status": kind, "round": r, "decider": decider,
                                          "cert": cert_summary(kind, payload["cert"])})
                    elif status == "rejected" and len(rejects) < 3:
                        rejects.append(f"  rejected {m}: {payload}")
                    elif status == "error" and len(errors) < 3:
                        errors.append(f"  error on {m}: {payload}")
                    elif status == "fatal":
                        fatal = payload
                if items:
                    journal.emit({"type": "machines", "items": items})
                patch()

            skipped = len(holdouts) - sum(tally.values())  # chunks cancelled by the round time budget
            holdouts = [m for m in holdouts if m not in done]
            history.append({"round": r, "holdouts": len(holdouts), "label": decider})
            toolbox.append({"round": r, "name": decider, "proved": tally["proved"]})
            breakdown = ", ".join(f"{v} {kd}" for kd, v in round_kinds.items())
            if fatal:
                verdict = f'Verdict on "{decider}": the module failed to load or defines no decide():\n{fatal}'
                note.say("error", f"{decider}: " + fatal.strip().splitlines()[-1])
            else:
                skip = f" · not run {skipped} (round time budget of {round_budget:.0f} s used up)" if skipped else ""
                verdict = "\n".join([
                    f'Verdict on "{decider}": kernel ACCEPTED {tally["proved"]}' + (f" ({breakdown})" if breakdown else "")
                    + f' · REJECTED {tally["rejected"]} · no certificate {tally["none"]} · errors {tally["error"]}{skip}.',
                    *rejects, *errors])
                note.say("kernel", f"{decider}: accepted {tally['proved']} · rejected {tally['rejected']} · "
                                   f"no certificate {tally['none']} · errors {tally['error']}{skip}"
                                   + (f" · {breakdown}" if breakdown else "") + f"  [{time.time() - t0:.1f}s]")
            patch(history=history)
            stalls = 0 if tally["proved"] else stalls + 1
            hint_due = not tally["proved"]
    finally:
        runner.close()
        certs.close()

    theorem = None if holdouts else f"{label} = {champion['steps']}"
    if theorem:
        note.say("kernel", f"Every holdout carries a kernel-checked certificate of non-halting. {theorem} ∎  "
                           f"Champion {champion['tm']} halts after {champion['steps']} steps; nothing runs longer.")
    else:
        note.say("system", f"{len(holdouts)} holdouts remain unproven after round {r}. No theorem.")
    patch(phase="proved" if theorem else "stalled", theorem=theorem)
    summary = {"name": name, "n": n, "k": k, "max_steps": max_steps, "model": model, "theorem": theorem,
               "champion": champion, "enumerated": e["enumerated"], "halting": e["halting"], "holdouts_initial": n0,
               "unproven": holdouts, "by_kind": kinds, "rounds": toolbox, "usage": usage}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def verify(run_dir: Path) -> bool:
    """Re-derive the theorem from a finished run using only the enumerator and the kernel: no model, no deciders."""
    summary = json.loads((run_dir / "summary.json").read_text())
    n, k = summary["n"], summary["k"]
    label = f"BB({n})" if k == 2 else f"BB({n},{k})"
    e = enumerate_tnf(n, k, summary["max_steps"], None)
    certs = {}
    with gzip.open(run_dir / "certs.jsonl.gz", "rt") as lines:
        for line in lines:
            entry = json.loads(line)
            certs[entry["tm"]] = entry["cert"]
    missing, kinds = [], {}
    for m in e["holdouts"]:
        try:
            kind = kernel.check(m, certs[m])
            kinds[kind] = kinds.get(kind, 0) + 1
        except (KeyError, kernel.Reject):
            missing.append(m)
    print(f"{e['enumerated']} machines enumerated from scratch · {e['halting']} halt (longest: {e['champion']['steps']} "
          f"steps, {e['champion']['tm']}) · {len(e['holdouts'])} holdouts")
    print(f"certificates accepted by the kernel: {kinds}")
    if missing:
        print(f"NO THEOREM: {len(missing)} holdouts without a valid certificate, e.g. {missing[:3]}")
        return False
    print(f"{label} = {e['champion']['steps']} ∎")
    return True
