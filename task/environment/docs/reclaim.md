# Reclaim

When an append cannot fit in the remaining journal pages, reclaim runs:

1. Fold live keys from complete records using the same tombstone-respecting rules as KV recovery.
2. Erase journal pages 0 through 27.
3. Rewrite each remaining live key as a fresh sealed put that consumes the advancing `next_seq` counter from the pre-erase tip. Leave `next_seq` at the post-rewrite tip so later appends and the recovered generation continue through wrap. Do not reuse each key's prior sequence and do not invent a second sequence space.
4. Resume the append that triggered reclaim.

Disposable `pad_puts` keys exist only to pressure space. After reclaim they may remain if they were live.
