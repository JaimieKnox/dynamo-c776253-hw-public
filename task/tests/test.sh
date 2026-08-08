#!/bin/bash
#
# Verifier entrypoint. Always exits 0. Writes reward 1/0.
# Phase A seals expectations from the independent reference model and removes it.
# Phase B grades agent outputs with no oracle import.
set -u
mkdir -p /logs/verifier
# Prevent agent-writable /app (ENV PYTHONPATH=/app) from shadowing stdlib/pytest.
unset PYTHONPATH
python3 -I -B /tests/derive_expectations.py
phase_one=$?
if [ $phase_one -eq 0 ]; then
  python3 -I -B -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
  status=$?
else
  echo "phase one failed with status $phase_one"
  status=$phase_one
fi
if [ $status -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
exit 0
