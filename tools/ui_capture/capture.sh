#!/usr/bin/env bash
# Thin runner for capture.js - see capture.js for all the real documentation.
# Usage: ./capture.sh specs/some_spec.json
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec node capture.js "$1"
