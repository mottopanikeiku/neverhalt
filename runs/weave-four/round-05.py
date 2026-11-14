import sys, time
from pathlib import Path

def search(target):
    if len(target) > 80:
        target = target[:80]
    H = len(target)
    W = max(len(r) for r in target) if target else 0
    target = [r.ljust(W, '.') for r in target]

    # Reconstruct target pixel rows as '0'/'1' grids (1 = light = '#').
    T = [tuple(1 if c == '#' else 0 for c in r) for r in target]

    # Build target rows as sets of lit columns but keep full width for later.
    # Target is indexed by row t and column c (column 0 = leftmost printed char).
    # We will infer transitions by simulating candidate machines.

    def score(machine, extra=None):
        # machine: TM program string. Simulate it.
        # parse
        parts = machine.split('_')
        # pad missing states as undefined/halt
        trans = {}
        for part in parts:
            if not part:
                continue
            # part = tri tri
            for read_bit in (0, 1):
                tok = part[3*read_bit:3*read_bit+3]
                if len(tok) < 3:
                    return -1.0, None, None
                wb, mv, ns = tok[0], tok[1], tok[2]
                if wb not in '01' or mv not in 'LR' or not ('A' <= ns <= 'Z'):
                    return -1.0, None, None
                trans[(chr(ord('A') + parts.index(part)) if False else None)] = None
        # state letters are derivable by position
        states_list = []
        for i, part in enumerate(parts):
            st = chr(ord('A') + i)
            states_list.append(st)
            for rb in (0, 1):
                tok = part[3*rb:3*rb+3]
                if len(tok) < 3:
                    return -1.0, None, None
                wb, mv, ns = tok[0], tok[1], tok[2]
                if wb not in '01' or mv not in 'LR' or not ('A' <= ns <= 'Z'):
                    return -1.0, None, None
                trans[(st, rb)] = (int(wb), mv, ns)
        # Simulate until halt or H steps.
        tape = {}
        head = 0
        st = 'A'
        head_min = 0
        head_max = 0
        rows = []
        for t in range(H):
            rows.append(tuple(tape.get(c, 0) for c in range(head_min, head_max + 1)))
            if (st, tape.get(head, 0)) in trans:
                wb, mv, ns = trans[(st, tape.get(head, 0))]
                tape[head] = wb
                if mv == 'L':
                    head -= 1
                else:
                    head += 1
                st = ns
            else:
                # halted: tape/head frozen. We break but must fill remaining rows.
                # We'll fill identical rows for the rest.
                frozen = tuple(tape.get(c, 0) for c in range(head_min, head_max + 1))
                while len(rows) < H:
                    rows.append(frozen)
                break
            if head < head_min:
                head_min = head
            if head > head_max:
                head_max = head
        # fill rows if we didn't reach H (shouldn't happen)
        while len(rows) < H:
            rows.append(rows[-1] if rows else tuple())
        # Now crop candidate to all columns visited by head in rows 0..H-1.
        # Actually we already cropped to head_min..head_max over whole simulation.
        # But row 0 of candidate tape is blank (all zeros) and target row 0 is blank too.
        # target columns: 0..W-1.
        # Alignment shift a: candidate column c corresponds to target column c + a.
        # union width = range from min(0, cand_min) to max(W, cand_max + a) for chosen a.
        # Compute crop of candidate: columns head_min..head_max are the visited ones.
        cand_crop = rows  # list of tuples over [head_min, head_max]
        cand_min = head_min
        cand_max = head_max
        best_acc = -1.0
        best_shift = None
        # candidate crop width
        cw = cand_max - cand_min + 1 if cand_max >= cand_min else 0
        # enumerate shifts so that crops overlap in target coordinate system
        # target columns 0..W-1; candidate columns map to target via shift a: target_col = cand_col + a
        # We want best accuracy over a range. Candidate start target coordinate min_a such that crops overlap,
        # but accuracy denominator uses union width even for non-overlap.
        # So enumerate a from -cand_max to W-1-cand_min (at least some overlap) plus a bit around.
        lo = -cand_max - 2
        hi = W - 1 - cand_min + 2
        if cw == 0 or cw > 1000:
            return -1.0, None, None
        for a in range(lo, hi + 1):
            # union columns in target coordinate: from min(0, cand_min+a) to max(W-1, cand_max+a)
            ul = min(0, cand_min + a)
            ur = max(W - 1, cand_max + a)
            uw = ur - ul + 1
            correct = 0
            for t in range(H):
                row = cand_crop[t] if t < len(cand_crop) else cand_crop[-1]
                # for each column in union
                # target col u -> candidate index = u - a - cand_min ; valid if 0 <= idx < cw
                for u in range(ul, ur + 1):
                    tc = T[t].get(u, 0) if u >= 0 else 0
                    idx = u - a - cand_min
                    cc = row[idx] if 0 <= idx < cw else (None if False else 0)
                    # But wait: non-overlapping candidate columns are wrong even if blank.
                    # If candidate has no column there, then the pixel is 'wrong' if target has a lit pixel?
                    # Actually "EVERY pixel in a non-overlapping column is wrong, even if it is blank."
                    # So if u not in candidate coordinate range, the candidate pixel is considered wrong (0 correction).
                    cand_in = (cand_min + a) <= u <= (cand_max + a)
                    if not cand_in:
                        # wrong pixel -> no correct, and 0 != target? Actually wrong regardless.
                        # We just don't count it correct.
                        continue
                    if tc == cc:
                        correct += 1
            acc = correct / (H * uw) if H > 0 and uw > 0 else 0.0
            if acc > best_acc:
                best_acc = acc
                best_shift = a
        return best_acc, best_shift, (cand_min, cand_max)

    # Instead of brute force, infer elementary machine.
    # The target looks like a diagonal / triangle growth pattern.
    # Common simple solution: a 3-state machine that moves right, writes 1, loops.
    # But target is 80 rows x 40 columns and has specific growing pattern.
    # We can attempt to infer transitions directly from target by searching
    # small machines and picking best accuracy.

    # Generate candidates.
    # Candidate 1: simple right-moving writer that never halts (infinite).
    # machine "1RB1RB" -> state A: 1RB 0? need two tokens.
    # Let's define one-state machine: row A = "1RB1RB". This writes 1 and moves R, loops forever.
    # That gives row t: lit columns 0..t, no halt. Target row t seems to have structure with '#'.
    # But reference target row t has '#' at various positions, not just prefix.

    # Better: infer the machine's behavior from target rows.
    # Target row 0 is blank. row 1 has '#' at last column (col 39). That suggests
    # head starts at some column and writes '#' moving left or right? Actually row 1
    # has '#' at column 39 (rightmost). row 2 has '##' at 38,39. row 3 '###' at 37..39.
    # So pattern: starts writing at col 39 row1, then row2 writes col38, etc.
    # So machine writes '#' at cell, moves left, writes '#', moves left... i.e., writes a diagonal.
    # But then later rows show more complex patterns with gaps.
    # Actually let's look at the target: it appears to be a repeating diagonal pattern
    # like a glider or "space-time weave" where '#' patterns propagate left and up.

    # Perhaps it's a known simple TM that produces a fractal. Let's try common tiny machines.
    # Machine "1LB0RB" maybe? One state A: read 0 -> 1LB, read 1 -> 0RB. That's a toggle moving L.
    # Let's brute force small machines: states A only (1 state) or 2 states.

    # We have cached enumerate_tnf but we may not rely. Let's do our own search for
    # machines with at most 2 states and up to 4 defined transitions (others undefined/halt).
    # But target likely needs more states because pattern is complex.

    # Let's first try some obvious simple machines and score them.
    candidates = []
    # A writes 1 and moves left, never halt (2 tokens both 1LB)
    candidates.append("1LB1LB")
    candidates.append("1LB0LB")
    candidates.append("1RB1RB")
    candidates.append("1LB1RB")
    # 2-state machines
    # We'll generate a set of 1-state and 2-state machines with limited defined transitions.
    # But 2 tokens per state per read bit => up to 4 tokens per state, 2 states = 8 tokens.
    # Too many to brute force fully, but we can random sample or use target inference.

    # Target inference: examine row t vs row t-1.
    # Compute for each column c the write occurred? Not directly observable.
    # But head position can be guessed from where changes happen.

    # Let's write a helper that given a machine simulates and returns accuracy.
    def make_machine(tokens):
        # tokens: list of (write, move, next) for states A,B,...; tokens for read 0 and 1.
        # tokens as string e.g. "1LB0RB"
        return tokens

    best = None
    for m in candidates:
        acc, shift, crop = score(m)
        if best is None or acc > best[0]:
            best = (acc, m, shift, crop)
        if acc > 0.9:
            # refine further
            pass

    if best and best[0] > 0.5:
        return best[1]

    # Try to construct a machine that matches the observed diagonal pattern.
    # From target, rows show a moving triangle of '#' with some pattern.
    # Let's analyze the first few rows programmatically to infer writes.

    # Compute difference between target row t and row t-1 to guess writes.
    # But we don't know head. Let's try to find a simple pattern:
    # row t seems to have '#' at columns: for t=1: {39}; t=2: {38,39}; t=3: {37,38,39}; t=4: {36,38,39}? Actually row4: ".....#. #" -> "....#.#"? Let's recount row 4: ".....................................#.#" -> columns 37 and 39? Wait row index 4 (0-based)?
    # The target rows as printed: first row blank (row 0), second row ".......#" etc.
    # Row 1: '.......................................#' -> length 40? Let's index: 39 '#'.
    # Row 2: '......................................##' -> 38,39.
    # Row 3: '.....................................###' -> 37,38,39.
    # Row 4: '.....................................#.#' -> 37,39.
    # Row 5: '.....................................#..' -> 37.
    # Row 6: '.....................................##.' -> 37,38.
    # Row 7: '......................................#.' -> 38.
    # Row 8: '....................................#.#.' -> 36? Let's count: 35 dots then '#.#' -> positions 35? Actually string length 40.
    # Hard to manually parse. Instead, we can programmatically infer the machine's moves.

    # However, 90 seconds and Python only. We can do a bounded search over machines with at most 3 states and defined transitions.
    # Number of possible transitions per (state, read) is 8 (write 0/1, move L/R, next state up to 2 letters for 2 states) = 2*2*2 = 8 for 2 states (next can be A or B, undefined counts as halt option) => 9 options per cell.
    # Two states: 4 cells, each 9 options = 6561 machines. That's feasible.
    # For 3 states: 6 cells, each 2*2*3 + 1 (undefined) = 13 options => 13^6 ~ 4.8M, too many for full simulation but maybe with pruning.
    # Let's do full search for 2-state machines first.

    # Build all 2-state machines.
    opt = []
    # undefined represented by None
    next_options = ['A', 'B', None]
    for wb in '01':
        for mv in 'LR':
            for ns in next_options:
                opt.append((wb, mv, ns))
    # For state A and B, each read bit (0,1) => 4 transition slots.
    # Total combos = len(opt)^4 = 9^4 = 6561. Good.
    # But note: undefined means halt. Multiple undefined can halt.
    # We'll enumerate all and simulate up to H=80 rows.
    # For speed, precompute transitions and simulate in a tight loop.
    # Since each simulation is cheap (80 steps), 6561*80 ~ 500k steps, fine.

    best_acc = -1.0
    best_machine = None
    # To speed simulation, we can write a specialized function.
    def sim_score(trans, H):
        # trans: dict (state, bit) -> (write, move, next) or None if undefined
        tape = {}
        head = 0
        st = 'A'
        head_min = 0
        head_max = 0
        rows = []
        for t in range(H):
            rows.append(tape)
            # copy current tape for row t? We'll build tuple later.
            # We need row t snapshot. We'll store a copy.
            # Instead, we can store the tape dict at each step.
            # For accuracy, we need pixel rows. Let's build list of dicts.
            # This is slow if we copy dict. Better: store only head_min..head_max changes.
            # We'll just store a tuple of tape values for the full visited range so far.
            # But range grows. Let's store the tape dict reference but copy on change.
            # Simpler: store snapshot as tuple of (head_min, head_max, list of values).
            # We'll do a two-pass: simulate and record (head_min, head_max, tuple of tape values in that range).
            # Actually, we can just build a list of rows where each row is a tuple of tape values for columns head_min..head_max at that time.
            # But columns visited may expand; earlier rows may not have values for the new columns (treat as 0).
            # Let's just store the full tape dict snapshot at each step (shallow copy is dict(tape)).
            # 80 steps, dict size small, fine.
            # Then after simulation, we know final head_min, head_max. We can crop.
            # Let's do that.
            # For speed, we'll collect list of dicts.
            # But 6561 machines * 80 * dict copy might be ~0.5M dict copies, ok.
            # Actually we can optimize: store tape as list of (pos,val) and record min/max, then materialize rows.
            # Let's just do the simple version and see.
            pass

    # Since we need to return quickly, let's implement a more efficient simulator.
    def simulate(trans, H):
        tape = {}
        head = 0
        st = 'A'
        hmin = 0
        hmax = 0
        rows = []  # each row: (hmin, hmax, list of values)
        for t in range(H):
            rows.append((hmin, hmax, [tape.get(c, 0) for c in range(hmin, hmax+1)]))
            tr = trans.get((st, tape.get(head, 0)))
            if tr is None:
                # halted: freeze remaining rows
                frozen = (hmin, hmax, [tape.get(c, 0) for c in range(hmin, hmax+1)])
                while len(rows) < H:
                    rows.append(frozen)
                break
            wb, mv, ns = tr
            tape[head] = wb
            if mv == 'L':
                head -= 1
                if head < hmin: hmin = head
            else:
                head += 1
                if head > hmax: hmax = head
            st = ns
        # now compute accuracy with best alignment against T
        # T is list of tuples of 0/1 length W.
        # Candidate crop: from hmin to hmax. For each row, we have values list length = hmax-hmin+1.
        # But rows were taken at different hmin/hmax. However hmin/hmax only change when expanding.
        # To keep it simple, we'll use the final hmin/hmax for all rows and treat missing as 0.
        final_min = hmin
        final_max = hmax
        cw = final_max - final_min + 1
        if cw <= 0:
            worker_acc = -1.0
            return -1.0
        best_a_acc = -1.0
        # We'll compute for shifts a in reasonable range.
        # Union width: target columns 0..W-1; candidate columns map to target via +a.
        # Candidate col c -> target col c + a.
        # Candidate range final_min..final_max.
        # For shift a, union target cols from min(0, final_min+a) to max(W-1, final_max+a).
        lo = -final_max - 2
        hi = W - 1 - final_min + 2
        if hi - lo > 200:
            # limit? target W=40, final_max likely small.
            pass
        for a in range(lo, hi+1):
            ul = min(0, final_min + a)
            ur = max(W - 1, final_max + a)
            uw = ur - ul + 1
            if uw <= 0:
                continue
            correct = 0
            for t in range(H):
                # get row values for final_min..final_max
                if t < len(rows):
                    rmin, rmax, vals = rows[t]
                    # vals covers rmin..rmax. For final_min..final_max, missing are 0.
                    # We'll index: for c in final_min..final_max, find in vals if rmin<=c<=rmax else 0.
                    # Precompute a mapping for this row? We'll just loop.
                    row_vals = {}
                    for i, v in enumerate(vals):
                        row_vals[rmin + i] = v
                else:
                    row_vals = {}
                for u in range(ul, ur+1):
                    tc = T[t][u] if 0 <= u < len(T[t]) else 0
                    # candidate coordinate
                    c = u - a
                    cand_in = final_min <= c <= final_max
                    if not cand_in:
                        # wrong pixel
                        continue
                    cc = row_vals.get(c, 0)
                    if tc == cc:
                        correct += 1
            acc = correct / (H * uw)
            if acc > best_a_acc:
                best_a_acc = acc
                best_a = a
        return best_a_acc

    # Enumerate 2-state machines
    opt_list = opt
    best_2 = None
    cnt = 0
    for t1 in opt_list:  # state A read0
        for t2 in opt_list:  # state A read1
            for t3 in opt_list:  # state B read0
                for t4 in opt_list:  # state B read1
                    trans = {
                        ('A', 0): t1,
                        ('A', 1): t2,
                        ('B', 0): t3,
                        ('B', 1): t4
                    }
                    acc = simulate(trans, H)
                    if best_2 is None or acc > best_2[0]:
                        best_2 = (acc, trans)
                        best_machine = (acc,trans)
                    cnt += 1
                    if cnt % 1000 == 0:
                        pass
    if best_2 and best_2[0] > 0.8:
        # return best machine string
        # Need to format as machine string with states in order A,B.
        # Format: row A: tokens for read0 then read1; row B similarly.
        def fmt_trans(trans):
            parts = []
            for st in ['A', 'B']:
                row = ''
                for rb in (0,1):
                    tr = trans.get((st, rb))
                    if tr is None:
                        row += '---'
                    else:
                        wb, mv, ns = tr
                        row += str(wb) + mv + ns
                parts.append(row)
            return '_'.join(parts)
        return fmt_trans(best_2[1])

    # If best 2-state not found, try 3-state with random search or structured.
    # Given time, we might guess a known simple machine.
    # The target might be generated by a 3-state machine like "1RB1LB_..." etc.
    # Let's try some handcrafted 3-state machines.
    # Maybe the machine is the "rule 110" crawler? Not sure.

    # Alternative: directly infer from target pattern.
    # The pattern seems to be a repeating diagonal of '#' moving left and up.
    # It might be the "U" shape machine (infinite binary tree)?
    # Let's analyze target: it looks like a repeating pattern of diagonal stripes.
    # Perhaps the machine is simply: A: 1RB 1RB (moves right writing 1 forever) => row t has '#' at 0..t. That would be a triangle at left, but target has triangle at right.
    # If we mirror: A: 1LB 1LB => writes at negative columns, but our tape is two-way infinite; crop to visited. Row t would have '#' at -t..-1. In target, the '#' are at the right side (columns 30-39). So maybe head starts at 39 and moves left? But initial head at 0.
    # Actually initial head at cell 0. Target row 1 has '#' at column 39. That means head moved 39 steps right before first write? Or the tape crop alignment is arbitrary; the crop is to columns visited. Column 0 in target is leftmost printed char, which may not be head start.
    # The problem says: "Crop the candidate to ALL columns visited by the head in rows 0..H-1; do not truncate to target width." and "For each integer horizontal alignment, equal pixels in overlapping columns are correct". So alignment is arbitrary. Thus the absolute columns don't matter, only relative pattern.
    # So target row t has a pattern that, when aligned, matches candidate.
    # The target's leftmost column in the printout is 0, but alignment can shift.
    # So we just need the pattern.

    # Let's look at the pattern: rows 0-80. It looks like a diagonal band of '#' moving left, with period ~4? Actually:
    # Row 1: ....# (one)
    # Row 2: ...##
    # Row 3: ..###
    # Row 4: ..#.#
    # Row 5: ..#..
    # Row 6: ..##
    # Row 7: ...#.
    # Row 8: ...#.#
    # This suggests a repeating pattern of a block that moves left by 1 each row and changes shape.
    # It might be the "Gosper glider gun"? No, that's 2D.
    # This is 1D TM space-time diagram. The pattern looks like a "bloom" or "expanding triangle with holes".

    # Given limited time, maybe the best 2-state machine we found is already high accuracy. Let's compute best_2 accuracy and return it.
    if best_2:
        # return best 2-state machine
        def fmt_trans(trans):
            parts = []
            for st in ['A', 'B']:
                row = ''
                for rb in (0,1):
                    tr = trans.get((st, rb))
                    if tr is None:
                        row += '---'
                    else:
                        wb, mv, ns = tr
                        row += str(wb) + mv + ns
                parts.append(row)
            return '_'.join(parts)
        m = fmt_trans(best_2[1])
        return m

    # Fallback: return a simple machine that might be close.
    return "1RB1RB"

