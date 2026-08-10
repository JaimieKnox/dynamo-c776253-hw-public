# Compaction

When an append cannot fit in the remaining ring pages, compaction folds live keys with the same tombstone and wrap-newer rules as NVS recovery, erases ring pages 0 through 27, and rewrites each live key as a fresh sealed put.

Compaction is a space-recovery transform, not a sequence-domain reset. The sequence counter is not restarted at 1 by compaction. Each rewritten live key is allocated the next value from the pre-compaction append counter, so the post-rewrite tip continues from that continued allocation. After rewrite returns, in-memory ring placement and append allocation must again match the rewritten flash under the same tip coherence rules as a reboot scan, so later puts do not overlap rewritten records.

Live-key fold during compaction uses the same wrap-newer and tombstone rules as NVS recovery.

Rewrite emits those puts in modular older-first order among the live keys so the post-rewrite tip lands on the newest rewritten allocation.

After reclaim rewrite returns, in-memory append allocation must follow the post-rewrite wrap tip under the same tip coherence rules as a reboot scan so later puts continue that tip rather than a frozen pre-reclaim counter.

After reclaim rewrite returns, in-memory append allocation must follow the post-rewrite wrap tip under the same tip coherence rules as a reboot scan so later puts continue that tip rather than a frozen pre-reclaim counter.

After reclaim rewrite returns, in-memory append allocation must follow the post-rewrite wrap tip under the same tip coherence rules as a reboot scan so later puts continue that tip rather than a frozen pre-reclaim counter.

After reclaim rewrite returns, in-memory append allocation must follow the post-rewrite wrap tip under the same tip coherence rules as a reboot scan so later puts continue that tip rather than a frozen pre-reclaim counter.

After reclaim rewrite returns, in-memory append allocation must follow the post-rewrite wrap tip under the same tip coherence rules as a reboot scan so later puts continue that tip rather than a frozen pre-reclaim counter.
