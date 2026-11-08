#!/usr/bin/env bash
# Public prepare/finalise pipeline checks, including transient import aliases.
set -euo pipefail
ulimit -c 0
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
test "$1" = --major
major=$2
tool=/usr/lib/llvm-$major/bin
plugin=$root/build/libbennett-plugin-$major.so
work=$root/.tmp/native-transports/$major
mkdir -p "$work"
fixture=$root/tests/probes/native-transport-import.ll
finalise=("$tool/opt" "-load-pass-plugin=$plugin" -passes=bennett-native-comparison-finalise)

# Only the importer intermediate needs -disable-verify: LLVM forbids aliases to
# declarations. The finalised output must pass the ordinary verifier unchanged.
"${finalise[@]}" -disable-verify "-bennett-native-report=$work/import.json" "$fixture" -S -o "$work/import.ll"
"$tool/opt" -passes=verify "$work/import.ll" -disable-output
rg -q '^declare void @__bennett_rt_transport_clock_read\(ptr\)' "$work/import.ll"
if rg -q '^@transport = alias' "$work/import.ll"; then
  echo 'runtime import retained a definition alias' >&2
  exit 1
fi
rg -q 'call void @__bennett_rt_transport_clock_read\(ptr null\)' "$work/import.ll"
jq -e '.phase == "finalised" and [.symbols[].native_symbol] == ["source"]' "$work/import.json" >/dev/null

for case in unknown stamped-unknown missing-provenance retargeted; do
  case "$case" in
    unknown) sed 's/__bennett_rt_transport_clock_read/unknown_host/g' "$fixture" > "$work/$case.ll" ;;
    stamped-unknown) sed -e 's/__bennett_rt_transport_clock_read/unknown_host/g' -e 's/^declare void @unknown_host(ptr)$/declare void @unknown_host(ptr) #0/' "$fixture" > "$work/$case.ll" ;;
    missing-provenance) sed 's/define void @entry() #0/define void @entry()/' "$fixture" > "$work/$case.ll" ;;
    retargeted) sed 's/@__bennett_rt_transport_clock_read/@__bennett_rt_transport_other_read/g' "$fixture" > "$work/$case.ll" ;;
  esac
  rm -f "$work/$case.json"
  if "${finalise[@]}" -disable-verify "-bennett-native-report=$work/$case.json" "$work/$case.ll" -disable-output >"$work/$case.stdout" 2>"$work/$case.stderr"; then
    echo "$case unexpectedly accepted" >&2
    exit 1
  fi
  rg -q 'BD-E-NATIVE-INPUT.*prepared source function provenance was lost' "$work/$case.stderr"
  test ! -e "$work/$case.json"
done

echo "LLVM $major: runtime import alias accepted; four provenance failures rejected"
