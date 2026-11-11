#pragma once
#include <algorithm>
#include <initializer_list>
#include <memory>
#include <set>
#include <unordered_map>
#include <utility>
#include <vector>

namespace bennett {
template <class T> class AnalysisAtomSetInterner;

// Ordered, immutable views share storage. Mutations preserve every other view
// and return iterators into the new storage, including after a shared erase.
template <class T> class AnalysisAtomSet {
  using Set = std::set<T>;
  std::shared_ptr<Set> storage;
  friend class AnalysisAtomSetInterner<T>;
  static const Set &none() { static const Set empty; return empty; }
  const Set &get() const { return storage ? *storage : none(); }
  Set &mutate() {
    if (!storage) storage = std::make_shared<Set>();
    else if (!storage.unique()) storage = std::make_shared<Set>(*storage);
    return *storage;
  }
  template <class Value> auto insertValue(Value &&value) {
    auto found = get().find(value);
    if (found != get().end()) return std::make_pair(found, false);
    auto result = mutate().insert(std::forward<Value>(value));
    return std::make_pair(typename Set::const_iterator(result.first), result.second);
  }
public:
  using value_type = T;
  using iterator = typename Set::const_iterator;
  using const_iterator = typename Set::const_iterator;
  using reverse_iterator = typename Set::const_reverse_iterator;
  using const_reverse_iterator = typename Set::const_reverse_iterator;
  AnalysisAtomSet() = default;
  AnalysisAtomSet(std::initializer_list<T> values) {
    if (values.size()) storage = std::make_shared<Set>(values);
  }
  const_iterator begin() const { return get().begin(); }
  const_iterator end() const { return get().end(); }
  const_reverse_iterator rbegin() const { return get().rbegin(); }
  const_reverse_iterator rend() const { return get().rend(); }
  size_t size() const { return get().size(); }
  bool empty() const { return get().empty(); }
  size_t count(const T &value) const { return get().count(value); }
  const_iterator find(const T &value) const { return get().find(value); }
  const_iterator lower_bound(const T &value) const { return get().lower_bound(value); }
  std::pair<const_iterator, bool> insert(const T &value) { return insertValue(value); }
  std::pair<const_iterator, bool> insert(T &&value) { return insertValue(std::move(value)); }
  const_iterator insert(const_iterator hint, const T &value) {
    if (!storage || !storage.unique()) return insert(value).first;
    return storage->insert(hint, value);
  }
  const_iterator erase(const_iterator position) {
    if (!storage.unique()) {
      T value = *position;
      auto &set = mutate();
      return set.erase(set.find(value));
    }
    return storage->erase(position);
  }
  size_t erase(const T &value) {
    if (!get().count(value)) return 0;
    return mutate().erase(value);
  }
  void clear() { storage.reset(); }
};

// Hashes select candidates only. The entire ordered set must match, including
// every kind, origin, offset, width and provenance bit in T's ordering.
// Weak entries do not retain dead sets or extend their analysis lifetime.
template <class T> class AnalysisAtomSetInterner {
  using Set = std::set<T>;
  std::unordered_map<size_t, std::vector<std::weak_ptr<Set>>> buckets;
public:
  bool intern(AnalysisAtomSet<T> &atoms, size_t hash) {
    if (!atoms.storage) return false;
    auto &bucket = buckets[hash];
    for (auto it = bucket.begin(); it != bucket.end();) {
      if (auto prior = it->lock()) {
        if (prior == atoms.storage) return true;
        if (prior->size() == atoms.size() &&
            std::equal(prior->begin(), prior->end(), atoms.begin(),
                       [](const T &a, const T &b) { return !(a < b) && !(b < a); })) {
          atoms.storage = std::move(prior);
          return true;
        }
        ++it;
      } else it = bucket.erase(it);
    }
    bucket.push_back(atoms.storage);
    return false;
  }
};
}
