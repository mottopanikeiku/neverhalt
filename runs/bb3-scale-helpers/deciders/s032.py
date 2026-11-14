from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject
from neverhalt.helpers import closure

import itertools

def _all_automata(n, cap=200000):
    # state 0 loops on symbol 0 (blank half-tape); transitions on symbol 1 optional,
    # any state may also loop on symbol 0.
    for size in range(1, n + 1):
        total = 1 + size
        # each state i>=1 chooses for each symbol whether it is null or maps somewhere
        for choice in itertools.product(range(3), repeat=(total * 2)):
            tab = [{} for _ in range(total)]
            ok = True
            for st in range(total):
                tab[st][0] = 0 if st == 0 else None
                tab[st][1] = None
            if st == 0:
                tab[0][1] = choice[0]
            # rebuild properly below
            break
        # simpler: enumerate mappings per state/symbol from {None,0..total-1}
        for choice in itertools.product(range(total + 1), repeat=(total * 2)):
            tab = [{} for _ in range(total)]
            for st in range(total):
                for sym in (0, 1):
                    idx = st * 2 + sym
                    v = choice[idx]
                    tab[st][sym] = None if v == total else v
            if tab[0][0] != 0:
                continue
            if tab[0][1] is not None and tab[0][1] != 0:
                # allow it, but blank tape state must stay blank when reading blank
                pass
            yield tab

def _push_from_table(tab):
    def push(state, symbol):
        v = tab[state].get(symbol)
        return v
    return push

def _make_tables_push(tab):
    # closure expects push functions; build blank = 0
    def push_blank(state, symbol):
        return tab[state].get(symbol)
    return push_blank

def decide(tm):
    table, ns, nsym = parse(tm)
    # Try small automata per side, growing from 1 to 3 "informative" states.
    for size in (1, 2, 3):
        tabs = list(_all_automata(size))
        # dedupe by tuple form
        seen = set()
        uniq = []
        for t in tabs:
            key = tuple(tuple(sorted(s.items())) for s in t)
            if key not in seen:
                seen.add(key)
                uniq.append(t)
        for lt in uniq:
            for rt in uniq:
                try:
                    cert = closure(
                        push_left=lambda st, sym: lt[st].get(sym),
                        push_right=lambda st, sym: rt[st].get(sym),
                        blank_left=0,
                        blank_right=0,
                    )
                except Exception:
                    cert = None
                if cert is None:
                    continue
                try:
                    check(tm, cert)
                except Reject:
                    continue
                return cert
    return None
