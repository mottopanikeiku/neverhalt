import importlib
import sys
import time
from pathlib import Path

from neverhalt import kernel, tm
from neverhalt.tnf import enumerate_tnf

if __name__ == "__main__":
    assert tm.run("1RB1LB_1LA---", 100)[:2] == (True, 6)
    assert tm.run("1RB---_1LB0RC_1LC1LA", 100)[:2] == (True, 21)
    assert tm.run("1RB1LB_1LA0LC_---1LD_1RD0RA", 1000)[:2] == (True, 107)
    refs = [importlib.import_module(f"neverhalt.reference.{m}") for m in ("r1_cyclers", "r2_translated", "r3_cps")]
    targets = [tuple(int(x) for x in a.split("x")) for a in sys.argv[1:]] or [(2, 2), (3, 2), (4, 2)]
    for n, k in targets:
        t0 = time.time()
        e = enumerate_tnf(n, k, 300, Path("cache"))
        print(f"\nBB({n},{k}): enumerated={e['enumerated']} halting={e['halting']} holdouts={len(e['holdouts'])} "
              f"champion={e['champion']}  [{time.time() - t0:.1f}s]", flush=True)
        left = e["holdouts"]
        for ref in refs:
            t0, still, kinds = time.time(), [], {}
            for m in left:
                c = ref.decide(m)
                if c is None:
                    still.append(m)
                    continue
                kind = kernel.check(m, c)
                kinds[kind] = kinds.get(kind, 0) + 1
            print(f"  {ref.NAME:32s} proved={kinds} remaining={len(still)} [{time.time() - t0:.1f}s]", flush=True)
            left = still
        print(f"  UNPROVEN ({len(left)}):", left[:12], flush=True)
