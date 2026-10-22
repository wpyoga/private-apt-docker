#!/bin/bash

set -Eeuo pipefail

: "${CHECK_INTERVAL:=21600}"

case "$CHECK_INTERVAL" in ''|*[!0-9]*) echo 'CHECK_INTERVAL must be integer seconds' >&2; exit 1;; esac

(( CHECK_INTERVAL >= 3600 )) || { echo 'CHECK_INTERVAL must be at least 3600 seconds' >&2; exit 1; }

while :; do
  if /usr/local/bin/update.sh; then echo 'Update cycle complete'; else echo 'Update cycle failed; retry next interval' >&2; fi
  sleep "$CHECK_INTERVAL" & wait $!
done
