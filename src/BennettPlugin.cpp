// bennett-plugin: LLVM pass plugin skeleton.
//
// The real code is behind BENNETT_HAVE_LLVM so this file compiles without LLVM
// headers installed. CMake defines it only when find_package(LLVM) succeeds.
//
// Planned pipeline (all in this one pass; see README):
//   1. taint analysis over the whole-program call graph,
//   2. region outlining,
//   3. controlled / adjoint body generation,
//   4. lowering to the virtual ISA (bennett-isa-spec),
//   5. call into bennett-sched for scheduling.

#ifdef BENNETT_HAVE_LLVM

#include "llvm/IR/PassManager.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"

namespace {

// Placeholder module pass. Fail loud: it must never silently succeed.
struct BennettPass : llvm::PassInfoMixin<BennettPass> {
  llvm::PreservedAnalyses run(llvm::Module &, llvm::ModuleAnalysisManager &) {
    llvm::report_fatal_error("bennett-plugin: pass not implemented (skeleton)");
  }
  static bool isRequired() { return true; }
};

} // namespace

// Entry point looked up by `opt -load-pass-plugin` / `clang -fpass-plugin`.
extern "C" LLVM_ATTRIBUTE_WEAK ::llvm::PassPluginLibraryInfo llvmGetPassPluginInfo() {
  return {LLVM_PLUGIN_API_VERSION, "bennett", "0.0.0", [](llvm::PassBuilder &PB) {
            PB.registerPipelineParsingCallback(
                [](llvm::StringRef Name, llvm::ModulePassManager &MPM,
                   llvm::ArrayRef<llvm::PassBuilder::PipelineElement>) {
                  if (Name == "bennett") {
                    MPM.addPass(BennettPass());
                    return true;
                  }
                  return false;
                });
          }};
}

#else

// Without LLVM there is nothing to build; keep the translation unit non-empty.
namespace bennett { const char *plugin_status() { return "built without LLVM (skeleton)"; } }

#endif
