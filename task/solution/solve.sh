#!/bin/bash
set -euo pipefail
cp -f /solution/fixed/ringlog.py /app/norctl/ringlog.py
cp -f /solution/fixed/compact.py /app/norctl/compact.py
cp -f /solution/fixed/banks.py /app/norctl/banks.py
cp -f /solution/fixed/nvs.py /app/norctl/nvs.py
cp -f /solution/fixed/runtime.py /app/norctl/runtime.py
python3 -m norctl /app/cases /app/out
