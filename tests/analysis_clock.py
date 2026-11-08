#!/usr/bin/env python3
"""Compiler analysis allowance counts its own CPU, excluding blocked time."""

import json
from pathlib import Path
import subprocess

from contracts import ROOT as R

d = R / ".tmp/analysis-clock"
d.mkdir(parents=True, exist_ok=True)
source = d / "clock.cpp"
source.write_text(r"""
#include "AnalysisBudgetClock.h"
#include <chrono>
#include <cstdio>
#include <ctime>
#include <thread>
int main() {
  bennett::AnalysisBudgetClock budget(50);
  auto wall = std::chrono::steady_clock::now();
  std::this_thread::sleep_for(std::chrono::milliseconds(150));
  if (!budget.expired() || *budget.expired()) return 1;
  // Unrelated compiler work in another thread must not consume this S2
  // invocation's allowance. std::clock independently measures process CPU.
  std::thread other([] {
    auto begin = std::clock();
    volatile unsigned long long value=0;
    while (1000.0*(std::clock()-begin)/CLOCKS_PER_SEC < 150)
      for (unsigned i=0;i<1024;++i) value += i;
  });
  other.join();
  if (!budget.expired() || *budget.expired()) return 2;
  auto blocked = budget.elapsedNanoseconds();
  if (!blocked || *blocked >= 50 * 1000000ULL) return 4;
  volatile unsigned long long value=0;
  while (budget.expired() && !*budget.expired())
    for (unsigned i=0;i<1024;++i) value += i;
  if (!budget.expired() || !*budget.expired()) return 3;
  auto consumed = budget.elapsedNanoseconds();
  if (!consumed || *consumed < 50 * 1000000ULL || *consumed < *blocked) return 5;
  auto elapsed=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-wall).count();
  std::printf("{\"passed\":5,\"cases\":5,\"wall_ms\":%lld}\n",(long long)elapsed);
}
""")
exe = d / "clock"
z = subprocess.run(
    [
        "c++",
        "-std=c++17",
        "-O2",
        "-pthread",
        "-I" + str(R / "src"),
        str(source),
        "-o",
        str(exe),
    ],
    capture_output=True,
    text=True,
    timeout=600,
)
assert z.returncode == 0, z.stderr
z = subprocess.run([str(exe)], capture_output=True, text=True, timeout=600)
assert z.returncode == 0, (z.returncode, z.stdout, z.stderr)
result = json.loads(z.stdout)
assert result["passed"] == result["cases"] == 5 and result["wall_ms"] >= 150
(R / ".tmp/analysis-clock.json").write_text(json.dumps(result, indent=2) + "\n")
print(z.stdout, end="")
