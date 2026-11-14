#!/usr/bin/env python3
"""Development-only synthetic NEVERHALT run; no proofs are actually checked.

Run from the project root: python3 web/mock_api.py --port 8766 --machines 1500
The 40-second loop deliberately resets both API cursors to exercise reconnects.
"""

import argparse
import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


INDEX = Path(__file__).with_name("index.html")
RUN_SECONDS = 40.0
CHAMPION = {"tm": "1RB---_1LB0RC_1LC1LA", "steps": 21}
ROUND_NOTES = [
    {
        "name": "exact_cycle_v1",
        "kind": "cycle",
        "label": "cycles",
        "reasoning": (
            "Begin with the smallest invariant: an identical complete configuration. "
            "The state, absolute head position, and nonzero tape support must all agree. "
            "A matching hash is only a candidate; the kernel will replay and compare."
        ),
        "model": (
            "**Round 1 — Find the loops.**\n\n"
            "Most of this field is not mysterious. A machine returns to exactly the same "
            "configuration, and determinism does the rest. I'll record the first repeat "
            "and send only its prefix and period to the kernel.\n\n"
            "```python\n"
            "def decide(tm, limit=256):\n"
            "    config = blank_configuration(tm)\n"
            "    seen = {}\n"
            "    for t in range(limit):\n"
            "        key = freeze(config)\n"
            "        if key in seen:\n"
            "            return {\n"
            "                'kind': 'cycle',\n"
            "                't': seen[key],\n"
            "                'p': t - seen[key],\n"
            "            }\n"
            "        seen[key] = t\n"
            "        config = step(tm, config)\n"
            "    return None\n"
            "```\n\n"
            "A finite witness to an infinite future. The kernel, not my confidence, decides."
        ),
    },
    {
        "name": "translated_cycle_v1",
        "kind": "tcycle",
        "label": "translated",
        "reasoning": (
            "The remaining diagonal traces suggest drift rather than absolute repetition. "
            "Normalize the complete finite tape support relative to the head. "
            "A translated repeat is valid only when the kernel checks the full configuration."
        ),
        "model": (
            "**Round 2 — A loop can travel.**\n\n"
            "Some machines never come home. They repeat the same configuration one cell "
            "farther along the tape. Translation symmetry lets us prove those too, "
            "without guessing from the picture.\n\n"
            "```python\n"
            "def translated_key(config):\n"
            "    state, head, support = config\n"
            "    relative = tuple(sorted(\n"
            "        cell - head for cell in support\n"
            "    ))\n"
            "    return state, relative\n"
            "\n"
            "def witness(first, second):\n"
            "    return {\n"
            "        'kind': 'tcycle',\n"
            "        't': first.time,\n"
            "        'p': second.time - first.time,\n"
            "        'shift': second.head - first.head,\n"
            "    }\n"
            "```\n\n"
            "The blue wave is a different kind of infinity: repetition in motion."
        ),
    },
    {
        "name": "closed_contexts_v2",
        "kind": "cps",
        "label": "closed sets",
        "reasoning": (
            "Exact and translated cycles leave machines with growing tape support. "
            "Use a finite abstraction of local contexts. We need an inductive set containing "
            "the blank start, closed under every abstract successor, and excluding halting."
        ),
        "model": (
            "**Round 3 — Stop following. Start enclosing.**\n\n"
            "The tape can keep growing even when no configuration repeats. I'll propose "
            "a finite collection of local contexts that contains every possible future. "
            "The certificate must close under **every** successor, not just a sampled trace.\n\n"
            "```python\n"
            "def close_contexts(seed, successors):\n"
            "    closed = {seed}\n"
            "    frontier = [seed]\n"
            "    while frontier:\n"
            "        context = frontier.pop()\n"
            "        for nxt in successors(context):\n"
            "            if nxt.is_halting:\n"
            "                return None\n"
            "            if nxt not in closed:\n"
            "                closed.add(nxt)\n"
            "                frontier.append(nxt)\n"
            "    return closed\n"
            "```\n\n"
            "The violet tiles have an invariant, not merely a long execution."
        ),
    },
    {
        "name": "context_refinement_v3",
        "kind": "cps",
        "label": "refined",
        "reasoning": (
            "The final holdouts are where the coarse abstraction loses information. "
            "Increase the left and right automaton state counts, preserving the same trusted "
            "closure check. A more expressive candidate is not a weaker proof obligation."
        ),
        "model": (
            "**Round 4 — The last finite frontier.**\n\n"
            "A handful of machines need more context. I'll enlarge the automata, then submit "
            "the resulting finite sets to exactly the same checker. No special cases. "
            "No exceptions for the stubborn ones.\n\n"
            "```python\n"
            "def refine(tm):\n"
            "    for nl, nr in [(2, 3), (3, 2), (3, 3)]:\n"
            "        abstraction = contexts(tm, nl, nr)\n"
            "        closed = close_contexts(\n"
            "            abstraction.blank_start,\n"
            "            abstraction.successors,\n"
            "        )\n"
            "        if closed is not None:\n"
            "            return {\n"
            "                'kind': 'cps',\n"
            "                'nl': nl, 'nr': nr,\n"
            "                'contexts': closed,\n"
            "            }\n"
            "    return None\n"
            "```\n\n"
            "When the last grey tile lights up, there is nowhere left for a larger halting time to hide."
        ),
    },
]


class Demo:
    def __init__(self, machine_count):
        self.machine_count = machine_count
        self.started = time.monotonic()
        self.cycle = -1
        self.lock = threading.Lock()
        self.advance()

    def restart(self, cycle):
        self.cycle = cycle
        self.random = random.Random(65100 + cycle)
        self.version = 1
        self.events = []
        self.machines = {}
        self.timeline = []
        self.action_index = 0
        self.elapsed = 0.0
        self.state = {
            "version": self.version,
            "problem": None,
            "phase": "idle",
            "round": 0,
            "model": "ricursiveai/ripple-65b-preview",
            "counts": {},
            "by_kind": {"cycle": 0, "tcycle": 0, "cps": 0},
            "champion": None,
            "history": [],
            "theorem": None,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0,
                      "cost_usd": 0.0, "seconds": 0.0, "calls": 0},
            "log_next": 0,
        }
        generated = []
        for machine_id in range(1, self.machine_count + 1):
            states = self.random.choice((3, 3, 3, 4))
            rows = []
            write_probability = self.random.uniform(0.45, 0.9)
            right_probability = self.random.uniform(0.15, 0.85)
            for _ in range(states):
                row = ""
                for _ in range(2):
                    write = "1" if self.random.random() < write_probability else "0"
                    move = "R" if self.random.random() < right_probability else "L"
                    next_state = chr(65 + self.random.randrange(states))
                    row += write + move + next_state
                rows.append(row)
            generated.append({"id": machine_id, "tm": "_".join(rows),
                              "status": "holdout", "round": None,
                              "decider": None, "cert": None})

        self.schedule(0.10, "log", {
            "kind": "system", "text": "NEVERHALT initialized · trusted kernel online.", "stream": None,
        })
        self.schedule(0.35, "log", {
            "kind": "system",
            "text": "Synthetic development run · diagrams are real simulations; verdicts and certificates are illustrative.",
            "stream": None,
        })
        self.schedule(0.75, "phase", "enumerating")
        for batch in range(12):
            start = self.machine_count * batch // 12
            end = self.machine_count * (batch + 1) // 12
            self.schedule(0.9 + batch * 0.2, "enumerate", generated[start:end])
        self.schedule(3.3, "simulation_done", None)

        ids = list(range(1, self.machine_count + 1))
        self.random.shuffle(ids)
        boundaries = [0, round(self.machine_count * 0.38),
                      round(self.machine_count * 0.67),
                      round(self.machine_count * 0.89), self.machine_count]
        for index, notes in enumerate(ROUND_NOTES):
            round_number = index + 1
            begin = (4.5, 12.0, 20.0, 28.0)[index]
            round_ids = ids[boundaries[index]:boundaries[index + 1]]
            self.schedule(begin, "round", round_number)
            self.stream(begin + 0.1, notes["reasoning"], "reasoning", f"r{round_number}-thinking", 48, 0.13)
            self.stream(begin + 0.95, notes["model"], "model", f"r{round_number}-notebook", 49, 0.14)
            for batch in range(8):
                start = len(round_ids) * batch // 8
                end = len(round_ids) * (batch + 1) // 8
                proofs = []
                for machine_id in round_ids[start:end]:
                    kind = notes["kind"]
                    if index == 3:
                        kind = self.random.choices(("cycle", "tcycle", "cps"), weights=(1, 1, 8))[0]
                    if kind in ("cycle", "tcycle"):
                        cert = {"kind": kind, "t": self.random.randrange(3, 100), "p": self.random.choice((2, 4, 6, 8, 12, 16))}
                        if kind == "tcycle":
                            cert["shift"] = self.random.choice((-2, -1, 1, 2))
                    else:
                        cert = {"kind": "cps", "nl": 2 if index == 2 else 3,
                                "nr": self.random.choice((2, 3)), "contexts": self.random.randrange(17, 184)}
                    proofs.append({"id": machine_id, "status": kind, "round": round_number,
                                   "decider": notes["name"], "cert": cert})
                self.schedule(begin + 3.25 + batch * 0.31, "proofs", proofs)
            self.schedule(begin + 6.0, "round_done", {
                "round": round_number, "holdouts": self.machine_count - boundaries[index + 1],
                "label": notes["label"], "accepted": len(round_ids),
            })
        self.schedule(35.0, "theorem", None)
        self.timeline.sort(key=lambda action: action[0])

    def schedule(self, at, operation, payload):
        self.timeline.append((at, operation, payload))

    def stream(self, at, content, kind, stream_id, chunk_size, spacing):
        for index, offset in enumerate(range(0, len(content), chunk_size)):
            self.schedule(at + index * spacing, "log", {
                "kind": kind, "text": content[offset:offset + chunk_size], "stream": stream_id,
            })

    def log(self, kind, text, stream=None):
        self.events.append({"i": len(self.events), "kind": kind, "text": text, "stream": stream})
        self.state["log_next"] = len(self.events)

    def apply(self, operation, payload):
        self.version += 1
        self.state["version"] = self.version
        if operation == "log":
            self.log(payload["kind"], payload["text"], payload["stream"])
            if payload["kind"] in ("model", "reasoning"):
                self.state["usage"]["completion_tokens"] += max(1, len(payload["text"]) // 4)
        elif operation == "phase":
            self.state["phase"] = payload
            self.state["problem"] = {"name": "BB(3)", "states": 3, "symbols": 2}
            self.log("system", "Enumerating the search space · simulating the blank-tape frontier.")
        elif operation == "enumerate":
            for machine in payload:
                self.machines[machine["id"]] = {**machine, "_version": self.version}
            count = len(self.machines)
            total_enumerated = max(4052, self.machine_count + 2800)
            enumerated = round(total_enumerated * count / self.machine_count)
            self.state["counts"] = {"enumerated": enumerated, "halting": enumerated - count,
                                    "holdouts_initial": self.machine_count, "holdouts": count, "proved": 0}
        elif operation == "simulation_done":
            self.state["phase"] = "hunting"
            self.state["champion"] = dict(CHAMPION)
            self.state["history"].append({"round": 0, "holdouts": self.machine_count, "label": "simulation"})
            self.log("system", f"Simulation complete · {self.machine_count:,} holdouts remain. Halting champion: 21 steps.")
        elif operation == "round":
            self.state["round"] = payload
            self.state["usage"]["calls"] = payload
            self.state["usage"]["prompt_tokens"] += 2400 + payload * 850
            self.log("system", f"Round {payload:02d} · asking Ripple for the next decider.")
        elif operation == "proofs":
            for proof in payload:
                machine = self.machines[proof["id"]]
                machine.update(proof)
                machine["_version"] = self.version
                self.state["by_kind"][proof["status"]] += 1
                self.state["counts"]["proved"] += 1
                self.state["counts"]["holdouts"] -= 1
        elif operation == "round_done":
            self.state["history"].append({key: payload[key] for key in ("round", "holdouts", "label")})
            self.log("kernel", f"accepted {payload['accepted']:,} · rejected 0\n{payload['holdouts']:,} holdouts remain. Every accepted witness independently checked.")
        elif operation == "theorem":
            self.state["phase"] = "proved"
            self.state["theorem"] = "BB(3) = 21"
            self.log("kernel", "ALL HOLDOUTS DISCHARGED\nBB(3) = 21 ∎")
            self.log("model", "Every machine in the frontier now has a certificate. The champion halts after 21 steps. The others run forever.\n\n**A finite proof of never.**")

    def advance(self):
        elapsed = time.monotonic() - self.started
        cycle = int(elapsed // RUN_SECONDS)
        if cycle != self.cycle:
            self.restart(cycle)
        self.elapsed = elapsed % RUN_SECONDS
        while self.action_index < len(self.timeline) and self.timeline[self.action_index][0] <= self.elapsed:
            _, operation, payload = self.timeline[self.action_index]
            self.apply(operation, payload)
            self.action_index += 1
        usage = self.state["usage"]
        usage["seconds"] = round(max(0.0, min(self.elapsed, 35.0) - 3.3), 1)
        usage["cost_usd"] = round((usage["prompt_tokens"] * 0.7 + usage["completion_tokens"] * 1.8) / 1_000_000, 5)

    def response(self, path, since):
        with self.lock:
            self.advance()
            if path == "/api/state":
                payload = self.state
            elif path == "/api/machines":
                payload = {"version": self.version,
                           "machines": [{key: value for key, value in machine.items() if key != "_version"}
                                        for machine in self.machines.values() if machine["_version"] > since]}
            elif path == "/api/log":
                payload = {"next": len(self.events), "events": self.events[since:]}
            else:
                return None
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description="Serve the NEVERHALT UI with a looping synthetic API.")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--machines", type=int, default=1200)
    args = parser.parse_args()
    if args.machines < 1:
        parser.error("--machines must be positive")
    demo = Demo(args.machines)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == "/":
                self.respond(INDEX.read_bytes(), "text/html; charset=utf-8")
                return
            if url.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if url.path not in ("/api/state", "/api/machines", "/api/log"):
                self.send_error(404)
                return
            query = parse_qs(url.query)
            try:
                since = max(0, int(query.get("since", ["0"])[0]))
            except ValueError:
                since = 0
            self.respond(demo.response(url.path, since), "application/json; charset=utf-8")

        def respond(self, body, content_type):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"NEVERHALT mock → http://127.0.0.1:{args.port}/", flush=True)
    print(f"{args.machines:,} synthetic machines · {RUN_SECONDS:.0f}s loop · Ctrl-C to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
