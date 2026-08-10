# Compaction

When an append cannot fit in the remaining ring pages, compaction folds live keys with the same tombstone and wrap-newer rules as NVS recovery, erases ring pages 0 through 27, and rewrites each live key as a fresh sealed put.

Compaction is a space-recovery transform, not a sequence-domain reset. The sequence counter is not restarted at 1 by compaction. Each rewritten live key is allocated the next value from the pre-compaction append counter, so the post-rewrite tip continues from that continued allocation. After rewrite, later puts and the recovered tip continue under that same tip rule. A reboot scan after rewrite still reports the wrap tip of the rewritten complete records.

Live-key fold during compaction uses the same wrap-newer and tombstone rules as NVS recovery.

Rewrite emits those puts in modular older-first order among the live keys so the post-rewrite tip lands on the newest rewritten allocation.

After reclaim returns, append allocation remains on the post-rewrite wrap tip among rewritten complete records.
