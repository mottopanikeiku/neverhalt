# Acceptance preflight only; never supplied to Ripple.
from pathlib import Path
from neverhalt.weave_sandbox import render, score
def search(target: list[str]) -> str:
    for path in ('/tmp/neverhalt/neverhalt/weave.py', '/tmp/neverhalt/runs'):
        if Path(path).exists():
            raise RuntimeError('hidden parent module/run directory exposed: ' + path)
    machine = '1LB0LB_1RA1LA'
    if render(machine, len(target)) != target or score(machine, target)[0] != 1.0:
        raise RuntimeError('pixel helper disagrees with preflight target')
    return machine
