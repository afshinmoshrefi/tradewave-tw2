#!/usr/bin/env bash
# DEPRECATED: use  run.sh prod <script> [tier]  instead.
# Thin forwarder kept so existing docs / muscle-memory keep working.
# The old sed-rewrite approach is gone; coordinates now come from prod_target.env
# via run.sh (payloads get the env file prepended; orchestrators source it).
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run.sh" prod "$@"
