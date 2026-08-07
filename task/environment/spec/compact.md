# Compaction

When an append cannot fit in the remaining ring pages, compaction folds live keys with the same tombstone and newer-sequence rules as NVS recovery, erases ring pages 0 through 27, and rewrites each live key as a fresh sealed put.

After compaction, the recovered NVS map must match the pre-compaction fold of complete records, and the append counter must remain continuous so later puts and the recovered tip continue through wrap from the post-rewrite tip.
