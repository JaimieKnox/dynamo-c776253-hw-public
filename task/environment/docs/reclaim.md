# Reclaim

When an append cannot fit in the remaining journal pages, reclaim runs:

1. Fold live keys from complete records using the same tombstone-respecting rules as KV recovery (tombstone wins for a key, then the key is omitted).
2. Erase journal pages 0 through 27.
3. Rewrite each remaining live key as a fresh sealed put while keeping the in-memory `next_seq` cursor continuous across the erase so later appends continue that stream.
4. Resume the append that triggered reclaim.

Disposable `pad_puts` keys exist only to pressure space. After reclaim they may remain if they were live.

Generation after reclaim is still the modular sequence tip among complete records on flash under the journal newer rule. Compose that rule with the rewrite step above when a reclaim crosses a 16-bit wrap.
