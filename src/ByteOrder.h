#pragma once
#include "llvm/ADT/APInt.h"
#include <string>

namespace bennett {
// ISA memory is little endian. Reverse a byte-sized carrier at a source
// big-endian load/store boundary; leave the data image in source byte order.
template<class Constant, class Emit>
std::string reverseBytes(std::string value, unsigned width,
                         Constant constant, Emit emit) {
  auto mask=constant(llvm::APInt(width,255));
  std::string result;
  for(unsigned k=0;k<width/8;++k) {
    auto byte=value;
    if(k)byte=emit(width,"lshr "+byte+" "+constant(llvm::APInt(width,k*8)));
    byte=emit(width,"and "+byte+" "+mask);
    auto shift=width-8-k*8;
    if(shift)byte=emit(width,"shl "+byte+" "+constant(llvm::APInt(width,shift)));
    result=result.empty()?byte:emit(width,"or "+result+" "+byte);
  }
  return result;
}
}
