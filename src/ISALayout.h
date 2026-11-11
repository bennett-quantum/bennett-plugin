#pragma once
#include "llvm/Support/JSON.h"
#include "llvm/Support/FormatVariadic.h"
#include <map>
#include <set>
#include <string>
#include <vector>
namespace bennett {
bool rContractProfile();
inline std::string layoutEnvelopeJSON(const llvm::json::Value &value) {
  if(auto *object=value.getAsObject()) {
    std::map<std::string,const llvm::json::Value *> sorted;
    for(auto &item:*object)sorted[item.first.str()]=&item.second;
    std::string text="{";
    for(auto &item:sorted) {if(text.size()>1)text+=",";text+=layoutEnvelopeJSON(llvm::json::Value(item.first))+":"+layoutEnvelopeJSON(*item.second);}
    return text+"}";
  }
  if(auto *array=value.getAsArray()) {
    std::string text="[";for(auto &item:*array) {if(text.size()>1)text+=",";text+=layoutEnvelopeJSON(item);}return text+"]";
  }
  return llvm::formatv("{0}",value).str();
}
enum class LayoutScope { Classical, Oracle, Globals, WithoutInterfaces };
struct LayoutLeaf {
  std::vector<std::string> path;
  std::string value;
};
// ISA 0.9 §9.2/K47 uses original key components. Legacy 0.8 retains
// its dotted identity, including the old ordering and collision behaviour.
inline std::string layoutEnvelope(const llvm::json::Object &layout,
                          LayoutScope scope = LayoutScope::Classical,
                          llvm::StringRef owner = "",
                          const std::set<std::string> &referenced = {}) {
  const bool structured = rContractProfile();
  std::map<std::string, LayoutLeaf> leaves;
  auto append = [&](std::vector<std::string> path, const llvm::json::Value &value) {
    llvm::json::Array components;
    for (const auto &part : path) components.push_back(part);
    auto key = structured ? layoutEnvelopeJSON(llvm::json::Value(std::move(components))) : [&]() {std::string joined;for(auto &part:path) {if(!joined.empty())joined+=".";joined+=part;}return joined;}();
    leaves[key] = {std::move(path), layoutEnvelopeJSON(value)};
  };
  for (const auto &member : layout) {
    auto key = member.first.str();
    if (key == "globals")
      for (const auto &global : *member.second.getAsObject())
        append({key, global.first.str()}, global.second);
    else if (key == "interface_regions")
      for (const auto &regionOwner : *member.second.getAsObject())
        for (const auto &region : *regionOwner.second.getAsObject())
          append({key, regionOwner.first.str(), region.first.str()}, region.second);
    else append({key}, member.second);
  }
  std::string result;
  for (const auto &entry : leaves) {
    const auto &path = entry.second.path;
    bool include = false;
    switch (scope) {
    case LayoutScope::Classical: include = true; break;
    case LayoutScope::WithoutInterfaces: include = path[0] != "interface_regions"; break;
    case LayoutScope::Oracle:
      include = path[0] != "interface_regions" ||
          (structured ? llvm::StringRef(path[1]) == owner :
           llvm::StringRef(entry.first).starts_with("interface_regions." + owner.str() + "."));
      break;
    case LayoutScope::Globals:
      include = path[0] == "globals" && referenced.count(path[1]);
      break;
    }
    if (include) result += "layout " + entry.first + " " + entry.second.value + "\n";
  }
  return result;
}
}
