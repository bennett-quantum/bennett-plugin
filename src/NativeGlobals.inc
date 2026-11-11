// LLVM 23 may re-encode use lists without changing a single IR definition.
// Compare all printed IR, including metadata/attributes, when bit encoding differs.
bool sameNativeMaterialisation(Module &original, Module &current) {
  if(bits(original)==bits(current))return true;
  auto text=[](Module &module) {
    auto copy=CloneModule(module);copy->setModuleIdentifier("");
    std::string result;raw_string_ostream stream(result);copy->print(stream,nullptr);
    return result;
  };
  return text(original)==text(current);
}

// Adapter metadata only: ISA layout leaves retain their published schema.
json::Object readNativeBuild(const json::Object &artifacts) {
  auto bytes=read((sys::path::parent_path(NativeRecord)+"/build.json").str());
  auto *artifact=artifacts.getObject(NativeEntry+"/build.json");
  if(!artifact || artifact->getString("sha256")!=digest(bytes->getBuffer()))
    fail("BD-E-NATIVE-INPUT","build metadata does not match launch record");
  auto value=json::parse(bytes->getBuffer());
  if(!value)fail("BD-E-NATIVE-INPUT",toString(value.takeError()));
  auto *build=value->getAsObject();
  if(!build)fail("BD-E-NATIVE-INPUT","invalid build metadata");
  return std::move(*build);
}

json::Object nativeDeviceGlobals(const json::Object &build, const json::Array &symbols) {
  auto *mapping=build.getObject("native_global_mapping");
  auto *globals=mapping?mapping->getObject("globals"):nullptr;
  auto *layout=build.getObject("layout");
  auto *placed=layout?layout->getObject("globals"):nullptr;
  if(!mapping || mapping->getString("schema")!="bennett-device-native-globals-1" ||
      !globals || !placed || globals->size()!=placed->size())
    fail("BD-E-NATIVE-INPUT","R device global correspondence missing; regenerate launch artifacts");
  std::map<std::string,const json::Object *> sources;
  for(auto &symbol:symbols) {
    auto *row=symbol.getAsObject();
    if(row->getString("kind")=="global")sources[row->getString("source_key")->str()]=row;
  }
  json::Object result;std::set<std::string> used;
  for(auto &item:*globals) {
    auto *row=item.second.getAsObject();auto *fixed=placed->getObject(item.first);
    auto key=row?row->getString("source_key"):std::nullopt;
    if(!key || !fixed || !sources.count(key->str()) || !used.insert(key->str()).second)
      fail("BD-E-NATIVE-INPUT","invalid R device global source correspondence");
    auto *source=sources.at(key->str());
    auto base=row->getInteger("base"),size=row->getInteger("size");
    if(!base || *base<0 || !size || *size<0 || base!=fixed->getInteger("base") ||
        size!=fixed->getInteger("size") || size!=source->getInteger("size"))
      fail("BD-E-NATIVE-INPUT","R device global placement/size correspondence mismatch");
    result[item.first]=json::Object{{"source_key",*key},{"native_symbol",*source->getString("native_symbol")},
      {"base",*base},{"size",*size}};
  }
  return result;
}

void bindNativeGlobals(json::Object &report, const json::Object &build,
                       const json::Object &artifacts) {
  auto bytes=read((sys::path::parent_path(NativeRecord)+"/launch.bennett").str());
  auto *artifact=artifacts.getObject(NativeEntry+"/launch.bennett");
  auto hash=digest(bytes->getBuffer());
  if(!artifact || artifact->getString("sha256")!=hash ||
      artifact->getInteger("bytes")!=int64_t(bytes->getBufferSize()))
    fail("BD-E-NATIVE-INPUT","launch object does not match launch record");
  report["launch_sha256"]=hash;
  report["device_globals"]=nativeDeviceGlobals(build,*report.getArray("symbols"));
}
