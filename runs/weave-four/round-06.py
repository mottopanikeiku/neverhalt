def search(target):
    h = len(target)
    W = max((len(r) for r in target), default=0)
    M = W + 40
    off = 20
    grid = [[0]*M for _ in range(h)]
    for i,r in enumerate(target):
        for j,ch in enumerate(r):
            if ch == '#':
                grid[i][off+j] = 1
    tape0 = [0]*(M+60)
    c0 = 30
    for t in range(M+60):
        tape0[c0+t] = 0

    # target[t] gives tape state after t steps. Reconstruct trajectory.
    # We must infer head path. Since we only know full tape, we simulate a
    # small search over possible head moves: choose the head position where
    # tape[t] can differ from tape[t+1].
    # Simplest: run BFS over states (head, state_name) with candidate rules.
    # But target is highly structured: it is a left-moving pulse.
    # We build a candidate machine directly from observed writes.

    # Build rows: row0 = 0 (blank), row t+1 = target row t.
    rows = [[0]*(M+60) for _ in range(h+1)]
    for t in range(h+1):
        for j in range(M+60):
            if t < h and off == off:
                pass
    for t in range(h):
        for j in range(M):
            rows[t+1][off + (j - off)] = grid[t][j] if (j-off) < W else 0
    for t in range(h+1):
        for j in range(M, M+60):
            rows[t][j] = 0

    # Locate head positions: head after t steps must be where row t+1 differs from row t.
    heads = [c0]
    for t in range(h):
        r0 = rows[t]
        r1 = rows[t+1]
        diff = [j for j in range(M+60) if r0[j] != r1[j]]
        # head after t is either diff[0]-1 or diff[0]+1 depending on write direction
        if not diff:
            # no change: usually write same symbol and move
            heads.append(heads[-1] + 1)  # guess move R (target appears to move right? check)
        else:
            # examine direction by signs of motion trend
            j = diff[0]
            # if r0[j]==1 and r1[j]==0: erased -> head moved right from j
            if r0[j] == 1 and r1[j] == 0:
                heads.append(j)
            else:
                heads.append(j-1)
    # Overwrite unknown cells with zeros already done.

    # Infer writes and moves from target rows difference pattern.
    # Data-driven: use observed deltas.
    # We build state names in order of first use from inferred (read,write,move) triples.
    # We infer transitions from the sequence of target rows plus reconstructed heads.
    # Steps:
    #  head[t] : position before step t (step t is transition producing row t+1)
    #  read_bit = rows[t][head[t]]
    #  write_bit = rows[t+1][head_after_move] ... unknown, but we know diff
    # Because writes are sparse, we infer write bit by comparing rows[t+1] at head[t].
    # Actually state at step t: read rows[t][head[t]], write to tape, move, state changes.
    # Final tape is rows[t+1]; final head is head[t+1].
    # For transition t, the head after move is head[t+1]. Tape after write is
    # rows[t+1]. So the written bit (before move) is what remains at the cell
    # that the head vacated (if moved) or stayed at.

    # Compute writes/moves:
    writes = []
    moves = []
    for t in range(h):
        ht = heads[t]
        hn = heads[t+1] if t+1 < len(heads) else ht
        if hn == ht:
            move = 'S'
            # if move S allowed? Spec uses L/R only. If frozen, may have halted.
            move = 'R'  # assume R; we'll test
        elif hn == ht+1:
            move = 'R'
        elif hn == ht-1:
            move = 'L'
        else:
            move = 'R'
        # write bit: at position hn (head after move), tape is rows[t+1][hn].
        # The head was at ht before writing; it wrote at ht then moved to hn.
        # So written bit = rows[t+1][ht] if move R (cell vacated) else rows[t+1][ht].
        w = rows[t+1][ht]
        writes.append(w)
        moves.append(move)

    # Build transition table by grouping identical observations.
    # A state is identified by (previous head, read bit) -> but Turing state
    # must be deterministic function of tape only. Standard TM: state + read bit.
    # We infer state names by walking tape; reuse states with same (read, write, move).
    # Simply assign new state whenever (read,write,move) changes or when
    # previously seen action is different; reuse same action -> same state.
    states = []
    state_of_action = {}
    symbols = ['A']
    def get_state(action):
        if action not in state_of_action:
            nm = chr(ord('A') + len(symbols))
            if nm >= 'Z':
                nm = '{' + nm + '}'  # may not be valid; hope not needed
            symbols.append(nm)
            state_of_action[action] = nm
        return state_of_action[action]

    # We simulate and record transitions
    cur = 'A'
    defined = {}  # (state, readbit) -> (writebit, move, nextstate)
    tape = rows[0][:]
    head = c0
    for t in range(h):
        ht = heads[t]
        readb = tape[ht]
        # write
        wb = writes[t]
        mv = moves[t]
        # move head
        if mv == 'L':
            nh = ht - 1
        else:
            nh = ht + 1
        # next state: use action key
        key = (readb, wb, mv)
        if key not in state_of_action:
            nm = chr(ord('A') + len(symbols))
            state_of_action[key] = nm
            symbols.append(nm)
        ns = state_of_action.get(key)
        defined[(cur, readb)] = (wb, mv, ns)
        tape[ht] = wb
        head = nh
        cur = ns

    # Assemble machine string with states A,B,... in defined order.
    # Spec: rows separated by '_' ; each row two tokens of 3 chars.
    order = ['A'] + [s for s in symbols if s != 'A']
    lines = []
    for s in order:
        tokens = ['', '']
        for rb in (0, 1):
            tgt = defined.get((s, rb))
            if tgt is None:
                tokens[rb] = '---'
            else:
                wb, mv, ns = tgt
                tokens[rb] = str(wb) + mv + ns
        lines.append(tokens[0] + tokens[1])
    machine = '_'.join(lines)
    if len(machine) > 250:
        return machine[:250]
    return machine

