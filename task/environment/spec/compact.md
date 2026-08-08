# Compaction

When an append cannot fit in the remaining ring pages, compaction folds live keys with the same tombstone and wrap-newer rules as NVS recovery, erases ring pages 0 through 27, and rewrites each live key as a fresh sealed put.

After rewrite, later puts and the recovered tip continue from the post-rewrite tip through wrap under the same Write cursor invariants as a reboot scan. Live-key fold during compaction uses the same wrap-newer and tombstone rules as NVS recovery.
