import sys
sys.setrecursionlimit(100000)
from neverhalt.tm import parse, run
from neverhalt.kernel import check, Reject

def table_of(tm):
    table, ns, nsl = parse(tm)
    return table, ns, nsl

def halting_states(table, ns):
    return ns

def main():
    pass

def decide(tm):
    return None

main()