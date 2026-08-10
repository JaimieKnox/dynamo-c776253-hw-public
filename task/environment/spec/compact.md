# Compaction

When an append cannot fit in the remaining ring pages, compaction folds live keys with the same wrap-newer and tombstone rules as NVS recovery, erases ring pages 0 through 27, and rewrites each live key as a fresh sealed put.

Compaction is a space-recovery transform. After rewrite returns, tip reporting and write-cursor placement must again be mutually coherent with crash-safe append placement under the same tip coherence rules as a reboot scan of the rewritten ring.
