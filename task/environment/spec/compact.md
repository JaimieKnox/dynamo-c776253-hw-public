# Compaction

When an append cannot fit in the remaining ring pages, compaction folds live keys with the same tombstone and wrap-newer rules as NVS recovery, erases ring pages 0 through 27, and rewrites each live key as a fresh sealed put.

The sequence counter is not reset by compaction. Each rewritten live key is allocated the next value from the pre-compaction `next_seq`, so the post-rewrite tip continues upward from the pre-compaction tip through wrap. It does not restart at 1. After rewrite, later puts and the recovered tip continue under that same continued allocation. A reboot scan after rewrite still reports the wrap tip of the rewritten complete records, and later appends continue from that tip.

Live-key fold during compaction uses the same wrap-newer and tombstone rules as NVS recovery.

After compaction returns, append allocation follows the post-rewrite tip from that continued counter. Callers must not restore a pre-compaction sequence counter over the post-rewrite tip.
