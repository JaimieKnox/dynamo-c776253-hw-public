# Reclaim

When an append cannot fit in the remaining journal pages, reclaim runs:

1. Fold live keys from complete records using the same tombstone-respecting rules as KV recovery. A tombstoned key must be omitted from the rewrite set.
2. Erase journal pages 0 through 27.
3. Rewrite each remaining live key as a fresh sealed put that consumes the advancing `next_seq` counter from the pre-erase tip. Rewrite order among live keys follows modular sequence order under the journal wrap rule (older live sequences first). Continue the pre-erase `next_seq` tip through the rewrite loop. Do not reset the sequence counter to `1` after erase. Leave `next_seq` at the post-rewrite tip so later appends and the recovered generation continue through wrap. Each rewrite consumes a new sequence from that advancing counter.
4. Resume the append that triggered reclaim.

Disposable `pad_puts` keys exist only to pressure space. After reclaim they may remain if they were live.
