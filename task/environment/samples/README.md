# Sample jobs

`sample_01` and `sample_02` are narrow calibration scripts. They never tear mid-commit, never wrap the 16-bit sequence near the top of the counter, never force journal reclaim, never interrupt promote, and never rely on anti-rollback rejection. Passing samples alone does not prove correct recovery under hard jobs.
