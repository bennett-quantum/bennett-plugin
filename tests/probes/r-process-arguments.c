#include <stdlib.h>
#include <stdio.h>
extern void __bennett_rt_prepare_process(int, char **, char **);
/* This program has no .fini_array callbacks; supply its static link bounds. */
void (*__fini_array_start[0])(void) = {};
extern __typeof__(__fini_array_start) __fini_array_end __attribute__((alias("__fini_array_start")));
static void cleanup(void) { puts("bye"); }
static int user_main(int argc, char **argv, char **envp) {
  if (argc != 2 || !envp || getenv("X")[0] != 'y') return 90;
  atexit(cleanup);
  puts(argv[1]);
  return 7;
}
int main(int argc, char **argv, char **envp) {
  __bennett_rt_prepare_process(argc,argv,envp);
  exit(user_main(argc,argv,envp));
}
