#!/usr/bin/env bash
# Public prepare/finalise pipeline checks, including transient import aliases.
set -euo pipefail
ulimit -c 0
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if test "$#" = 0; then
  for major in 18 23; do bash "$0" --major "$major"; done
  exit 0
fi
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

for case in unknown stamped-unknown runtime-helper missing-provenance missing-transport-provenance retargeted; do
  case "$case" in
    unknown) sed 's/__bennett_rt_transport_clock_read/unknown_host/g' "$fixture" > "$work/$case.ll" ;;
    stamped-unknown) sed -e 's/__bennett_rt_transport_clock_read/unknown_host/g' -e 's/^declare void @unknown_host(ptr)$/declare void @unknown_host(ptr) #0/' "$fixture" > "$work/$case.ll" ;;
    runtime-helper) sed 's/__bennett_rt_transport_clock_read/__bennett_rt_unknown_helper/g' "$fixture" > "$work/$case.ll" ;;
    missing-provenance) sed 's/define void @entry() #0/define void @entry()/' "$fixture" > "$work/$case.ll" ;;
    missing-transport-provenance) sed 's/^declare void @__bennett_rt_transport_clock_read(ptr)$/define void @__bennett_rt_transport_clock_read(ptr %p) { ret void }/' "$fixture" > "$work/$case.ll" ;;
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

# Hand-written launch metadata binds exactly these fixture bytes, so this also
# exercises the real preparation identity checks without invoking a producer.
"$tool/llvm-as" "$root/tests/probes/native-transport-source.ll" -o "$work/device.bc"
identity=$(sha256sum "$work/device.bc" | cut -d' ' -f1)
bytes=$(stat -c %s "$work/device.bc")
printf '{"mode":"marked"}\n' > "$work/build.json"
build_hash=$(sha256sum "$work/build.json" | cut -d' ' -f1)
cat > "$work/launch-record.json" <<EOF
{"schema":"bennett-plugin-launch-record-1","entry":"entry","artifacts":{"device.bc":{"sha256":"$identity","bytes":$bytes},"entry/build.json":{"sha256":"$build_hash"}}}
EOF
prepare=("$tool/opt" "-load-pass-plugin=$plugin" -passes=bennett-native-comparison "-bennett-native-record=$work/launch-record.json" -bennett-native-entry=entry)
"${prepare[@]}" -bennett-native-prepare-only "-bennett-native-report=$work/prepared.json" "$work/device.bc" -S -o "$work/prepared.ll"
"$tool/opt" -passes=verify "$work/prepared.ll" -disable-output
# There are exactly two materialised definitions, entry and its ordinary runtime
# helper. The six transport wrappers are imports, without aliases or provenance.
jq -e '[.symbols[].llvm_name] | sort == ["__bennett_rt_source_helper", "entry"]' "$work/prepared.json" >/dev/null
test "$(rg -c '^declare .*@__bennett_rt_transport_' "$work/prepared.ll")" = 6
if rg -q '^define .*@__bennett_rt_transport_|^@.* = alias .*@__bennett_rt_transport_' "$work/prepared.ll"; then
  echo 'preparation published a runtime transport definition' >&2
  exit 1
fi

# A closure link may pull production wrappers back in before finalisation.
extract=()
for transport in clock_read entropy_read console_write block_read block_write exit; do
  extract+=("--func=__bennett_rt_transport_$transport")
done
"$tool/llvm-extract" "${extract[@]}" "$work/device.bc" -o "$work/wrappers.bc"
"$tool/llvm-link" "$work/prepared.ll" "$work/wrappers.bc" --only-needed -o "$work/relinked.bc"
"${finalise[@]}" "-bennett-native-report=$work/finalised.json" "$work/relinked.bc" -S -o "$work/finalised.ll"
"$tool/opt" -passes=verify "$work/finalised.ll" -disable-output
test "$(rg -c '^declare .*@__bennett_rt_transport_' "$work/finalised.ll")" = 6
if rg -q 'call .*@__bennett_effect_' "$work/finalised.ll"; then
  echo 'source effect marker retained after finalisation' >&2
  exit 1
fi
jq -e --arg identity "$identity" '.phase == "finalised" and .materialised_sha256 == $identity and (.symbols | length) == 2' "$work/finalised.json" >/dev/null
"${prepare[@]}" "-bennett-native-report=$work/direct.json" "$work/device.bc" -S -o "$work/direct.ll"
"$tool/opt" -passes=verify "$work/direct.ll" -disable-output
test "$(rg -c '^declare .*@__bennett_rt_transport_' "$work/direct.ll")" = 6
test "$(sha256sum "$work/device.bc" | cut -d' ' -f1)" = "$identity"
echo "LLVM $major: import alias, six transport wrappers, closure relink, direct adaptation; six provenance failures rejected"
