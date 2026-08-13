#!/usr/bin/env bash
# Initialize the durable TradeWave release-state directory on dev.
# This script does not create a release, acquire the dev activation lock, or deploy code.

set -euo pipefail

STATE_PARENT=/var/lib/tradewave
STATE_DIR=${STATE_PARENT}/release-state

if [[ ${EUID} -ne 0 ]]; then
    echo "ERROR: run as root so owner and mode can be established." >&2
    exit 1
fi

if ! getent passwd flask >/dev/null; then
    echo "ERROR: required service account 'flask' does not exist." >&2
    exit 1
fi

if [[ -L ${STATE_PARENT} || -L ${STATE_DIR} ]]; then
    echo "ERROR: release-state path must not be a symlink." >&2
    exit 1
fi
if [[ -e ${STATE_PARENT} && ! -d ${STATE_PARENT} ]]; then
    echo "ERROR: ${STATE_PARENT} exists but is not a directory." >&2
    exit 1
fi
if [[ -e ${STATE_DIR} && ! -d ${STATE_DIR} ]]; then
    echo "ERROR: ${STATE_DIR} exists but is not a directory." >&2
    exit 1
fi

if [[ ! -d ${STATE_PARENT} ]]; then
    install -d -o root -g root -m 0755 "${STATE_PARENT}"
fi
install -d -o flask -g flask -m 0750 "${STATE_DIR}"

owner_mode=$(stat -c '%U:%G %a' "${STATE_DIR}")
if [[ ${owner_mode} != 'flask:flask 750' ]]; then
    echo "ERROR: unexpected release-state owner/mode: ${owner_mode}" >&2
    exit 1
fi

printf 'release-state initialized: %s (%s)\n' "${STATE_DIR}" "${owner_mode}"
