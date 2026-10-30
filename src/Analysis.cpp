#include "Bennett.h"
#include "llvm/ADT/SmallString.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/IR/PatternMatch.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/IR/Constants.h"
#include "llvm/IR/GlobalAlias.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/IR/Operator.h"
#include "llvm/Support/SHA256.h"
#include "llvm/Support/FormatVariadic.h"
#include "llvm/Transforms/Utils/Cloning.h"
#include "llvm/IR/DebugInfo.h"
#include <numeric>
#include <tuple>
using namespace llvm;
namespace bennett {
static AV atom(Atom::Kind k,const Value *o=nullptr,int64_t off=0,int64_t stride=0) {
 AV a;a.atoms.insert({k,o,off,stride,APInt(1,0)});return a;
}
static AV integer(APInt n) {AV a;a.atoms.insert({Atom::Int,nullptr,0,0,n});return a;}
bool Atom::operator<(const Atom &b)const {
 auto x=std::make_tuple(kind,object,offset,stride,integer.getBitWidth());
 auto y=std::make_tuple(b.kind,b.object,b.offset,b.stride,b.integer.getBitWidth());
 return x<y||(x==y&&integer.ult(b.integer));
}
bool AV::merge(const AV &v) {
 bool change=false;
 if(v.top&&!top){top=true;change=true;}
 for(auto &a:v.atoms)if(!(top&&a.kind==Atom::Int))change|=atoms.insert(a).second;
 unsigned n=0;for(auto &a:atoms)n+=a.kind==Atom::Int;
 if(n>4096){top=true;change=true;}
 if(top)for(auto i=atoms.begin();i!=atoms.end();)if(i->kind==Atom::Int)i=atoms.erase(i);else ++i;
 return change;
}
bool AV::roots()const{for(auto &a:atoms)if(a.kind==Atom::Root)return true;return false;}
Function *resolve(Value *v) {
 if(auto *ga=dyn_cast<GlobalAlias>(v))v=ga->getAliaseeObject();
 auto *f=dyn_cast<Function>(v);if(!f)return nullptr;
 std::set<Function *> seen;
 Function *start=f;
 while(f&&!f->isDeclaration()&&f->size()==1) {
  if(!seen.insert(f).second)return start; // A thunk on a cycle resolves to itself.
  auto &b=f->front();if(b.size()!=2)break;
  auto *c=dyn_cast<CallInst>(&b.front());auto *r=dyn_cast<ReturnInst>(&b.back());
  if(!c||!r||c->getCallingConv()!=CallingConv::C||c->hasOperandBundles()||
     c->getFunctionType()!=f->getFunctionType()||c->arg_size()!=f->arg_size())break;
  if(!f->getReturnType()->isVoidTy()&&r->getReturnValue()!=c)break;
  bool same=true;unsigned i=0;for(Argument &a:f->args())same&=c->getArgOperand(i++)==&a;
  if(!same)break;
  Value *target=c->getCalledOperand();if(auto *ga=dyn_cast<GlobalAlias>(target))target=ga->getAliaseeObject();
  auto *g=dyn_cast<Function>(target);if(!g)break;f=g;
 }
 return f;
}
std::string regionKey(Function *f) {
 // Clone only the direct closure, strip non-semantic names/metadata, and give
 // closure members DFS names. Retain external references such as marker names.
 Module &src=*f->getParent();std::vector<Function *> order;std::set<Function *> seen;
 std::function<void(Function *)> dfs=[&](Function *g){
  g=resolve(g);if(!g||g->isDeclaration()||!seen.insert(g).second)return;order.push_back(g);
  for(Instruction &i:instructions(g))if(auto *c=dyn_cast<CallBase>(&i))if(auto *t=resolve(c->getCalledOperand()))dfs(t);
 };dfs(f);
 ValueToValueMapTy map;auto clone=CloneModule(src,map,[&](const GlobalValue *v){return seen.count(const_cast<Function *>(dyn_cast<Function>(v)));});
 StripDebugInfo(*clone);clone->setModuleIdentifier("");clone->setSourceFileName("");clone->setDataLayout("");
#if LLVM_VERSION_MAJOR >= 23
 clone->setTargetTriple(Triple());
#else
 clone->setTargetTriple("");
#endif

 while(!clone->named_metadata_empty())clone->eraseNamedMetadata(&*clone->named_metadata_begin());
 unsigned n=0;for(auto *g:order){auto *c=cast<Function>(map[g]);c->setName("__canonical_"+std::to_string(n++));}
 n=0;for(auto *g:order){auto *c=cast<Function>(map[g]);c->setName("f"+std::to_string(n++));c->setLinkage(GlobalValue::ExternalLinkage);c->setUnnamedAddr(GlobalValue::UnnamedAddr::None);
  for(Argument &a:c->args())a.setName("");for(BasicBlock &b:*c){b.setName("");for(Instruction &i:b)i.setName("");}}
 // CloneModule retains unrelated declarations. Erase unused declarations/globals.
 bool again=true;while(again){again=false;for(auto i=clone->global_begin();i!=clone->global_end();) {auto &g=*i++;if(g.use_empty()){g.eraseFromParent();again=true;}}
  for(auto i=clone->begin();i!=clone->end();){auto &g=*i++;if(g.isDeclaration()&&g.use_empty()){g.eraseFromParent();again=true;}}}
 std::string text;raw_string_ostream out(text);clone->print(out,nullptr);auto hash=SHA256::hash(arrayRefFromStringRef(text));return toHex(hash,true);
}
AV Analysis::get(const Value *v) {
 if(auto *c=dyn_cast<ConstantInt>(v))return integer(c->getValue());
 if(isa<ConstantPointerNull>(v))return integer(APInt(M.getDataLayout().getPointerSizeInBits(),0));
 if(auto *f=dyn_cast<Function>(v))return atom(Atom::Fn,f);
 if(auto *g=dyn_cast<GlobalVariable>(v))return atom(Atom::Ptr,g);
 if(auto *g=dyn_cast<GlobalAlias>(v))return get(g->getAliasee());
 if(auto *c=dyn_cast<ConstantExpr>(v)) {
  if(c->isCast()) {auto a=get(c->getOperand(0));if(c->getOpcode()==Instruction::IntToPtr&&!a.roots())a.top=true;return a;}
  if(c->getOpcode()==Instruction::GetElementPtr){
   auto *g=cast<GEPOperator>(c);APInt off(M.getDataLayout().getIndexTypeSizeInBits(g->getType()),0);
   auto a=get(c->getOperand(0));if(g->accumulateConstantOffset(M.getDataLayout(),off)){
    AV r;for(auto b:a.atoms){if(b.kind==Atom::Ptr)b.offset+=off.getSExtValue();r.atoms.insert(b);}r.top=a.top;return r;}
  }
  AV a;a.top=true;return a;
 }
 if(isa<UndefValue>(v)||isa<PoisonValue>(v))return integer(APInt(std::max(1u,(unsigned)M.getDataLayout().getTypeSizeInBits(v->getType()).getKnownMinValue()),0));
 return values[v];
}
void Analysis::seed(Constant *c,const Value *obj,int64_t off,Type *t) {
 auto &dl=M.getDataLayout();
 if(t->isStructTy()) {auto *st=cast<StructType>(t);auto *layout=dl.getStructLayout(st);
  for(unsigned i=0;i<st->getNumElements();++i)if(auto *e=c->getAggregateElement(i))seed(e,obj,off+layout->getElementOffset(i),st->getElementType(i));
 }else if(t->isArrayTy()||t->isVectorTy()) {
  Type *et=t->isArrayTy()?t->getArrayElementType():cast<VectorType>(t)->getElementType();
  unsigned count=t->isArrayTy()?t->getArrayNumElements():cast<VectorType>(t)->getElementCount().getKnownMinValue();
  for(unsigned i=0;i<count;++i)if(auto *e=c->getAggregateElement(i))seed(e,obj,off+i*dl.getTypeAllocSize(et).getKnownMinValue(),et);
 }else store(get(c),atom(Atom::Ptr,obj,off),dl.getTypeStoreSize(t).getKnownMinValue());
}
static bool overlaps(const Atom &p,const Slot &s,uint64_t size) {
 if(p.object!=s.object)return false;
 if(p.stride==-1||s.stride==-1)return true;
 if(p.stride==0&&s.stride==0)return p.offset<s.offset+(int64_t)s.bytes&&s.offset<p.offset+(int64_t)size;
 int64_t stride=std::gcd(p.stride,s.stride);if(stride==0)return true;
 // Byte interval overlap, including non-aligned partial reads.
 for(int64_t d=-(int64_t)size+1;d<(int64_t)s.bytes;++d)if((p.offset-s.offset-d)%stride==0)return true;
 return false;
}
void Analysis::store(const AV &v,const AV &p,uint64_t size) {
 for(auto &a:p.atoms)if(a.kind==Atom::Ptr) {
  for(auto &s:slots)if(s.object==a.object&&s.offset==a.offset&&s.stride==a.stride&&s.bytes==size){changed|=s.value.merge(v);goto next;}
  slots.push_back({a.object,a.offset,a.stride,size,v});changed=true;
  next:;
 }
}
AV Analysis::load(const AV &p,Type *t) {
 AV r;uint64_t size=M.getDataLayout().getTypeStoreSize(t).getKnownMinValue();
 r.top=p.top;
 for(auto &a:p.atoms)if(a.kind==Atom::Ptr) {
  if(!a.object){r.top=true;continue;}
  bool partial=false;
  for(auto &s:slots)if(overlaps(a,s,size)) {
   bool exact=a.stride==0&&s.stride==0&&a.offset==s.offset&&size==s.bytes;
   bool sameClass=size==s.bytes&&((a.offset-s.offset)%(int64_t)size==0)&&
     (a.stride==0||a.stride%(int64_t)size==0)&&(s.stride==0||s.stride%(int64_t)size==0);
   if(exact||sameClass)r.merge(s.value);
   else {partial=true;for(auto &b:s.value.atoms)if(b.kind==Atom::Root)r.atoms.insert(b);}
  }
  // Immutable initialiser bytes reconstruct whole integer loads exactly.
  if(auto *g=dyn_cast<GlobalVariable>(a.object);g&&g->isConstant()&&t->isIntegerTy()&&a.stride==0){
   APInt bits(t->getIntegerBitWidth(),0);bool known=true;
   for(unsigned b=0;b<size;++b){bool found=false;for(auto &s:slots)if(s.object==a.object&&s.stride==0&&s.offset<=a.offset+b&&a.offset+b<s.offset+(int64_t)s.bytes&&s.value.atoms.size()==1){
    auto &x=*s.value.atoms.begin();if(x.kind!=Atom::Int)continue;unsigned bi=a.offset+b-s.offset;
    unsigned shift=M.getDataLayout().isLittleEndian()?bi*8:(s.bytes-1-bi)*8;
    uint64_t byte=x.integer.lshr(shift).getLimitedValue()&255;
    unsigned dest=M.getDataLayout().isLittleEndian()?b*8:(size-1-b)*8;
    bits|=APInt(bits.getBitWidth(),byte).shl(dest);found=true;break;
   }known&=found;}
   if(known){r.merge(integer(bits));partial=false;}
  }
  if(partial)r.top=true;
 }
 return r;
}
std::set<Function *> Analysis::candidates(Value *v,FunctionType *type) {
 AV a=get(v);std::set<Function *> r;
 for(auto &x:a.atoms)if(x.kind==Atom::Fn)if(auto *f=resolve(const_cast<Value *>(x.object)))r.insert(f);
 bool top=a.top;for(auto &x:a.atoms)top|=x.kind==Atom::Ptr;
 if(top)for(Function &f:M)if(f.hasAddressTaken()&&(!type||f.getFunctionType()==type)&&!markers().count(f.getName().str()))r.insert(resolve(&f));
 return r;
}
void Analysis::bind(CallBase &c,Function *f) {
 if(!f||f->isDeclaration())return;
 edges[c.getFunction()].insert(f);
 unsigned i=0;for(Argument &a:f->args()){if(i<c.arg_size())changed|=values[&a].merge(get(c.getArgOperand(i)));++i;}
 for(BasicBlock &b:*f)if(auto *r=dyn_cast<ReturnInst>(b.getTerminator()))if(r->getReturnValue())changed|=values[&c].merge(get(r->getReturnValue()));
}
static bool allocation(const Function *f) {
 if(!f)return false;
 static const std::set<std::string> names={"malloc","calloc","realloc","aligned_alloc","posix_memalign","memalign","strdup","strndup","_Znwm","_Znam","_ZnwmRKSt9nothrow_t","_ZnamRKSt9nothrow_t","_ZnwmSt11align_val_t","_ZnamSt11align_val_t","__rust_alloc","__rust_alloc_zeroed","__rust_realloc","julia.gc_alloc_obj","ijl_gc_alloc_typed","jl_gc_alloc","ijl_gc_small_alloc","ijl_gc_big_alloc","__bennett_nz_alloc"};
 return names.count(f->getName().str())||f->hasFnAttribute(Attribute::AllocSize)||f->hasFnAttribute(Attribute::AllocKind);
}
void Analysis::step(Instruction &i) {
 AV a;
 if(isa<AllocaInst>(i))a=atom(Atom::Ptr,&i);
 else if(auto *g=dyn_cast<GetElementPtrInst>(&i)) {
  auto base=get(g->getPointerOperand());
  unsigned bits=M.getDataLayout().getIndexTypeSizeInBits(g->getType());
  #if LLVM_VERSION_MAJOR >= 23
  SmallMapVector<Value *,APInt,4> vars;
#else
  MapVector<Value *,APInt> vars;
#endif
APInt off(bits,0);
  if(!g->collectOffset(M.getDataLayout(),bits,vars,off))unimplemented("§5 PT2 GEP offset",2,g);
  a=base;
  for(auto &entry:vars) {
   AV r;auto indices=get(entry.first);
   for(auto p:a.atoms)if(p.kind==Atom::Ptr){
    if(indices.top){p.stride=p.stride==-1?-1:std::gcd(p.stride,std::abs(entry.second.getSExtValue()));if(p.stride==1)p.stride=-1;r.atoms.insert(p);}
    for(auto &v:indices.atoms)if(v.kind==Atom::Int){auto q=p;q.offset+=(v.integer.sextOrTrunc(bits)*entry.second).getSExtValue();r.atoms.insert(q);}
   }r.top=a.top;a=r;
  }
  AV r;for(auto p:a.atoms){if(p.kind==Atom::Ptr)p.offset+=off.getSExtValue();r.atoms.insert(p);}r.top=a.top;a=r;
 }else if(auto *l=dyn_cast<LoadInst>(&i))a=load(get(l->getPointerOperand()),l->getType());
 else if(auto *s=dyn_cast<StoreInst>(&i)) {
  if(s->getValueOperand()->getType()->isAggregateType()||s->getValueOperand()->getType()->isVectorTy())unimplemented("§5 PT7 aggregate/vector memory",2,s);
  store(get(s->getValueOperand()),get(s->getPointerOperand()),M.getDataLayout().getTypeStoreSize(s->getValueOperand()->getType()).getKnownMinValue());
 }else if(auto *p=dyn_cast<PHINode>(&i))for(Value *v:p->incoming_values())a.merge(get(v));
 else if(auto *s=dyn_cast<SelectInst>(&i)){a=get(s->getTrueValue());a.merge(get(s->getFalseValue()));}
 else if(auto *c=dyn_cast<CastInst>(&i)) {
  a=get(c->getOperand(0));
  if(c->getOpcode()==Instruction::IntToPtr) {
   bool hasFn=false;for(auto &x:a.atoms)hasFn|=x.kind==Atom::Fn;
   if(!a.roots()&&!hasFn){a.top=true;a.merge(atom(Atom::Ptr));}
  } else if(c->getType()->isIntegerTy()) {
   AV r;r.top=a.top;for(auto x:a.atoms){if(x.kind==Atom::Int){unsigned w=c->getType()->getIntegerBitWidth();x.integer=c->getOpcode()==Instruction::SExt?x.integer.sextOrTrunc(w):x.integer.zextOrTrunc(w);}r.atoms.insert(x);}a=r;
  }
 }else if(isa<FreezeInst>(i))a=get(i.getOperand(0));
 else if(auto *c=dyn_cast<CallBase>(&i)) {
  Function *f=resolve(c->getCalledOperand());StringRef n=f?f->getName():StringRef();
  if(n=="__bennett_qalloc"||n=="__bennett_qborrow")a=atom(Atom::Root,c);
  else if(auto *mem=dyn_cast<MemTransferInst>(c)) {
   AV src=get(mem->getSource()),dst=get(mem->getDest());auto *len=dyn_cast<ConstantInt>(mem->getLength());
   auto snapshot=slots;
   for(auto s:snapshot)for(auto &p:src.atoms)if(p.kind==Atom::Ptr&&p.object==s.object)for(auto &d:dst.atoms)if(d.kind==Atom::Ptr){
    if(len&&p.stride==0&&d.stride==0&&s.stride==0&&s.offset>=p.offset&&s.offset+(int64_t)s.bytes<=p.offset+(int64_t)len->getZExtValue())store(s.value,atom(Atom::Ptr,d.object,d.offset+s.offset-p.offset),s.bytes);
    else if(!len||overlaps(p,s,len->getZExtValue())){AV partial;partial.top=true;for(auto &x:s.value.atoms)if(x.kind==Atom::Root)partial.atoms.insert(x);store(partial,atom(Atom::Ptr,d.object,d.offset,-1),s.bytes);}
   }
  }else if(isa<MemSetInst>(c))unimplemented("§5 PT8 byte fills",2,c);
  else if(allocation(f)){a=atom(Atom::Ptr,c);if(n=="posix_memalign"){store(a,get(c->getArgOperand(0)),M.getDataLayout().getPointerSize());a.top=true;}}
  else if(f&&!f->isDeclaration())bind(*c,f);
  else if(!f) {for(auto *g:candidates(c->getCalledOperand(),c->getFunctionType()))bind(*c,g);}
  else if(!markers().count(n.str())&&!f->isIntrinsic()) {
   a.top=true;
   for(Value *v:c->args())for(auto &p:get(v).atoms)if(p.kind==Atom::Ptr) {
    AV top;top.top=true;store(top,atom(Atom::Ptr,p.object,0,-1),1);
   }
  }
  if(f&&markers().count(n.str()))for(unsigned pos:regionOperands(n)) {
   bool oracle=n=="__bennett_oracle"||n=="__bennett_inplace";
   auto *rt=FunctionType::get(Type::getVoidTy(M.getContext()),{PointerType::get(M.getContext(),0)},false);
   for(auto *g:candidates(c->getArgOperand(pos),oracle?nullptr:rt))if(!g->isDeclaration()) {
    // Region edges bind env, but do not inherit the caller tier.
    if(!oracle&&g->arg_size()==1)changed|=values[&*g->arg_begin()].merge(get(c->getArgOperand(c->arg_size()-1)));
   }
  }
 }else if(isa<BinaryOperator>(i)||isa<ICmpInst>(i)) {
  AV x=get(i.getOperand(0)),y=get(i.getOperand(1));
  if((x.top||y.top)&&i.getOpcode()==Instruction::And) {
   auto *mask=dyn_cast<ConstantInt>(i.getOperand(1));if(!mask)mask=dyn_cast<ConstantInt>(i.getOperand(0));
   if(mask&&mask->getValue().popcount()<=12){auto m=mask->getValue();APInt sub=m;do{a.merge(integer(sub));if(sub.isZero())break;sub=(sub-1)&m;}while(true);}
   else a.top=true;
  }else if(x.top&&i.getOpcode()==Instruction::URem&&isa<ConstantInt>(i.getOperand(1))&&cast<ConstantInt>(i.getOperand(1))->getValue().ule(4096)&&!cast<ConstantInt>(i.getOperand(1))->isZero()) {
   auto *m=cast<ConstantInt>(i.getOperand(1));for(unsigned k=0;k<m->getZExtValue();++k)a.merge(integer(APInt(m->getBitWidth(),k)));
  }else {
   a.top=x.top||y.top;
   for(auto &v:x.atoms)for(auto &w:y.atoms) {
    if(v.kind==Atom::Int&&w.kind==Atom::Int&&v.integer.getBitWidth()==w.integer.getBitWidth()) {
     APInt b=v.integer,c=w.integer,r=b;bool valid=true;
     switch(i.getOpcode()) {
      case Instruction::Add:r=b+c;break;case Instruction::Sub:r=b-c;break;case Instruction::Mul:r=b*c;break;
      case Instruction::And:r=b&c;break;case Instruction::Or:r=b|c;break;case Instruction::Xor:r=b^c;break;
      case Instruction::Shl:r=c.uge(b.getBitWidth())?APInt(b.getBitWidth(),0):b.shl(c);break;
      case Instruction::LShr:r=c.uge(b.getBitWidth())?APInt(b.getBitWidth(),0):b.lshr(c);break;
      case Instruction::AShr:r=c.uge(b.getBitWidth())?APInt(b.getBitWidth(),0):b.ashr(c);break;
      case Instruction::UDiv:case Instruction::SDiv:case Instruction::URem:case Instruction::SRem:
       if(c.isZero()){valid=false;break;}r=i.getOpcode()==Instruction::UDiv?b.udiv(c):i.getOpcode()==Instruction::SDiv?b.sdiv(c):i.getOpcode()==Instruction::URem?b.urem(c):b.srem(c);break;
      case Instruction::ICmp:r=APInt(1,ICmpInst::compare(b,c,cast<ICmpInst>(i).getPredicate()));break;
      default:valid=false;
     }
     if(valid)a.merge(integer(r));if(a.top)goto done;
    }else if(v.kind==Atom::Ptr) {auto p=v;
     if(w.kind==Atom::Int&&(i.getOpcode()==Instruction::Add||i.getOpcode()==Instruction::Sub))p.offset+=(i.getOpcode()==Instruction::Add?1:-1)*w.integer.getSExtValue();else p.stride=-1;a.atoms.insert(p);
    }
   }
  }
  done:;
 }else if(i.getType()->isVectorTy()||i.getType()->isAggregateType())unimplemented("§5 PT10 vector/aggregate lanes",2,&i);
 changed|=values[&i].merge(a);
}
void Analysis::run() {
 for(GlobalVariable &g:M.globals())if(g.hasInitializer())seed(g.getInitializer(),&g,0,g.getValueType());
 for(Function &f:M)if(!f.isDeclaration()&&(!f.hasLocalLinkage()||f.hasAddressTaken()))for(Argument &a:f.args()) {
  if(a.getType()->isPointerTy()){values[&a].merge(atom(Atom::Ptr));values[&a].merge(atom(Atom::Root,&a));}
  else values[&a].top=true;
 }
 unsigned rounds=0;
 do{changed=false;for(Function &f:M)for(Instruction &i:instructions(f))step(i);
  if(++rounds>16384)unimplemented("§5 fixpoint resource exhaustion",1);
 }while(changed);
 // Candidate entry roots that never reach a handle operand are removed (§6.6).
 std::set<const Value *> live;
 for(Function &f:M)for(Instruction &i:instructions(f))if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=c->getCalledFunction())
  for(unsigned p:handleOperands(g->getName()))for(auto &x:get(c->getArgOperand(p)).atoms)if(x.kind==Atom::Root)live.insert(x.object);
 auto prune=[&](AV &v){for(auto it=v.atoms.begin();it!=v.atoms.end();)if(it->kind==Atom::Root&&isa<Argument>(it->object)&&!live.count(it->object))it=v.atoms.erase(it);else ++it;};
 for(auto &e:values)prune(e.second);for(auto &s:slots)prune(s.value);
 // Tiers and graph are derived from the same fixed candidate/ROOT solution.
 std::map<Function *,std::set<Function *>> full=edges;
 for(Function &f:M)if(!f.isDeclaration()) {
  if(!f.hasLocalLinkage())tiers[&f].insert("H");
  for(Argument &a:f.args())if(get(&a).roots())tiers[&f].insert("CC");
  for(Instruction &i:instructions(f)) {
   if(auto *l=dyn_cast<LoadInst>(&i);l&&get(l).roots())tiers[&f].insert("CC");
   if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=c->getCalledFunction();g&&markers().count(g->getName().str())) {
    tiers[&f].insert("CC");auto n=g->getName();
    for(unsigned p:regionOperands(n))for(auto *r:candidates(c->getArgOperand(p))) {
     full[&f].insert(r);tiers[r].insert(n=="__bennett_oracle"||n=="__bennett_inplace"?"L":n=="__bennett_reversible"?"R":"CC");
    }
   }
  }
 }
 bool more=true;while(more){more=false;for(auto &e:edges)for(auto *f:e.second)for(auto &t:tiers[e.first])more|=tiers[f].insert(t).second;}
 // §3.8 source-effect lies, including indirect and region edges.
 std::set<Function *> reaches;for(Function &f:M)for(Instruction &i:instructions(f))if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=c->getCalledFunction();g&&markers().count(g->getName().str()))reaches.insert(&f);
 more=true;while(more){more=false;for(auto &e:full)for(auto *g:e.second)if(reaches.count(g))more|=reaches.insert(e.first).second;}
 for(Function &f:M)if(reaches.count(&f)&&(f.onlyReadsMemory()||f.hasFnAttribute(Attribute::WillReturn)||f.hasFnAttribute(Attribute::Speculatable)))fail("BD-E-EFFECT-LIE","§3.8",&f);
}
void Analysis::checkHandles() {
 unsigned pw=M.getDataLayout().getPointerSizeInBits();
 for(Function &f:M)for(Instruction &i:instructions(f)) {
  for(unsigned k=0;k<i.getNumOperands();++k) {
   Value *v=i.getOperand(k);if(!get(v).roots())continue;bool good=false;
   if(isa<PHINode>(i)||isa<FreezeInst>(i)||isa<ReturnInst>(i))good=true;
   if(isa<SelectInst>(i))good=k!=0;
   if(auto *c=dyn_cast<CastInst>(&i))good=(c->getOpcode()==Instruction::PtrToInt&&c->getType()->isIntegerTy(pw))||
    (c->getOpcode()==Instruction::IntToPtr&&c->getOperand(0)->getType()->isIntegerTy(pw))||
    (c->getOpcode()==Instruction::BitCast&&M.getDataLayout().getTypeSizeInBits(c->getType())==pw);
   if(auto *cmp=dyn_cast<ICmpInst>(&i))good=cmp->isEquality()&&(get(cmp->getOperand(1-k)).roots()||isa<ConstantPointerNull>(cmp->getOperand(1-k))||PatternMatch::match(cmp->getOperand(1-k),PatternMatch::m_Zero()));
   if(auto *s=dyn_cast<StoreInst>(&i))good=k==0;
   if(auto *c=dyn_cast<CallBase>(&i)) {
    Function *g=resolve(c->getCalledOperand());
    good=g&&!g->isDeclaration()&&k<c->arg_size();
    if(g&&markers().count(g->getName().str()))for(unsigned p:handleOperands(g->getName()))good|=k==p;
    if(!good&&g&&g->isDeclaration()&&!markers().count(g->getName().str()))fail("BD-E-HANDLE-ESCAPE","§6.4 external argument",c);
   }
   if(!good)fail("BD-E-HANDLE-USE","§6.2",&i);
  }
  if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=c->getCalledFunction())for(unsigned p:handleOperands(g->getName()))if(!get(c->getArgOperand(p)).roots())fail("BD-E-HANDLE-UNTRACKED","§6.2",c);
  if(auto *l=dyn_cast<LoadInst>(&i);l&&get(l).roots()) {
   if(!l->getType()->isPointerTy()&&!l->getType()->isIntegerTy(pw))fail("BD-E-HANDLE-USE","§6.2 partial handle read",l);
   auto p=get(l->getPointerOperand());for(auto &x:p.atoms)for(auto &s:slots)if(s.value.roots()&&overlaps(x,s,M.getDataLayout().getTypeStoreSize(l->getType()).getKnownMinValue()))
    if(s.bytes!=pw/8||(x.stride==0&&s.stride==0&&x.offset!=s.offset))fail("BD-E-HANDLE-USE","§6.2 overlapping read",l);
  }
  if(auto *r=dyn_cast<ReturnInst>(&i);r&&r->getReturnValue()&&get(r->getReturnValue()).roots()&&!f.hasLocalLinkage())fail("BD-E-HANDLE-ESCAPE","§6.4 exported return",r);
 }
 for(auto &s:slots)if(!s.object&&s.value.roots())fail("BD-E-HANDLE-ESCAPE","§6.4 EXT slot");
 // Reachable pointee slots crossing opaque calls are also escapes.
 for(Function &f:M)for(Instruction &i:instructions(f))if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=c->getCalledFunction();g&&g->isDeclaration()&&!g->isIntrinsic()&&!markers().count(g->getName().str()))
  for(Value *v:c->args()) {std::set<const Value *> objects;for(auto &p:get(v).atoms)if(p.kind==Atom::Ptr)objects.insert(p.object);
   bool more=true;while(more){more=false;for(auto &s:slots)if(objects.count(s.object)){if(s.value.roots())fail("BD-E-HANDLE-ESCAPE","§6.4 external reachable slot",c);for(auto &p:s.value.atoms)if(p.kind==Atom::Ptr)more|=objects.insert(p.object).second;}}
  }
}
void Analysis::checkRegions() {
 bool defer=false;if(auto *md=dyn_cast_or_null<MDString>(M.getModuleFlag("bennett.measure_in_unitary")))defer=md->getString()=="defer";
 for(Function &f:M)for(Instruction &i:instructions(f))if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=c->getCalledFunction())for(unsigned p:regionOperands(g->getName())) {
  auto rr=candidates(c->getArgOperand(p));if(rr.size()!=1)continue;auto *r=*rr.begin();
  if(g->getName()=="__bennett_oracle"||g->getName()=="__bennett_inplace")continue;
  auto *rt=FunctionType::get(Type::getVoidTy(M.getContext()),{PointerType::get(M.getContext(),0)},false);
  if(r->getFunctionType()!=rt)fail("BD-E-REGION-TYPE","§7.2",c);
  std::set<Function *> seen;std::vector<Function *> todo={r};
  while(!todo.empty()){auto *h=todo.back();todo.pop_back();if(!seen.insert(h).second)continue;
   for(Instruction &j:instructions(h))if(auto *cb=dyn_cast<CallBase>(&j))if(auto *called=cb->getCalledFunction();called&&called->getName()=="__bennett_measure") {
    if(g->getName()=="__bennett_reversible")fail("BD-E-REVERSIBLE-MEASURE","§7.5(b)",cb);
    if(!defer)fail("BD-E-REGION-MEASURE","§7.5(a)",cb);
   }
   for(auto *next:edges[h])todo.push_back(next);
  }
 }
}
static std::string label(const Value *v) {std::string s;raw_string_ostream o(s);v->printAsOperand(o,false);return s;}
json::Object Analysis::report() {
 json::Array funcs,regions,vals;
 for(Function &f:M)if(!f.isDeclaration()) {
  json::Array ts,es;for(auto &t:tiers[&f])ts.push_back(t);for(auto *g:edges[&f])es.push_back(g->getName().str());
  funcs.push_back(json::Object{{"name",f.getName().str()},{"tiers",std::move(ts)},{"callees",std::move(es)}});
  for(Instruction &i:instructions(f)) {
   AV a=get(&i);if(!i.getType()->isVoidTy()){json::Array atoms;
    for(auto &x:a.atoms){if(x.kind==Atom::Int){SmallString<40> s;x.integer.toString(s,10,false);atoms.push_back("INT("+s.str().str()+")");}
     else atoms.push_back(std::string(x.kind==Atom::Root?"ROOT(":x.kind==Atom::Fn?"FN(":"PTR(")+(x.object?label(x.object):"EXT")+","+std::to_string(x.offset)+","+std::to_string(x.stride)+")");}
    vals.push_back(json::Object{{"function",f.getName().str()},{"value",label(&i)},{"top",a.top},{"atoms",std::move(atoms)}});
   }
   if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=c->getCalledFunction())for(unsigned p:regionOperands(g->getName())) {
    json::Array rr;for(auto *r:candidates(c->getArgOperand(p)))rr.push_back(json::Object{{"name",r->getName().str()},{"key",r->isDeclaration()?"external":regionKey(r)}});
    regions.push_back(json::Object{{"function",f.getName().str()},{"marker",g->getName().str()},{"operand",(int64_t)p},{"candidates",std::move(rr)}});
   }
  }
 }
 return json::Object{{"dialect","0.2.6"},{"isa","0.8"},{"mode","analysis-only"},{"functions",std::move(funcs)},{"regions",std::move(regions)},{"values",std::move(vals)}};
}
}
