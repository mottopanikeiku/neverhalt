"""Runs INSIDE the sandbox and executes untrusted, model-written decider code.

argv: decider path, seconds allowed per machine.  stdin: one machine per line.
real stdout: one JSON line per machine, {"i": index, "cert": ...} or {"i": index, "err": "..."}.
Nothing printed here is trusted: the parent re-checks every certificate with the kernel.
"""
import importlib.util
import json
import os
import resource
import signal
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Timeout(BaseException):
    pass


def _alarm(*_):
    raise Timeout()


def main():
    path, limit = sys.argv[1], float(sys.argv[2])
    gib = 1 << 30
    resource.setrlimit(resource.RLIMIT_AS, (2 * gib, 2 * gib))
    out, sys.stdout = sys.stdout, sys.stderr  # prints from the decider must not touch the protocol
    try:
        spec = importlib.util.spec_from_file_location("decider", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        decide = module.decide
    except BaseException:
        out.write(json.dumps({"fatal": traceback.format_exc(limit=3)[-1200:]}) + "\n")
        return
    signal.signal(signal.SIGALRM, _alarm)
    for i, line in enumerate(sys.stdin):
        signal.setitimer(signal.ITIMER_REAL, limit)
        try:
            text = json.dumps({"i": i, "cert": decide(line.strip())})
            signal.setitimer(signal.ITIMER_REAL, 0)
        except Timeout:
            text = json.dumps({"i": i, "err": "timeout"})
        except BaseException as e:
            signal.setitimer(signal.ITIMER_REAL, 0)
            text = json.dumps({"i": i, "err": f"{type(e).__name__}: {e}"[:300]})
        out.write(text + "\n")
    out.flush()


if __name__ == "__main__":
    main()
