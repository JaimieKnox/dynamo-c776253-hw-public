# Compaction

When an append cannot fit in the remaining ring pages, compaction folds live keys with the same tombstone and newer-sequence rules as NVS recovery, erases ring pages 0 through 27, and rewrites each live key as a fresh sealed put.

Live rewrite order follows modular sequence order under the ring wrap rule (older live sequences first). The ring sequence counter that appends use is continuous across compaction: its tip before erase is the starting tip for the rewrite loop, and after compaction the counter remains at the post-rewrite tip so later appends and the recovered tip continue through wrap.

Disposable `pad_puts` keys exist only to pressure space. After compaction they may remain if they were live.
