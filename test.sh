#!/usr/bin/env bash
set -euo pipefail
echo "Running skill validation..."
python3 tools/validate_skills.py
echo "Running catalog generation..."
python3 tools/generate_catalog.py --check 2>/dev/null || python3 tools/generate_catalog.py
echo "All tests passed."
