#!/bin/sh
#BASE_DIR="./D4A2/04_recording_addr_size/run_test/snapshots"
BASE_DIR="./D4A2/02_recording/snapshots"

for ante in "$BASE_DIR"/*anterior.bin; do
  if [ -f "$ante" ]; then
    post="${ante%anterior.bin}posterior.bin"
    result=$(radiff2 "$ante" "$post")
    case $result in
      (*[![:blank:]]*) printf '%s:\n%s\n' "${ante%_anterior.bin}" "$result";;
      (*) ;;
    esac
  fi
done