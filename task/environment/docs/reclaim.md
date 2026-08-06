# Reclaim

When an append cannot fit in the remaining journal pages, reclaim folds live keys with the same tombstone rules as KV recovery, erases journal pages 0 through 27, and rewrites each live key as a fresh sealed put.

Live rewrite order follows modular sequence order under the journal wrap rule (older live sequences first). Do not sort the rewrite by raw numeric sequence order. The journal sequence counter that appends use is continuous across reclaim: its tip before erase is the starting tip for the rewrite loop, and after reclaim the counter remains at the post-rewrite tip so later appends and the recovered generation continue through wrap. Do not restore the pre-erase tip after the rewrite loop finishes.

Disposable `pad_puts` keys exist only to pressure space. After reclaim they may remain if they were live.
