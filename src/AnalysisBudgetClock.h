#pragma once
#include <cstdint>
#include <optional>
#include <time.h>

namespace bennett {
// S2 is single-threaded. Scheduler delays and unrelated compiler threads are
// outside its CPU allowance; the caller owns any overall wall-clock deadline.
class AnalysisBudgetClock {
  static std::optional<uint64_t> read() {
    timespec time;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &time) != 0 || time.tv_sec < 0)
      return std::nullopt;
    return uint64_t(time.tv_sec) * 1000000000 + uint64_t(time.tv_nsec);
  }
  std::optional<uint64_t> start = read();
  uint64_t limit;
public:
  explicit AnalysisBudgetClock(unsigned milliseconds)
      : limit(uint64_t(milliseconds) * 1000000) {}
  std::optional<bool> expired() const {
    auto now = read();
    if (!start || !now || *now < *start) return std::nullopt;
    return *now - *start >= limit;
  }
};
}
