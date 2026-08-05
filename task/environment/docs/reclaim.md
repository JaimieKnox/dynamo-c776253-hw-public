# Reclaim

When an append cannot fit in the remaining journal pages, reclaim runs:

1. Fold live keys from complete records using the same tombstone-respecting rules as KV recovery. A tombstoned key must be omitted from the rewrite set. Skipping tombstones and rewriting the pre-delete value is wrong.
2. Erase journal pages 0 through 27.
3. Rewrite each remaining live key as a fresh sealed put that consumes the advancing `next_seq` counter from the pre-erase tip. Rewrite order among live keys follows modular sequence order under the journal wrap rule (older live sequences first). Leave `next_seq` at the post-rewrite tip so later appends and the recovered generation continue through wrap. Do not freeze or restore the pre-erase `next_seq` after rewrite. Do not reuse each key's prior sequence and do not invent a second sequence space.
4. Resume the append that triggered reclaim.

Disposable `pad_puts` keys exist only to pressure space. After reclaim they may remain if they were live.
