# Reclaim

When an append cannot fit in the remaining journal pages, reclaim runs:

1. Fold live keys from complete records using the same tombstone-respecting rules as KV recovery.
2. Erase journal pages 0 through 27.
3. Rewrite each remaining live key as a fresh sealed put. The sequence stream must stay continuous across the erase so later appends and the recovered generation tip remain correct through wrap. Do not invent a second sequence space for rewritten keys.
4. Resume the append that triggered reclaim.

Disposable `pad_puts` keys exist only to pressure space. After reclaim they may remain if they were live.
