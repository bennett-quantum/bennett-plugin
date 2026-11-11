// Materialise runtime constant expressions before the ordinary instruction
// lowerers. Keep globals/initialisers symbolic until the comparison link fixes
// addresses; no host address or early comparison result enters this pass.
class ConstantOperands {
  std::map<Instruction *,std::map<Constant *,Value *>> caches;

  bool needsInstruction(Constant *constant) {
    if(isa<GlobalAlias>(constant))return true;
    if(auto *expression=dyn_cast<ConstantExpr>(constant)) {
      if(expression->getOpcode()!=Instruction::GetElementPtr)return true;
    } else if(!isa<ConstantAggregate>(constant))return false;
    for(auto &operand:constant->operands())
      if(needsInstruction(cast<Constant>(operand)))return true;
    return false;
  }

  Value *materialise(Constant *constant, Instruction *before) {
    if(auto *alias=dyn_cast<GlobalAlias>(constant))return materialise(alias->getAliasee(),before);
    if(!isa<ConstantExpr>(constant) && !isa<ConstantAggregate>(constant))return constant;
    auto &cache=caches[before];auto found=cache.find(constant);
    if(found!=cache.end())return found->second;
    SmallVector<Value *> operands;bool changed=false;
    for(auto &operand:constant->operands()) {
      auto *value=materialise(cast<Constant>(operand),before);
      operands.push_back(value);changed|=value!=operand.get();
    }
    if(auto *expression=dyn_cast<ConstantExpr>(constant)) {
      // Existing GEP lowering already preserves relocation identities and
      // object bytes. Only expand it when a nested expression was expanded.
      if(!changed && expression->getOpcode()==Instruction::GetElementPtr)return constant;
      auto *instruction=expression->getAsInstruction();
      for(unsigned k=0;k<operands.size();++k)instruction->setOperand(k,operands[k]);
      if(expression->isCast() || expression->getOpcode()==Instruction::GetElementPtr)
        instruction->setMetadata("bennett.constant.operand",MDNode::get(instruction->getContext(),ConstantAsMetadata::get(expression)));
      instruction->insertInto(before->getParent(),before->getIterator());
      cache[constant]=instruction;return instruction;
    }
    if(!changed)return constant;
    IRBuilder<NoFolder> builder(before);Value *aggregate=PoisonValue::get(constant->getType());
    for(unsigned k=0;k<operands.size();++k) {
      if(constant->getType()->isVectorTy())aggregate=builder.CreateInsertElement(aggregate,operands[k],builder.getInt32(k));
      else aggregate=builder.CreateInsertValue(aggregate,operands[k],{k});
    }
    cache[constant]=aggregate;return aggregate;
  }

public:
  void run(Function &function) {
    SmallVector<WeakTrackingVH> users;
    for(auto &instruction:instructions(function))users.emplace_back(&instruction);
    for(auto &handle:users) {
      auto *user=dyn_cast_or_null<Instruction>(static_cast<Value *>(handle));
      // EH clauses are constant descriptors, not runtime operand evaluation.
      if(!user || isa<LandingPadInst>(user))continue;
      for(unsigned k=0;k<user->getNumOperands();++k) {
        auto *constant=dyn_cast<Constant>(user->getOperand(k));
        if(!constant || !needsInstruction(constant))continue;
        Instruction *before=user;
        if(auto *phi=dyn_cast<PHINode>(user)) {
          auto *predecessor=phi->getIncomingBlock(k);
          // Preserve edge-only evaluation, even for expressions which may
          // trap. All PHIs on this edge then share the new insertion point.
          if(predecessor->getTerminator()->getNumSuccessors()>1)
            predecessor=SplitEdge(predecessor,phi->getParent());
          before=predecessor->getTerminator();
        }
        user->setOperand(k,materialise(constant,before));
      }
    }
  }
};
