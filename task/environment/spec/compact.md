# Compaction

When an append cannot fit in the remaining ring pages, compaction folds live keys with the same tombstone and wrap-newer rules as NVS recovery, erases ring pages 0 through 27, and rewrites each live key as a fresh sealed put.

Compaction is a space-recovery transform. After rewrite returns, tip reporting and append allocation must again be mutually coherent under the same tip coherence rules as a reboot scan of the rewritten ring. Live-key fold during compaction uses the same wrap-newer and tombstone rules as NVS recovery.
