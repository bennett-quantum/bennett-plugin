// Preserve the source-to-object association at the materialisation boundary.
json::Object nativeGlobalMapping(const Entry &e, const json::Object &build) {
  json::Object globals;
  auto *placed=build.getObject("layout")->getObject("globals");
  for(auto &item:*placed) {
    auto *row=item.second.getAsObject();
    auto source=e.deviceGlobalSources.find(item.first.str());
    if(source==e.deviceGlobalSources.end())fail("output","missing device global source correspondence");
    globals[item.first]=json::Object{{"source_key",source->second},
      {"base",*row->getInteger("base")},{"size",*row->getInteger("size")}};
  }
  return json::Object{{"schema","bennett-device-native-globals-1"},{"globals",std::move(globals)}};
}
