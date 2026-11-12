// §5.2 evaluates N23's actual graph before candidate sets freeze. Keeping
// the graph also keeps its alloca identity stable across fixpoint rounds.
AV Analysis::evaluateVarargs(Instruction &i,bool spill) {
  auto &slice=vaTransfers[&i];
  if(!slice)slice.reset(varargsTransfer(i,spill));
  if(!slice->arg_empty())
    changed|=mergeFacts(values[&*slice->arg_begin()],vaBlocks[i.getFunction()]);
  for(auto &v:instructions(*slice))if(!isa<ReturnInst>(v))step(v);
  auto *result=cast<ReturnInst>(slice->back().getTerminator())->getReturnValue();
  return result?get(result):AV{};
}
void Analysis::bindVarargs(CallBase &c,Function &callee) {
  auto *f=&callee;
  if(f->isVarArg()) {
    if(!c.getFunctionType()->isVarArg())
      unimplemented("§5.2 / §14.3 N23 nonvariadic call of variadic definition",2,&c);
    AV block=evaluateVarargs(c,true);
    if(!f->isDeclaration())changed|=mergeFacts(vaBlocks[f],block);
  }
}
// PT12 reaches the spill object as well as pointers stored inside it. This
// includes pointer leaves of aggregate/vector variadic actuals.
void Analysis::varargsReachable(CallBase &c,std::set<const Value *> &reachable) {
  auto transfer=vaTransfers.find(&c);
  if(transfer==vaTransfers.end())return;
  auto *result=cast<ReturnInst>(transfer->second->back().getTerminator())->getReturnValue();
  if(result)for(auto &p:get(result).atoms)if(p.kind==Atom::Ptr && p.object)reachable.insert(p.object);
}
void Analysis::seedVarargs(Function &f) {
  if(f.isVarArg())changed|=mergeFacts(vaBlocks[&f],atom(Atom::Ptr,nullptr,0,-1));
}
bool Analysis::stepVarargs(Instruction &i) {
  if(isVaOperation(i) || (isa<IntrinsicInst>(i) &&
      cast<IntrinsicInst>(i).getIntrinsicID()==Intrinsic::ptrmask)) {
    auto result=evaluateVarargs(i,false);
    auto &slice=vaTransfers.at(&i);
    auto *value=cast<ReturnInst>(slice->back().getTerminator())->getReturnValue();
    if(value && (i.getType()->isAggregateType() || i.getType()->isVectorTy()))copyFields(&i,value);
    else if(value)changed|=mergeFacts(values[&i],result);
    return true;
  }
  return false;
}
// An allocation result summary does not replace N23/PT9 argument or body
// effects. N23's call metadata retains this obligation after its ABI rewrite.
static void bindVaAllocation(CallBase &c,Function &f,function_ref<void()> transfer) {
  if(!f.isDeclaration() && (f.isVarArg() || c.getMetadata("bennett.varargs.fixed"))) { transfer(); }
}
