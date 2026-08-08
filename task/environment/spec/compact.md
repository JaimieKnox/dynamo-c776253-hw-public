# Compaction

When an append cannot fit in the remaining ring pages, compaction folds live keys with the same tombstone and newer-sequence rules as NVS recovery, erases ring pages 0 through 27, and rewrites each live key as a fresh sealed put in modular older-first sequence order under the ring wrap rule.

After rewrite, later puts and the recovered tip continue from the post-rewrite tip through wrap. Append allocation after compaction follows the same Write cursor invariants as a reboot scan.
