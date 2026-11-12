#!/usr/bin/env python3
"""Exact AV copies share storage; growing facts detach and intern by content."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from contracts import ROOT, run

PROBE = r'''
#include "Bennett.h"
#include "AnalysisAtomSet.h"
#include "llvm/AsmParser/Parser.h"
#include "llvm/IR/LLVMContext.h"
#include "llvm/IR/ValueSymbolTable.h"
#include "llvm/Support/SourceMgr.h"
#include <iostream>
using namespace llvm;
using namespace bennett;
static Atom number(unsigned n) { return {Atom::Int,nullptr,0,0,APInt(64,n)}; }
static bool sameNodes(const AV &a,const AV &b) {
  return a.atoms.size()==b.atoms.size() && !a.atoms.empty() &&
         &*a.atoms.begin()==&*b.atoms.begin();
}
static int failTest(const char *message) { std::cerr<<message<<'\n';return 1; }
int main(int argc,char **argv) {
  std::string mode=argv[1];
  if(mode=="copy") {
    AV a;for(unsigned i=0;i<16;++i)a.atoms.insert(number(i));
    AV b=a;if(!sameNodes(a,b))return failTest("AV copy cloned the atom nodes");
    auto duplicate=b.atoms.insert(number(4));
    if(duplicate.second || !sameNodes(a,b))return failTest("duplicate insertion detached");
    b.atoms.insert(b.atoms.end(),number(20));
    if(a.atoms.count(number(20)) || sameNodes(a,b))return failTest("hint insertion mutated shared source");
    AV c=a;auto next=c.atoms.erase(c.atoms.find(number(4)));
    if(next==c.atoms.end() || next->integer!=5 || !a.atoms.count(number(4)) || c.atoms.count(number(4)))
      return failTest("shared erase lost iterator position or changed source");
    AV d=a;if(d.atoms.erase(number(99)) || !sameNodes(a,d))return failTest("missing erase detached");
    d.atoms.clear();if(!d.atoms.empty() || a.atoms.size()!=16)return failTest("clear changed shared source");
    AV e;e.atoms.insert(e.atoms.end(),number(1));
    if(e.atoms.size()!=1)return failTest("empty hinted insertion failed");
    return 0;
  }
  LLVMContext context;SMDiagnostic error;
  std::string ir="target datalayout = \"e-p:64:64\"\n@slot0 = internal global ptr null\n@slot1 = internal global ptr null\n";
  for(unsigned i=0;i<16;++i)ir+="@t"+std::to_string(i)+" = internal global i8 0\n";
  ir+="@table = internal constant [16 x ptr] [";
  for(unsigned i=0;i<16;++i)ir+=(i?", ":"")+std::string("ptr @t")+std::to_string(i);
  ir+="]\ndefine internal ptr @sink(ptr %arg) { ret ptr %arg }\n"
      "define internal void @pair_sink({ptr,ptr} %arg) { ret void }\n"
      "define ptr @top(i64 %arg) {\n"
      " %index = and i64 %arg, 15\n %address = getelementptr ptr, ptr @table, i64 %index\n"
      " %set = load ptr, ptr %address\n %copy = freeze ptr %set\n"
      " store ptr %copy, ptr @slot0\n store ptr %set, ptr @slot1\n"
      " %call = call ptr @sink(ptr %copy)\n"
      " %first = insertvalue {ptr,ptr} poison, ptr %set, 0\n"
      " %pair = insertvalue {ptr,ptr} %first, ptr %set, 1\n"
      " call void @pair_sink({ptr,ptr} %pair)\n ret ptr %call\n}\n";
  auto module=parseAssemblyString(ir,error,context);
  if(!module){error.print("sharing-probe",errs());return 1;}
  if(mode=="merge") {
    auto *object=module->getGlobalVariable("t0",true);
    AV a;
    a.atoms.insert({Atom::Ptr,object,4,0,APInt(1,0)});
    a.atoms.insert({Atom::Ptr,object,7,1,APInt(1,0)});
    a.atoms.insert({Atom::Root,object,0,0,APInt(1,0)});
    a.atoms.insert(number(9));
    if(a.atoms.isNormalized())return failTest("raw insert retained union proof");
    AV b=a;b.top=true;
    if(!a.merge(b) || !a.top || a.atoms.size()!=2)
      return failTest("shared merge omitted canonicalisation or TOP absorption");
    auto pointer=a.atoms.begin();
    if(pointer->kind!=Atom::Ptr || pointer->offset || pointer->stride!=-1)
      return failTest("shared noncanonical pointer was skipped");
    if(b.atoms.size()!=4 || a.merge(b))
      return failTest("shared merge changed its source or repeated growth");
    AV normal;normal.merge(a);
    if(!normal.atoms.isNormalized())return failTest("union lost its normalisation proof");
    AV copied;copied.merge(normal);
    if(!sameNodes(normal,copied))return failTest("normalised union rebuilt immutable nodes");
    auto saved=normal;
    normal.atoms.insert(number(11));
    if(normal.atoms.isNormalized() || !saved.atoms.isNormalized())
      return failTest("mutation did not revoke only the mutated view's proof");
    AV singleton;singleton.merge(AV{{number(1)},false});
    if(!singleton.atoms.isNormalized())return failTest("finite INT union not normalised");
    singleton.top=true;
    AV absorbed;absorbed.merge(singleton);
    if(!absorbed.top || !absorbed.atoms.empty())return failTest("normalised TOP kept integers");
    return 0;
  }
  if(mode=="interner") {
    AnalysisAtomSetInterner<Atom> pool;
    Atom marker{Atom::Ptr,module->getGlobalVariable("t0",true),0,0,APInt(64,0)};
    auto make=[&](Atom value) { AnalysisAtomSet<Atom> set;for(unsigned i=0;i<16;++i)set.insert(number(i));set.insert(value);return set; };
    auto a=make(marker),b=make(marker);
    if(pool.intern(a,1) || !pool.intern(b,1) || &*a.begin()!=&*b.begin())
      return failTest("equal atom sets not shared");
    for(unsigned kind=0;kind<8;++kind) {
      Atom other=marker;
      if(kind==0)other.kind=Atom::Fn;
      if(kind==1)other.kind=Atom::Root;
      if(kind==2)other.object=module->getGlobalVariable("t1",true);
      if(kind==3)other.offset=1;
      if(kind==4)other.stride=8;
      if(kind==5)other.integer=APInt(32,0);
      if(kind==6)other.numerical=true;
      if(kind==7)other.integer=APInt(64,1);
      auto c=make(other);
      if(pool.intern(c,1) || &*c.begin()==&*b.begin())return failTest("hash collision hid atom provenance");
    }
    a.insert(number(99));if(b.count(number(99)))return failTest("interned source mutated");
    { auto temporary=make(marker);if(pool.intern(temporary,42))return failTest("unexpected canonical image"); }
    auto fresh=make(marker);if(pool.intern(fresh,42))return failTest("interner retained a dead set");
    return 0;
  }
  Analysis analysis(*module,module->getFunction("top"),true);analysis.run();
  auto *top=module->getFunction("top");
  auto value=[&](const char *name)->AV& {return analysis.values[top->getValueSymbolTable()->lookup(name)];};
  auto &set=value("set");if(set.top || set.atoms.size()!=16)return failTest("unexpected table facts");
  if(mode=="values") {
    if(!sameNodes(set,value("copy")) || !sameNodes(set,value("call")))return failTest("equal value sets not interned");
  } else if(mode=="parameters") {
    if(!sameNodes(set,analysis.values[module->getFunction("sink")->getArg(0)]))return failTest("parameter set not interned");
  } else if(mode=="fields") {
    auto *arg=module->getFunction("pair_sink")->getArg(0);
    if(!sameNodes(set,analysis.fields[{arg,{0}}]) || !sameNodes(set,analysis.fields[{arg,{1}}]))
      return failTest("aggregate parameter fields not interned");
  } else if(mode=="slots") {
    const AV *first=nullptr,*second=nullptr;
    for(auto &slot:analysis.slots) {
      if(slot.object==module->getGlobalVariable("slot0",true))first=&slot.value;
      if(slot.object==module->getGlobalVariable("slot1",true))second=&slot.value;
    }
    if(!first || !second || first->top || first->atoms.size()!=17 || !sameNodes(*first,*second))
      return failTest("equal slot sets not interned");
  } else return failTest("unknown sharing case");
  return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--major', type=int, choices=(18, 23), required=True)
    parser.add_argument('--plugin', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    header = (args.source_root / 'src/Bennett.h').read_text()
    # Access only: no data member, layout, or production visibility changes.
    (directory / 'Bennett.h').write_text(header.replace('class Analysis {', 'class Analysis {\npublic:', 1))
    source = directory / 'probe.cpp'
    source.write_text(PROBE)
    flags = run([f'/usr/lib/llvm-{args.major}/bin/llvm-config', '--cxxflags', '--ldflags', '--libs', '--system-libs'])
    assert flags.returncode == 0, flags.stderr
    executable = directory / 'probe'
    options = shlex.split(flags.stdout)
    link = [x for x in options if x.startswith(('-l', '-L'))]
    compile_flags = [x for x in options if x not in link]
    argv = ['c++', *compile_flags, '-std=c++17', '-UNDEBUG',
            '-I', directory, '-I', args.source_root / 'src', '-I', ROOT / 'src',
            source, args.plugin.absolute(), *link, f'-Wl,-rpath,{args.plugin.absolute().parent}', '-o', executable]
    built = run(argv)
    assert built.returncode == 0, built.stderr
    rows = []
    for case in ('copy', 'values', 'parameters', 'fields', 'slots', 'interner', 'merge'):
        result = run([executable.absolute(), case])
        rows.append(dict(case=case, exit=result.returncode, stderr=result.stderr))
    (directory / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    assert all(row['exit'] == 0 for row in rows), rows
    print(json.dumps(dict(major=args.major, cases=len(rows), passed=True)))


if __name__ == '__main__':
    main()
