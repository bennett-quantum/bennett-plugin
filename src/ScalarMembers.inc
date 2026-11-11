struct ScalarMembers {
  std::map<std::string,std::string> bodies, signatures;
  std::string text;
};
ScalarMembers scalarMembers(Scalar &s, const std::vector<Function *> &closure,
                            Analysis &analysis, const std::map<Function *,std::string> &functions) {
  auto &m = s.m;
  ScalarMembers members;
  for(auto *g:closure) {
    Scalar member{m,*g};member.globals=s.globals;member.functions=functions;member.analysis=&analysis;
    auto name=functions.at(g);members.bodies[name]=member.body();
    std::vector<std::string> widths;for(auto &a:g->args())for(auto &field:member.fields(a.getType()))widths.push_back(std::to_string(member.width(field.type)));
    members.signatures[name]="{\"abi\":\""+producerISA()+"\",\"kind\":\"lproc\",\"params\":["+join(widths,",")+"],\"result\":"+std::to_string(member.width(g->getReturnType()))+",\"tier\":\"q\"}";
    if(rContractProfile()) {
      auto signature=json::parse(members.signatures[name]);auto &object=*signature->getAsObject();
      object["args"]=json::Array{};object["mem"]=json::Array{};object["tokens"]=json::Array{};
      members.signatures[name]=canonicalJSON(*signature);
    }
    if(!members.text.empty())members.text+="\n";members.text+=members.bodies[name];
  }
  return members;
}
