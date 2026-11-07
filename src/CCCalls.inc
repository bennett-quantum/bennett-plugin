// ISA 0.8 §9.2: full CC memory envelopes and recursive SCC identities.
void linkCCCalls(Entry &e, const std::map<std::string,std::string> &sections,
                 json::Object &signature, const std::string &body,
                 std::map<std::string,std::string> &hashes, json::Object &symbols,
                 std::string &bodies) {
  auto functions=e.ccFunctions;
  for(auto &item:e.snapshotFunctions)functions.insert(item);
  auto entry=e.f.getName().str();
  auto sigText=jcs(json::Value(std::move(signature)));
  auto sigCopy=parse(sigText);signature=std::move(*sigCopy.getAsObject());
  functions[entry]={sigText,body};
  std::regex token(R"(@([A-Za-z_][A-Za-z_0-9]*))");
  std::map<std::string,std::set<std::string>> edges;
  for(auto &fn:functions) {
    auto rest=fn.second.second.substr(fn.second.second.find('\n')+1);
    for(std::sregex_iterator it(rest.begin(),rest.end(),token),end;it!=end;++it)
      if(functions.count((*it)[1]))edges[fn.first].insert((*it)[1]);
  }
  auto reaches=[&](std::string from,std::string to) {
    std::set<std::string> seen;
    std::function<bool(std::string)> walk=[&](std::string n) {
      if(n==to)return true;if(!seen.insert(n).second)return false;
      for(auto &v:edges[n])if(walk(v))return true;return false;
    };return walk(from);
  };
  std::string memory;
  if(sections.count("data")) {
    SmallVector<StringRef> lines;StringRef(sections.at("data")).split(lines,'\n');
    for(auto line:lines)memory+="data "+line.str()+"\n";
  }
  if(sections.count("layout")) {
    auto layout=parse(sections.at("layout"));std::map<std::string,std::string> leaves;
    for(auto &v:*layout.getAsObject()) {
      if(v.first=="globals")for(auto &g:*v.second.getAsObject())leaves["globals."+g.first.str()]=jcs(g.second);
      else if(v.first=="interface_regions")for(auto &o:*v.second.getAsObject())for(auto &r:*o.second.getAsObject())leaves["interface_regions."+o.first.str()+"."+r.first.str()]=jcs(r.second);
      else leaves[v.first.str()]=jcs(v.second);
    }
    for(auto &leaf:leaves)memory+="layout "+leaf.first+" "+leaf.second+"\n";
  }
  std::function<void(std::string)> visit=[&](std::string name) {
    if(hashes.count(name))return;
    std::vector<std::string> group;
    for(auto &fn:functions)if(reaches(name,fn.first)&&reaches(fn.first,name))group.push_back(fn.first);
    std::set<std::string> inside(group.begin(),group.end());
    bool cyclic=group.size()>1 || edges[name].count(name);
    for(auto &n:group)for(auto &edge:edges[n])if(!inside.count(edge))visit(edge);
    std::string envelopes;
    for(auto &n:group) {
      auto &fn=functions.at(n);auto nl=fn.second.find('\n');
      auto rest=fn.second.substr(nl+1);std::string canonical=fn.second.substr(0,nl+1),refs;
      size_t last=0;std::set<std::string> seen;
      for(std::sregex_iterator it(rest.begin(),rest.end(),token),end;it!=end;++it) {
        auto target=(*it)[1].str();std::string replacement;
        if(cyclic && inside.count(target))replacement="$"+std::to_string(std::find(group.begin(),group.end(),target)-group.begin());
        else {
          if(!hashes.count(target))fail("output","unresolved CC callee "+target,&e.f);
          replacement=hashes.at(target);if(seen.insert(target).second)refs+=replacement+"\n";
        }
        canonical+=rest.substr(last,it->position()-last)+"@"+replacement;last=it->position()+it->length();
      }
      canonical+=rest.substr(last);
      std::string devices;
      if(sections.count("devices")) {
        auto document=parse(sections.at("devices"));std::set<std::string> used;
        std::regex effect(R"(effect ([a-z]+)\.)"),service(R"(hostcall ([A-Za-z_0-9./]+) )");
        for(std::sregex_iterator it(rest.begin(),rest.end(),effect),end;it!=end;++it)used.insert((*it)[1]);
        for(std::sregex_iterator it(rest.begin(),rest.end(),service),end;it!=end;++it)used.insert((*it)[1]);
        for(auto &device:used)for(auto category:{"models","services"})
          if(auto *entries=document.getAsObject()->getObject(category))if(auto *value=entries->get(device))devices+="device "+device+" "+jcs(*value)+"\n";
      }
      envelopes+="isa="+producerISA()+"\nptr_width="+std::to_string(e.m.getDataLayout().getPointerSizeInBits())+"\n"+fn.first+"\n"+canonical+"\n"+memory+devices+refs;
    }
    auto digest=hash(envelopes);
    for(unsigned i=0;i<group.size();++i)hashes[group[i]]=cyclic?hash(digest+":"+std::to_string(i)):digest;
  };
  for(auto &fn:functions)visit(fn.first);
  for(auto &fn:functions)if(fn.first!=entry) {
    auto sig=parse(fn.second.first);auto kind=sig.getAsObject()->getString("kind")->str();
    symbols[std::to_string(symbols.size())]=json::Object{{"name",fn.first},{"kind",kind},{"signature",std::move(sig)},{"interface_hash",hashes.at(fn.first)}};
    bodies+="\n"+fn.second.second;
  }
}
