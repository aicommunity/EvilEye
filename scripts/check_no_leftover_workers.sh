#!/usr/bin/env bash
# Fail if spawned worker processes survive the test run (leaked MpControl pools).
set -u
sleep 2
# multiprocessing spawn children and the resource tracker started by this job.
leftovers="$(ps -eo pid,ppid,args | grep -E 'multiprocessing\.(spawn|resource_tracker)|spawn_main' | grep -v grep || true)"
if [ -n "$leftovers" ]; then
  echo "Leftover multiprocessing workers after tests:"
  echo "$leftovers"
  exit 1
fi
echo "No leftover workers."
