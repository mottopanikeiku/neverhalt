NAME = "n-gram closed sets"

from neverhalt.helpers import closure
from neverhalt.tm import parse


def decide(tm):
    """Automata that remember the last n cells of each half-tape, for growing n."""
    table, _, k = parse(tm)
    shift = lambda gram, x: gram[1:] + (x,)
    for n in (1, 2, 3, 4, 5, 6):
        cert = closure(table, k, shift, shift, (0,) * n, (0,) * n)
        if cert:
            return cert
    return None
