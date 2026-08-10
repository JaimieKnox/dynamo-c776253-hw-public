# Compaction

When an append cannot fit in the remaining ring pages, compaction folds live keys with the same tombstone and wrap-newer rules as NVS recovery, erases ring pages 0 through 27, and rewrites each live key as a fresh sealed put.

Compaction is a space-recovery transform, not a sequence-domain reset. The sequence counter continues from the pre-compaction append counter rather than restarting at 1, so rewritten allocations advance from that continued counter. After rewrite returns, in-memory ring placement and append allocation must again match the rewritten flash under the same tip coherence rules as a reboot scan.

Live-key fold during compaction uses the same wrap-newer and tombstone rules as NVS recovery.

Rewrite order must leave the wrap tip among rewritten records on the wrap-newest live key allocation, so later appends continue that tip under the tip coherence rules above.
