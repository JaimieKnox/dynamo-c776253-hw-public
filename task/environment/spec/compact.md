# Compaction

When an append cannot fit in the remaining ring pages, compaction folds live keys with the same tombstone and wrap-newer rules as NVS recovery, erases ring pages 0 through 27, and rewrites each live key as a fresh sealed put.

Compaction is a space-recovery transform, not a sequence-domain reset. Live keys are rewritten as fresh sealed puts whose allocated sequences keep the ring tip coherent with the tip that the same live set would imply under ordinary append traffic. After rewrite, later puts and the recovered tip continue under that continued allocation. A reboot scan after rewrite still reports the wrap tip of the rewritten complete records.

Live-key fold during compaction uses the same wrap-newer and tombstone rules as NVS recovery.

Rewrite emits those puts in modular older-first order among the live keys so the post-rewrite tip lands on the newest rewritten allocation.

After reclaim returns, append allocation remains on the post-rewrite wrap tip among rewritten complete records. Do not keep a pre-reclaim append counter across reclaim when that counter disagrees with the post-rewrite wrap tip.
