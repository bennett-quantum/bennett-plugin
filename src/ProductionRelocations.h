#pragma once

#include "llvm/ADT/StringExtras.h"
#include "llvm/ADT/StringRef.h"
#include <map>
#include <string>

namespace bennett {

// Generated address markers have a decimal index and a trailing word boundary.
// Resolve all indices together so linking visits each body only once, regardless
// of how many function addresses the module takes. No leading boundary is needed
// (matching the original CCFUNCTION<n>\b substitution).
struct ProductionRelocations {
  std::map<std::string, std::string> values;
  uint64_t inputBytes = 0;
  uint64_t scannedBytes = 0;

  void replace(std::string &text, llvm::StringRef prefix) {
    if (values.empty()) return;
    inputBytes += text.size();
    scannedBytes += text.size();
    std::string result;
    size_t last = 0, pos = 0;
    while ((pos = text.find(prefix.str(), pos)) != std::string::npos) {
      auto begin = pos;
      pos += prefix.size();
      auto digits = pos;
      while (pos < text.size() && llvm::isDigit(text[pos])) ++pos;
      if (pos < text.size() && (llvm::isAlnum(text[pos]) || text[pos] == '_'))
        continue;
      auto found = values.find(text.substr(digits, pos - digits));
      if (found == values.end()) continue;
      result.append(text, last, begin - last);
      result += found->second;
      last = pos;
    }
    if (!last) return;
    result.append(text, last, std::string::npos);
    text = std::move(result);
  }
};

} // namespace bennett
