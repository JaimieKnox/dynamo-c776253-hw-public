#!/bin/bash
set -euo pipefail
cp -f /solution/fixed/journal.py /app/fw/journal.py
cp -f /solution/fixed/reclaim.py /app/fw/reclaim.py
cp -f /solution/fixed/slots.py /app/fw/slots.py
python3 -m fw /app/jobs /app/output
