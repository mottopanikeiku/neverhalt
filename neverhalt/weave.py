"""Reverse-engineer the weave: python3 -m neverhalt.weave run easy; ... report.

Run ``preflight`` before any paid call; then ``run easy``, ``run four``,
``run challenge``, ``run diamond`` (or ``run all``), and ``report``.
``report --synthesize`` refreshes winner circuit measurements without a model
call. Runs resume the journal with six rounds by default; an explicit --rounds
override and --stop-at timestamp support an authorized, time-bounded demo run.

All pixels and verdicts are computed here, outside Ripple's read-only sandbox.
A diagram has H rows, starting with the blank tape; halted tapes stay frozen.
The crop includes every head position in rows 0..H-1, including blank cells.
Scoring counts equal overlapping pixels / pixels in the union of both crops;
non-overlapping columns are wrong even when blank. Horizontal shifts are free.

The cached TNF holdouts omit total-transition completions and first-state loops.
Minimality therefore supplements those caches with an exhaustive, target-pruned
blank-tape execution tree. No claim relies on the cache being complete alone.
The circuit is the controller only, NOT the infinite tape or a physical TM.
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import dataclasses
from datetime import datetime
import fcntl
from functools import wraps
from fractions import Fraction
import html
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time

from . import kernel
from .llm import chat, load_config, RIPPLE_MODEL
from .reference.r2_translated import decide
from .tm import parse, run
from .tnf import enumerate_tnf
from .weave_sandbox import trace, evaluate

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
NAMES = ("easy", "four", "challenge", "diamond")
SCORING = """Row t is the binary tape AFTER t steps, starting with row 0 blank.
Crop the candidate to ALL columns visited by the head in rows 0..H-1; do not
truncate to target width. A halted machine's tape/head remain frozen. For each
integer horizontal alignment, equal pixels in overlapping columns are correct;
EVERY pixel in a non-overlapping column is wrong, even if it is blank. Accuracy
is correct pixels / (H * number of columns in the union of the two crops).
Take the best alignment. Ties: fewer declared states, then fewer defined
transitions. Exact requires identical widths and ALL H rows, not just a crop."""


def worker_budget(function):
    """Serialize local CPU stages; concurrent provider requests need no workers."""
    @wraps(function)
    def bounded(*args, **kwargs):
        directory = RUNS / "weave-easy"
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "workers.lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            return function(*args, **kwargs)
    return bounded


def better(a: dict, b: dict | None) -> bool:
    if b is None:
        return True
    return (Fraction(a["correct"], a["total"]), -a["states"], -a["transitions"]) > (
        Fraction(b["correct"], b["total"]), -b["states"], -b["transitions"])


def mirror(tm: str) -> str:
    return tm.translate(str.maketrans("LR", "RL"))


def generate_challenge() -> tuple[str, dict]:
    rng = random.Random(982344)
    best = None
    sampled = 0
    for _ in range(18000):
        sampled += 1
        tm = "_".join("".join(f"{rng.randrange(2)}{rng.choice('LR')}{chr(65 + rng.randrange(5))}"
                              for _ in range(2)) for _ in range(5))
        view = trace(tm, 80)
        if not 8 <= view["width"] <= 44 or view["halted"] or view["visited_states"] != 5:
            continue
        unique = len(set(view["rows"]))
        if unique < 30:
            continue
        cert = decide(tm, 500)
        if not cert or cert["p"] < 8:
            continue
        try:
            kernel.check(tm, cert)
        except kernel.Reject:
            continue
        quality = unique + min(cert["p"], 40) + sum(r.count("#") for r in view["rows"]) / (80 * view["width"])
        if best is None or quality > best[0]:
            best = quality, tm, cert
    if best is None:
        raise RuntimeError("deterministic random sample found no certified rich 5-state target")
    return best[1], {"seed": 982344, "sampled": sampled, "certificate": best[2]}


def prepare(name: str) -> dict:
    directory = RUNS / f"weave-{name}"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "target.json"
    if path.exists():
        return json.loads(path.read_text())
    metadata = {}
    if name == "easy":
        hidden = "1LB0LB_1RA1LA"
    elif name == "four":
        hidden = "1LB0LD_1LC1RC_1RD1RA_1LA0RA"
    elif name == "challenge":
        hidden, metadata = generate_challenge()
    else:
        hidden = None
    if hidden:
        target = trace(hidden, 80)["rows"]
        cert = decide(hidden)
        kernel.check(hidden, cert)
        metadata["certificate"] = cert
    else:
        # Hand-drawn diamond, expanded to 80 rows, 33 columns; deliberately not
        # constrained to the one-cell-per-step tape update law.
        art = ["................#................", "............#.......#............",
               "........#...............#........", "....#.......................#....",
               "#...............................#", "....#.......................#....",
               "........#...............#........", "............#.......#............",
               "................#................", "................................."]
        target = ["." * 33] + [art[(t - 1) // 8] for t in range(1, 80)]
        metadata["hand_drawn_ascii"] = art
    data = {"name": name, "target": target, "hidden_tm": hidden,
            "hidden_states": parse(hidden)[1] if hidden else None, "generation": metadata}
    path.write_text(json.dumps(data, indent=2) + "\n")
    (directory / "target.txt").write_text("\n".join(target) + "\n")
    return data


def sandbox_cmd(code: Path) -> list[str]:
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise RuntimeError("bubblewrap is required: refusing an unsandboxed model program")
    package = ROOT / "neverhalt"
    # /tmp is hidden, and only the allowed modules/cache/search are reintroduced.
    # In particular, neither hidden targets nor .env nor previous reports exist
    # in the child filesystem. /run and /home can contain user credentials.
    cmd = [bwrap, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
           "--tmpfs", "/home", "--tmpfs", "/root", "--tmpfs", "/run", "--tmpfs", "/tmp",
           "--dir", str(ROOT), "--dir", str(package)]
    for filename in ("__init__.py", "tm.py", "tnf.py", "weave_sandbox.py"):
        cmd += ["--ro-bind", str(package / filename), str(package / filename)]
    cmd += ["--ro-bind", str(ROOT / "cache"), str(ROOT / "cache"),
            "--ro-bind", str(code.resolve()), "/tmp/search.py",
            "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
            "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
            sys.executable, "-I", str(package / "weave_sandbox.py"), "/tmp/search.py"]
    return cmd


@worker_budget
def execute(code: Path, target: list[str]) -> dict:
    started = time.monotonic()
    try:
        proc = subprocess.run(sandbox_cmd(code), input=json.dumps(target), text=True,
                              capture_output=True, timeout=100, cwd="/")
        if proc.returncode:
            return {"error": f"sandbox exit {proc.returncode}: {proc.stderr[-2000:]}",
                    "seconds": time.monotonic() - started}
        result = json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, ValueError, OSError, RuntimeError) as exc:
        result = {"error": f"{type(exc).__name__}: {exc}"}
    result["seconds"] = time.monotonic() - started
    return result


def certificate(tm: str, supplied=None) -> dict:
    result = {"proved": False}
    if supplied is not None:
        try:
            kind = kernel.check(tm, supplied)
            if supplied.get("kind") != "cycle":
                raise ValueError("weave requires a cycle certificate")
            result.update(proved=True, kind=kind, certificate=supplied, source="Ripple")
        except (kernel.Reject, ValueError, AttributeError) as exc:
            result["supplied_rejection"] = str(exc)
    if not result["proved"]:
        cert = decide(tm)
        if cert:
            try:
                kind = kernel.check(tm, cert)
                result.update(proved=True, kind=kind, certificate=cert, source="r2_translated.decide")
            except kernel.Reject as exc:
                result["rejection"] = str(exc)
    if result["proved"]:
        cert = result["certificate"]
        result["period"] = cert["p"]
        result["shift"] = run(tm, cert["t"] + cert["p"])[3] - run(tm, cert["t"])[3]
    else:
        result["status"] = "unknown: no accepted cycle certificate found"
    return result


def exact_rows(tm: str, target: list[str]) -> bool:
    rows = trace(tm, len(target))["rows"]
    return rows == target or [r[::-1] for r in rows] == target


def cache_chunk(args) -> dict:
    machines, target, deadline = args
    count = 0
    for tm in machines:
        if time.monotonic() > deadline:
            return {"checked": count, "complete": False}
        count += 1
        if exact_rows(tm, target):
            return {"checked": count, "complete": True, "witness": tm}
    return {"checked": count, "complete": True}


def execution_tree(target: list[str], n: int, deadline: float) -> dict:
    """Complete blank-tape prefix enumeration, including total and halting TMs.

    State labels are introduced in order of first use. Only the first move is
    normalized to R; reflecting target covers L. All possible initial positions
    within the final crop are tried. A visited (state,read) has one transition;
    a new one branches over every direction and existing/new state. The write
    bit is forced by consecutive target rows. Unvisited transitions may halt.
    """
    h, width = len(target), len(target[0])
    nodes = 0
    for reflected in (False, True):
        rows = target if not reflected else [row[::-1] for row in target]
        bits = [sum((c == "#") << x for x, c in enumerate(row)) for row in rows]
        if bits[0]:
            return {"complete": True, "nodes": nodes}
        suffix_same = [False] * h
        suffix_same[-1] = True
        for t in range(h - 2, -1, -1):
            suffix_same[t] = suffix_same[t + 1] and bits[t] == bits[t + 1]
        table = {}

        def visit(t, q, pos, used, lo, hi):
            nonlocal nodes
            nodes += 1
            if nodes % 2048 == 1 and time.monotonic() > deadline:
                raise TimeoutError
            if t == h - 1:
                return dict(table) if lo == 0 and hi == width - 1 else None
            read = (bits[t] >> pos) & 1
            key = q, read
            delta = bits[t] ^ bits[t + 1]
            if delta and delta != 1 << pos:
                return None
            write = (bits[t + 1] >> pos) & 1
            if key in table:
                w, d, q2 = table[key]
                if w != write or not 0 <= pos + d < width:
                    return None
                return visit(t + 1, q2, pos + d, used, min(lo, pos + d), max(hi, pos + d))
            # Undefined transition freezes the tape for the rest of the horizon.
            if suffix_same[t] and lo == 0 and hi == width - 1:
                return dict(table)
            for d in ((1,) if t == 0 else (1, -1)):
                p2 = pos + d
                if not 0 <= p2 < width:
                    continue
                for q2 in range(min(used + 1, n)):
                    table[key] = write, d, q2
                    found = visit(t + 1, q2, p2, max(used, q2 + 1), min(lo, p2), max(hi, p2))
                    if found is not None:
                        return found
                table.pop(key, None)
            return None

        try:
            for origin in range(width):
                found = visit(0, 0, origin, 1, origin, origin)
                if found is not None:
                    tm = "_".join("".join("---" if (q, s) not in found else
                        f"{found[q, s][0]}{'R' if found[q, s][1] > 0 else 'L'}{chr(65 + found[q, s][2])}"
                        for s in range(2)) for q in range(n))
                    tm = mirror(tm) if reflected else tm
                    if trace(tm, h)["rows"] != target:
                        raise RuntimeError("execution-tree witness failed independent trace")
                    return {"complete": True, "nodes": nodes, "witness": tm}
        except TimeoutError:
            return {"complete": False, "nodes": nodes}
    return {"complete": True, "nodes": nodes}


@worker_budget
def minimality(candidate: dict, target: list[str]) -> dict:
    if not candidate["exact"]:
        return {"confirmed": False, "status": "not applicable: no exact match", "checks": []}
    n = candidate["states"]
    checks = []
    for smaller in range(1, min(n, 5)):
        started = time.monotonic()
        deadline = started + 180
        row = {"states": smaller}
        if smaller >= 2:
            cache_path = ROOT / "cache" / f"tnf_{smaller}x2_300.json"
            if not cache_path.exists():
                row["cache"] = "missing; execution tree still covers all machines"
            else:
                machines = enumerate_tnf(smaller, 2, 300, ROOT / "cache")["holdouts"]
                chunks = [machines[i:i + 256] for i in range(0, len(machines), 256)]
                row.update(cached_holdouts=len(machines), cached_checked=0, mirrors=True)
                if smaller <= 3:
                    results = [cache_chunk((chunk, target, deadline)) for chunk in chunks]
                else:
                    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
                        results = list(pool.map(cache_chunk, ((chunk, target, deadline) for chunk in chunks)))
                row["cached_checked"] = sum(r["checked"] for r in results)
                row["cached_complete"] = all(r["complete"] for r in results)
                witness = next((r["witness"] for r in results if r.get("witness")), None)
                if witness:
                    row.update(witness=witness, complete=True, seconds=time.monotonic() - started)
                    checks.append(row)
                    return {"confirmed": False, "status": f"not minimal: {smaller}-state match exists", "checks": checks}
        tree = execution_tree(target, smaller, deadline)
        row.update(tree)
        row["seconds"] = time.monotonic() - started
        checks.append(row)
        if tree.get("witness"):
            return {"confirmed": False, "status": f"not minimal: {smaller}-state match exists", "checks": checks}
        if not tree["complete"]:
            return {"confirmed": False, "status": f"exhaustive through {smaller - 1}; {smaller} states unchecked (3-minute limit)", "checks": checks}
    if n > 5:
        return {"confirmed": False, "status": "exhaustive through 4; larger state counts unchecked", "checks": checks}
    return {"confirmed": True, "status": f"minimum {n} states: exhaustive exclusion of every smaller state count", "checks": checks}


def verilog(tm: str, combinational: bool = False) -> str:
    table, n, _ = parse(tm)
    bits = max(1, (n - 1).bit_length())
    lines = ["// Controller only: external tape supplies read_bit; move_right=0 means left."]
    if combinational:
        state_port = f"input [{bits - 1}:0] state, " if n > 1 else ""
        lines += [f"module tm_comb({state_port}input read_bit,",
                  f"          output reg [{bits - 1}:0] next_state,",
                  "          output reg write_bit, output reg move_right, output reg halt);"]
        if n == 1:
            lines += ["  wire [0:0] state = 1'b0; // A is the only state: zero register bits."]
    else:
        lines += ["// clk advances one TM step; synchronous reset starts state A; halt freezes state.",
                  "module tm(input clk, input reset, input read_bit,",
                  "          output reg write_bit, output reg move_right, output reg halt);",
                  f"  reg [{bits - 1}:0] state;" if n > 1 else "  wire [0:0] state = 1'b0; // No state register needed.",
                  f"  reg [{bits - 1}:0] next_state;"]
    lines += ["  always @* begin", "    write_bit = read_bit; move_right = 1'b0; halt = 1'b1;",
              "    next_state = state;", "    case ({state, read_bit})"]
    for (q, s), (w, d, q2) in sorted(table.items()):
        lines.append(f"      {bits + 1}'d{2 * q + s}: begin write_bit = 1'b{w}; move_right = 1'b{int(d > 0)}; halt = 1'b0; next_state = {bits}'d{q2}; end")
    lines += ["      default: begin end", "    endcase", "  end"]
    if not combinational and n > 1:
        lines += ["  always @(posedge clk) begin", f"    if (reset) state <= {bits}'d0;",
                  "    else if (!halt) state <= next_state;", "  end"]
    lines += ["endmodule", ""]
    return "\n".join(lines)


@worker_budget
def synthesize(directory: Path, tm: str) -> dict:
    source = verilog(tm)
    (directory / "controller.v").write_text(source)
    (directory / "comb.v").write_text(verilog(tm, combinational=True))
    register_bits = (parse(tm)[1] - 1).bit_length()
    exe = shutil.which("yowasp-yosys") or shutil.which("yosys")
    if not exe:
        user_tool = Path.home() / ".local/bin/yowasp-yosys"
        exe = str(user_tool) if user_tool.exists() else None
    if not exe:
        command = [sys.executable, "-m", "pip", "install", "--user", "yowasp-yosys"]
        try:
            install = subprocess.run(command, capture_output=True, text=True, timeout=300)
            (directory / "yosys-install.log").write_text(install.stdout + install.stderr)
            user_tool = Path.home() / ".local/bin/yowasp-yosys"
            exe = str(user_tool) if install.returncode == 0 and user_tool.exists() else shutil.which("yowasp-yosys")
        except subprocess.TimeoutExpired:
            (directory / "yosys-install.log").write_text("installation exceeded 5 minutes\n")
        if not exe:
            return {"status": "unavailable: installation failed or exceeded 5 minutes; no gate count", "source": source}
    started = time.monotonic()
    attempts = []
    scripts = [
        "read_verilog comb.v; synth -top tm_comb -flatten; abc -g AND,OR,XOR,MUX; opt_clean; stat",
        "read_verilog comb.v; synth -top tm_comb -noabc; techmap; opt; stat",
    ]
    for index, script in enumerate(scripts):
        stat_path = directory / f"yosys-stat-{index}.json"
        stat_path.unlink(missing_ok=True)
        command = [exe, "-p", script + f"; tee -o {stat_path.name} stat -json"]
        try:
            remaining = 300 - (time.monotonic() - started)
            if remaining <= 0:
                break
            proc = subprocess.run(command, cwd=directory, capture_output=True, text=True,
                                  timeout=remaining, env={**os.environ, "RAYON_NUM_THREADS": "2"})
            output = proc.stdout + proc.stderr
            log_name = "yosys-comb.log" if index == 0 else "yosys-unmapped.log"
            (directory / log_name).write_text(output)
            attempts.append({"command": command, "exit": proc.returncode, "log": log_name})
            # Machine-readable final statistics include explicit zero-cell designs.
            if proc.returncode or not stat_path.exists():
                continue
            try:
                metrics = json.loads(stat_path.read_text())["modules"]["\\tm_comb"]
                cells = metrics["num_cells_by_type"]
                count = metrics["num_cells"]
            except (ValueError, KeyError):
                continue
            return {"status": "MEAS: ABC-mapped combinational controller cells; NOT physical area" if index == 0 else
                    "MEAS: unmapped Yosys combinational cells; NOT ABC gate count or physical area",
                    **({"gates": count} if index == 0 else {"unmapped_cells": count}),
                    "register_bits": register_bits, "register_note": "exact by Verilog construction; register excluded from combinational synthesis",
                    "cells": cells, "source": source, "attempts": attempts,
                    "seconds": time.monotonic() - started}
        except subprocess.TimeoutExpired:
            attempts.append({"command": command, "error": "5-minute total synthesis limit"})
            break
    return {"status": "synthesis unavailable: no final statistics within 5 minutes; no gate count",
            "source": source, "register_bits": register_bits, "attempts": attempts}


def verdicts(candidate: dict, data: dict, directory: Path, supplied=None) -> dict:
    out = {"forever": certificate(candidate["tm"], supplied),
           "minimality": minimality(candidate, data["target"])}
    hidden = data["hidden_tm"]
    if hidden:
        a, b = trace(candidate["tm"], 10 * len(data["target"])), trace(hidden, 10 * len(data["target"]))
        out["ten_h"] = {"rows": 10 * len(data["target"]), "agree": a["rows"] == b["rows"],
                        "rule": "independently cropped diagrams, same orientation, every pixel"}
    else:
        out["ten_h"] = {"status": "not applicable: hand-drawn target has no hidden machine"}
    out["circuit"] = synthesize(directory, candidate["tm"])
    return out


def append_journal(directory: Path, record: dict):
    with (directory / "journal.jsonl").open("a") as handle:
        handle.write(json.dumps(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def records(directory: Path) -> list[dict]:
    path = directory / "journal.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def prompt(data: dict, previous: list[dict]) -> str:
    feedback = [{"round": r["round"], "error": r.get("error"),
                 "accuracy": r.get("candidate", {}).get("accuracy"),
                 "states": r.get("candidate", {}).get("states"),
                 "defined_transitions": r.get("candidate", {}).get("transitions"),
                 "first_mismatching_rows": r.get("candidate", {}).get("mismatches"),
                 "minimality": r.get("verdicts", {}).get("minimality", {}).get("status")}
                for r in previous if r.get("mode") == "ripple"]
    return f"""Reverse-engineer this binary Turing-machine space-time weave. Find the SMALLEST
machine whose blank-tape execution matches the target; maximize accuracy if impossible.
Never assume the hidden machine is available: only the target is accessible.
Notation: rows separated by _, one row per state A,B,...; each row has two
3-character tokens for read=0 and read=1: write bit, L/R move, next state letter.
Example notation only: 1RB0LA_0LA1RB. --- is undefined and halts. Start state A,
head at cell 0, all-zero two-way infinite tape. 1 lights a pixel; 0 is dark.
{SCORING}
Sandbox: 90 seconds CPU, 1 GiB RAM, no network, read-only filesystem, Python
standard library only. You may import neverhalt.tm and neverhalt.tnf. At most
4 worker processes. Cached enumerate_tnf(n,2,300,Path('/tmp/neverhalt/cache'))
exists for n=2,3,4. Note: its holdouts omit first-state self loops and some
fully-defined machines, so do not rely on it as a complete search. First moves
in cached TNF are R: also test mirrored machines/targets. Consider inferring
writes from successive target rows and searching consistent transition tables;
state names can be introduced in order of first use. Any choice of search is YOURS.
API details: neverhalt.tm.parse(machine) returns (table, n_states, n_symbols),
where table[(state_int, read_int)] = (write_int, move_int, next_state_int);
states A,B,... are integers 0,1,... and move_int is +1 (R) or -1 (L).
neverhalt.tm.run(machine, max_steps) returns
(halted, steps, state_int, head_position, tape_dict_of_nonzero_cells).
enumerate_tnf returns a DICT; machines are in result['holdouts'] (list[str]).
neverhalt.tm.diagram includes head letters and row numbers, NOT binary pixels.
Use the provided pixel helpers instead of reimplementing simulation/scoring:
from neverhalt.weave_sandbox import render, score
render(machine, H) -> list[str] with the EXACT binary harness crop.
score(machine, target) -> (accuracy_float, declared_state_count), using the
EXACT alignment/width penalty above. These helpers contain no hidden targets.
The harness independently checks pixels, cycle proofs, and minimality. It does
not trust your score. Return notes and exactly ONE python fenced block defining
search(target: list[str]) -> str. Return the machine string, not a diagram.
Optionally return {{'tm': machine_string, 'certificate': {{'kind':'cycle','t':T,'p':P}}}}.
Do not call search at module import. Keep search inside the 90-second CPU budget.
Target dimensions: {len(data['target'])} rows x {len(data['target'][0])} columns.
TARGET:\n{chr(10).join(data['target'])}
Previous rounds:\n{json.dumps(feedback)}
"""


def preflight():
    data = prepare("easy")
    directory = RUNS / "weave-easy"
    code = directory / "stub.py"
    code.write_text("# Acceptance preflight only; never supplied to Ripple.\n"
                    "from pathlib import Path\n"
                    "from neverhalt.weave_sandbox import render, score\n"
                    "def search(target: list[str]) -> str:\n"
                    f"    for path in ({str(ROOT / 'neverhalt/weave.py')!r}, {str(RUNS)!r}):\n"
                    "        if Path(path).exists():\n"
                    "            raise RuntimeError('hidden parent module/run directory exposed: ' + path)\n"
                    f"    machine = {data['hidden_tm']!r}\n"
                    "    if render(machine, len(target)) != target or score(machine, target)[0] != 1.0:\n"
                    "        raise RuntimeError('pixel helper disagrees with preflight target')\n"
                    "    return machine\n")
    execution = execute(code, data["target"])
    if "error" in execution:
        raise RuntimeError(f"preflight sandbox failed: {execution['error']}")
    candidate = evaluate(execution["tm"], data["target"])
    checks = verdicts(candidate, data, directory)
    result = {"round": 0, "mode": "stub", "notes": "Acceptance preflight: trusted stub returns hidden easy machine; not a Ripple result.",
              "code_file": code.name, "candidate": candidate, "execution": execution, "verdicts": checks,
              "isolation": {"measured": True, "weave_module_hidden": True, "run_directories_hidden": True,
                            "method": "preflight search raises if either hidden path exists in its bubblewrap filesystem",
                            "command": "python3 -m neverhalt.weave preflight"}}
    append_journal(directory, result)
    render_all()
    if not candidate["exact"] or not checks["forever"]["proved"] or not checks["minimality"]["confirmed"] or not checks["circuit"].get("source"):
        raise RuntimeError("preflight did not complete every requested pipeline stage; inspect report")
    (directory / "preflight.json").write_text(json.dumps({"passed": True, "command": "python3 -m neverhalt.weave preflight",
                                                         "result": result}, indent=2) + "\n")
    print(f"PREFLIGHT exact=True forever=True minimality=True circuit_export=True gates={checks['circuit'].get('gates', 'unavailable')}", flush=True)


def extract_code(content: str) -> str:
    blocks = re.findall(r"```(?:python|py)[ \t]*\n(.*?)```", content, re.S | re.I)
    if len(blocks) != 1:
        raise ValueError(f"expected one complete Python block; got {len(blocks)}")
    tree = ast.parse(blocks[0])
    if not any(isinstance(node, ast.FunctionDef) and node.name == "search" for node in tree.body):
        raise ValueError("Python block must define the top-level search(target) function")
    return blocks[0] + "\n"


def run_target(name: str, rounds: int, stop_at: float | None = None):
    passed = RUNS / "weave-easy" / "preflight.json"
    if not passed.exists() or not json.loads(passed.read_text()).get("passed"):
        raise RuntimeError("run `python3 -m neverhalt.weave preflight` before calling Ripple")
    data = prepare(name)
    directory = RUNS / f"weave-{name}"
    previous = records(directory)
    ripple = [r for r in previous if r.get("mode") == "ripple"]
    best_record = None
    for record in ripple:
        if record.get("candidate") and better(record["candidate"], best_record["candidate"] if best_record else None):
            best_record = record
    if best_record and best_record["candidate"]["exact"] and best_record.get("verdicts", {}).get("minimality", {}).get("confirmed"):
        print(f"{name}: already exact and minimum", flush=True)
        return
    cfg = dataclasses.replace(load_config(ROOT), reasoning="off", model=RIPPLE_MODEL, max_tokens=24000)
    for number in range(max((r["round"] for r in ripple), default=0) + 1, rounds + 1):
        if stop_at is not None and time.time() >= stop_at:
            print(f"{name}: new-round deadline reached", flush=True)
            break
        record = {"round": number, "mode": "ripple", "started": time.time(), "model": cfg.model,
                  "reasoning": "off", "max_tokens": cfg.max_tokens, "attempts": [], "notes": ""}
        request = prompt(data, previous)
        (directory / f"round-{number:02d}.prompt.txt").write_text(request)
        append_journal(directory, {**record, "mode": "round_started"})
        messages = [{"role": "system", "content": "You are Ripple. Write a concise executable search program. Use the documented render and score helpers rather than reimplementing them. Keep notes brief and put the complete program in exactly one Python block."},
                    {"role": "user", "content": request}]
        def on_retry(delay, error):
            append_journal(directory, {"mode": "retry", "round": number, "delay": delay,
                                       "error": str(error), "time": time.time()})
            print(f"{name} round {number}: retry in {delay:.1f}s: {error}", flush=True)
        for fix in range(4):
            if stop_at is not None and time.time() >= stop_at:
                record["error"] = "request deadline reached before next same-round fix"
                break
            stem = f"round-{number:02d}" + (f"-fix-{fix}" if fix else "")
            stream_path = directory / f"{stem}.stream.txt"
            chunks = []
            def on_content(text):
                chunks.append(text)
                with stream_path.open("a") as handle:
                    handle.write(text)
            attempt = {"fix": fix, "started": time.time()}
            content = ""
            print(f"{name} round {number} fix {fix}: requesting Ripple", flush=True)
            try:
                patience = min(1200.0, max(1.0, stop_at - time.time())) if stop_at is not None else 1200.0
                response = chat(cfg, messages, on_content, lambda _: None, on_retry, patience=patience)
                attempt["llm"] = response
                content = response["content"]
                (directory / f"{stem}.response.txt").write_text(content)
                record["notes"] += "\n" + re.sub(r"```.*?```", "", content, flags=re.S).strip()
                source = extract_code(content)
                code = directory / f"{stem}.py"
                code.write_text(source)
                attempt["code_file"] = code.name
                record["code_file"] = code.name
                execution = execute(code, data["target"])
                attempt["execution"] = execution
                if "error" in execution:
                    raise RuntimeError(execution.get("traceback", execution["error"])[-1200:])
                candidate = evaluate(execution["tm"], data["target"])
                record["execution"] = execution
                record["candidate"] = candidate
                if better(candidate, best_record["candidate"] if best_record else None):
                    record["verdicts"] = verdicts(candidate, data, directory, execution.get("certificate"))
                    best_record = record
                print(f"{name} round {number}: accuracy={candidate['accuracy']:.8f} states={candidate['states']} exact={candidate['exact']}", flush=True)
                attempt["finished"] = time.time()
                record["attempts"].append(attempt)
                break
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                attempt.update(error=error, finished=time.time())
                record["attempts"].append(attempt)
                append_journal(directory, {"mode": "fix_attempt", "round": number, **attempt})
                print(f"{name} round {number} fix {fix}: {error[-400:]}", flush=True)
                if fix == 3:
                    record["error"] = error
                else:
                    messages += [{"role": "assistant", "content": content or "(no complete visible reply)"},
                                 {"role": "user", "content": f"The program failed: {error[-400:]}\nSend the COMPLETE corrected module now: exactly one ```python block defining search(target), no other text. Use from neverhalt.weave_sandbox import render, score; both are already implemented. No placeholders."}]
        record["finished"] = time.time()
        append_journal(directory, record)
        previous.append(record)
        render_all()
        if best_record and best_record["candidate"]["exact"] and best_record.get("verdicts", {}).get("minimality", {}).get("confirmed"):
            break


STYLE = """<style>:root{color-scheme:dark}body{margin:0;background:#0a0d0e;color:#edf0e8;font:15px Arial,sans-serif}main{max-width:1280px;margin:auto;padding:28px}h1{font-size:32px;letter-spacing:-.04em}h1 span,a{color:#ddf7a4}h2{font-size:18px}section,details{background:#0d1214;border:1px solid #263030;padding:18px;margin:18px 0}pre{font:12px/1.35 ui-monospace,monospace;overflow:auto;white-space:pre}p{line-height:1.5}.muted{color:#7f8d8c}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}.pair svg{width:100%;max-height:720px;image-rendering:pixelated}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #263030}.good{color:#8cf0bc}.bad{color:#f4bd84}summary{cursor:pointer}.chart{width:100%;height:200px}code{color:#ddf7a4}@media(max-width:700px){.pair{grid-template-columns:1fr}main{padding:12px}}</style>"""


def svg_diagram(rows: list[str]) -> str:
    h, w = len(rows), len(rows[0])
    path = " ".join(f"M{x},{y}h1v1h-1z" for y, row in enumerate(rows) for x, c in enumerate(row) if c == "#")
    return f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="binary space-time diagram" viewBox="0 0 {w} {h}"><rect width="{w}" height="{h}" fill="#17211d"/><path d="{path}" fill="#ddf7a4"/></svg>'


def chart(rounds: list[dict]) -> str:
    points, states = [], []
    state_scale = max(5, max((r.get("candidate", {}).get("states", 0) for r in rounds), default=0))
    for i, r in enumerate(rounds):
        c = r.get("candidate")
        if c:
            x = 35 + i * 530 / max(1, len(rounds) - 1)
            points.append(f"{x},{165 - 140 * c['accuracy']}")
            states.append(f"{x},{165 - 140 * c['states'] / state_scale}")
    parts = [f'<svg class="chart" viewBox="0 0 600 210" role="img" aria-label="round accuracy and state count chart"><path d="M35 20V165H575" fill="none" stroke="#7f8d8c"/><text x="35" y="205" fill="#8cf0bc">green: accuracy 0–100%</text><text x="300" y="205" fill="#81baff">blue: states 0–{state_scale}</text>']
    for series, color in ((points, "#8cf0bc"), (states, "#81baff")):
        parts.append(f'<polyline points="{" ".join(series)}" fill="none" stroke="{color}" stroke-width="3"/>')
        for point in series:
            x, y = point.split(",")
            parts.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>')
    for i, record in enumerate(rounds):
        x = 35 + i * 530 / max(1, len(rounds) - 1)
        parts.append(f'<text x="{x}" y="182" fill="#7f8d8c" text-anchor="middle">R{record["round"]}</text>')
    return "".join(parts) + "</svg>"


def render_report(name: str) -> str:
    data = prepare(name)
    directory = RUNS / f"weave-{name}"
    journal = records(directory)
    rounds = [r for r in journal if r.get("mode") == "ripple"]
    candidates = [r for r in rounds if r.get("candidate")]
    stub = [r for r in journal if r.get("mode") == "stub"]
    best = None
    for r in candidates:
        if better(r["candidate"], best["candidate"] if best else None):
            best = r
    display = best or (stub[-1] if stub else None)
    if display:
        for update in journal:
            if update.get("mode") == "circuit" and update.get("round") == display["round"] and update.get("tm") == display["candidate"]["tm"]:
                display.setdefault("verdicts", {})["circuit"] = update["circuit"]
    e = html.escape
    if best:
        c = best["candidate"]
        headline = f"{c['states']} states vs hidden {data['hidden_states'] if data['hidden_states'] else 'none'} · {'EXACT' if c['exact'] else f'{100*c["accuracy"]:.4f}% accuracy'}"
        v = best.get("verdicts", {})
        circuit = v.get("circuit", {})
        measurement = f'{circuit["gates"]} mapped gates' if "gates" in circuit else (
            f'{circuit["unmapped_cells"]} unmapped cells' if "unmapped_cells" in circuit else "gate count unavailable")
        headline += f" · forever {'proved' if v.get('forever', {}).get('proved') else 'unknown'} · {v.get('minimality', {}).get('status', 'minimality not run')} · {measurement}"
    else:
        headline = "No Ripple candidate yet" + (" · stub preflight only" if display else "")
    body = [f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>WEAVE — {e(name)}</title>{STYLE}<main>',
            '<p><a href="../weave-index.html">← All weaves</a></p>', f'<h1>NEVERHALT <span>/ WEAVE / {e(name)}</span></h1>',
            f'<p>{e(headline)}</p><p class="muted">Ripple alone writes live search programs. Trusted Python harness scores and checks; stub preflight is labeled, not a model result. No external resources.</p>',
            '<section><h2>Target vs best candidate</h2><div class="pair">',
            f'<div><p>Target · {len(data["target"])} × {len(data["target"][0])}</p>{svg_diagram(data["target"])}</div>']
    if display:
        c = display["candidate"]
        body.append(f'<div><p>{"Ripple" if best else "STUB PREFLIGHT ONLY"} · {c["states"]} states · {c["transitions"]} defined transitions</p>{svg_diagram(c["rows"])}</div>')
    else:
        body.append('<div>No candidate returned.</div>')
    body.append('</div></section><section><h2>Scoring contract</h2><pre>' + e(SCORING) + '</pre></section>')
    isolation = next((r.get("isolation", {"status": "not checked in this older preflight"})
                      for r in reversed(records(RUNS / "weave-easy")) if r.get("mode") == "stub"),
                     {"status": "preflight not run"})
    body += ['<section><h2>Hidden-target isolation</h2>',
             '<p>Bubblewrap hides /tmp, /home, /root and /run; host mounts are read-only and networking is unshared. Only the selected search file, tm.py, tnf.py, weave_sandbox.py and the enumeration cache are reintroduced. The parent weave.py and all run directories holding hidden targets are absent in the child. The preflight stub explicitly checks both paths; its known hidden machine is never supplied to a live search.</p>',
             f'<pre>{e(json.dumps(isolation, indent=2))}</pre></section>']
    if display:
        c, v = display["candidate"], display.get("verdicts", {})
        body += [f'<section><h2>Verdicts {"— stub, NOT Ripple" if not best else ""}</h2>',
                 f'<p>Exact: <strong>{c["exact"]}</strong> · accuracy {c["correct"]}/{c["total"]} = {100*c["accuracy"]:.6f}% · alignment {c["offset"]}</p>',
                 f'<p>Machine: <code>{e(c["tm"])}</code></p>']
        for title, key in (("Forever / kernel certificate", "forever"), ("Minimality", "minimality"), ("Generated-target agreement at 10H", "ten_h")):
            body.append(f'<h3>{title}</h3><pre>{e(json.dumps(v.get(key, {"status": "not run"}), indent=2))}</pre>')
        circuit = v.get("circuit", {})
        body += ['</section><section><h2>Controller circuit</h2>',
                 '<p>Controller only; excludes tape memory and head-position storage. Results distinguish ABC-mapped gates from explicitly labeled unmapped Yosys cells; neither is silicon area. Binary state-register bits are exact by construction and excluded from combinational synthesis.</p>',
                 f'<pre>{e(json.dumps({k: x for k, x in circuit.items() if k != "source"}, indent=2))}</pre>',
                 f'<pre>{e(circuit.get("source", "No circuit available"))}</pre></section>']
    body += ['<section><h2>Ripple rounds</h2>', chart(rounds), '<table><tr><th>Round</th><th>Accuracy</th><th>States</th><th>Outcome</th></tr>']
    for r in rounds:
        c = r.get("candidate", {})
        accuracy = f'{100*c["accuracy"]:.4f}%' if c else '—'
        body.append(f'<tr><td>{r["round"]}</td><td>{accuracy}</td><td>{c.get("states", "—")}</td><td>{e(r.get("error", "exact" if c.get("exact") else "approximate"))}</td></tr>')
    body.append('</table></section>')
    for r in rounds:
        source = (directory / r["code_file"]).read_text() if r.get("code_file") else "No executable Python block returned."
        body.append(f'<details open><summary>Ripple round {r["round"]}: notes, code, evidence</summary><pre>{e(r.get("notes", ""))}</pre><pre>{e(source)}</pre><pre>{e(json.dumps({k:x for k,x in r.items() if k not in ("notes", "llm")}, indent=2))}</pre></details>')
    body += ['<details><summary>Hidden target provenance (never included in Ripple prompts or sandbox)</summary>',
             f'<pre>{e(json.dumps({k:x for k,x in data.items() if k != "target"}, indent=2))}</pre></details>',
             '<details><summary>Audit journal and preflight</summary>', f'<pre>{e(json.dumps(stub + [r for r in journal if r.get("mode") == "retry"], indent=2))}</pre></details>',
             '</main></html>']
    (directory / "report.html").write_text("\n".join(body))
    return headline


def render_all():
    RUNS.mkdir(parents=True, exist_ok=True)
    headlines = [(name, render_report(name)) for name in NAMES]
    body = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>NEVERHALT — reverse-engineer the weave</title>', STYLE,
            '<main><h1>NEVERHALT <span>/ reverse-engineer the weave</span></h1><p>Ripple searches. The trusted harness checks pixels, proves forever, tests minimality, and synthesizes controller circuits.</p>']
    for name, headline in headlines:
        body.append(f'<section><h2><a href="weave-{name}/report.html">{name}</a></h2><p>{html.escape(headline)}</p></section>')
    body.append('</main></html>')
    (RUNS / "weave-index.html").write_text("\n".join(body))


def refresh_circuits():
    for name in NAMES:
        directory = RUNS / f"weave-{name}"
        best = None
        for record in records(directory):
            if record.get("mode") == "ripple" and record.get("candidate") and better(
                    record["candidate"], best["candidate"] if best else None):
                best = record
        if best:
            measurement = synthesize(directory, best["candidate"]["tm"])
            append_journal(directory, {"mode": "circuit", "round": best["round"],
                                      "tm": best["candidate"]["tm"], "circuit": measurement})
            print(f"{name}: {measurement['status']} · {measurement.get('gates', measurement.get('unmapped_cells', 'unavailable'))}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("target", choices=(*NAMES, "all"))
    run_parser.add_argument("--rounds", type=int, default=6, choices=range(1, 21))
    run_parser.add_argument("--stop-at", help="ISO timestamp after which no new model request starts")
    report_parser = sub.add_parser("report")
    report_parser.add_argument("--synthesize", action="store_true", help="refresh winner circuit measurements without another model call")
    sub.add_parser("preflight")
    args = parser.parse_args()
    if args.command == "preflight":
        preflight()
    elif args.command == "report":
        if args.synthesize:
            refresh_circuits()
        render_all()
        print(RUNS / "weave-index.html")
    else:
        for name in NAMES if args.target == "all" else (args.target,):
            run_target(name, args.rounds, datetime.fromisoformat(args.stop_at).timestamp() if args.stop_at else None)


if __name__ == "__main__":
    main()
