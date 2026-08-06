# Reclaim

When an append cannot fit in the remaining journal pages, reclaim runs:

1. Fold live keys from complete records using the same tombstone-respecting rules as KV recovery. A tombstoned key must be omitted from the rewrite set.
2. Erase journal pages 0 through 27.
3. Rewrite each remaining live key as a fresh sealed put. Rewrite order among live keys follows modular sequence order under the journal wrap rule (older live sequences first). Each rewrite consumes the next value from the journal sequence counter as recovered for appends, using that counter's tip from before the erase as the starting point, then leaves the counter at the post-rewrite tip.
4. Resume the append that triggered reclaim.

Disposable `pad_puts` keys exist only to pressure space. After reclaim they may remain if they were live.
