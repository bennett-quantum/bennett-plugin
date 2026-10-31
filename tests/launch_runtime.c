/* Launch-ABI protocol witness, not a device execution oracle. The production
 * object is separately executed by the independent ISA reference interpreter.
 */
#include "bennett_launch.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned stage, tokens;
static unsigned char object_marker, args_marker, result_marker;
static bennett_program_t *program;
static bennett_args_t *arguments;
static bennett_result_t *result;
bennett_status bennett_load(const uint8_t *o, size_t n, const uint8_t *t,
                            size_t tn, bennett_program_t **out) {
  assert(stage++ == 0 && n > 100 && !memcmp(o, "bennett-object isa=0.8", 21));
  assert(tn == 2 && !memcmp(t, "{}", 2));
  FILE *f = fopen(getenv("CAPTURE_OBJECT"), "wb");
  assert(f);
  assert(fwrite(o, 1, n, f) == n);
  assert(!fclose(f));
  *out = program = (bennett_program_t *)&object_marker;
  return BENNETT_OK;
}
bennett_status bennett_args_new(size_t n, bennett_args_t **out) {
  assert(stage++ == 1 && n == 3);
  *out = arguments = (bennett_args_t *)&args_marker;
  return BENNETT_OK;
}
bennett_status bennett_args_set_int(bennett_args_t *a, size_t i, uint32_t w,
                                    const uint8_t *v) {
  assert(stage++ == 2 && a == arguments && i == 0 && w == 32 && v[0] == 11 &&
         !v[1] && !v[2] && !v[3]);
  return BENNETT_OK;
}
bennett_status bennett_budget(bennett_program_t *p, const char *r, uint64_t s,
                              uint64_t h, uint64_t st, uint64_t d,
                              bennett_token *out) {
  assert(stage == 3 + 2 * tokens && p == program && !strcmp(r, "ref") &&
         s == 5 && h == 0 && st == 7 && d == 1);
  ++stage;
  *out = 100 + tokens;
  return BENNETT_OK;
}
bennett_status bennett_args_set_token(bennett_args_t *a, size_t i,
                                      bennett_token t) {
  assert(stage++ == 4 + 2 * tokens && a == arguments && i == tokens + 1 &&
         t == 100 + tokens);
  ++tokens;
  return BENNETT_OK;
}
bennett_status bennett_run(bennett_program_t *p, const char *e,
                           const bennett_args_t *a, const uint8_t *t, size_t n,
                           bennett_run_id *out) {
  assert(stage++ == 7 && tokens == 2 && p == program && a == arguments &&
         !strcmp(e, "top") && !t && !n);
  *out = 33;
  return BENNETT_OK;
}
void bennett_args_free(bennett_args_t *a) {
  assert(stage++ == 8 && a == arguments);
}
bennett_status bennett_wait(bennett_program_t *p, bennett_run_id id,
                            bennett_result_t **out, bennett_request_t **rq) {
  assert(stage++ == 9 && p == program && id == 33);
  *out = result = (bennett_result_t *)&result_marker;
  *rq = NULL;
  return BENNETT_OK;
}
size_t bennett_result_nfaults(const bennett_result_t *r) {
  assert(stage++ == 10 && r == result);
  return 0;
}
bennett_status bennett_result_get(const bennett_result_t *r, size_t i,
                                  bennett_arg_kind *k, uint32_t *w,
                                  uint8_t *out, size_t cap) {
  assert(stage++ == 11 && r == result && i == 0 && cap == 4);
  *k = BENNETT_ARG_INT;
  *w = 32;
  unsigned v = EXPECTED;
  for (unsigned j = 0; j < 4; ++j)
    out[j] = (v >> (8 * j)) & 255;
  return BENNETT_OK;
}
bennett_status bennett_run_close(bennett_program_t *p, bennett_run_id id) {
  assert(stage++ == 12 && p == program && id == 33);
  return BENNETT_OK;
}
void bennett_result_free(bennett_result_t *r) {
  assert(stage++ == 13 && r == result);
}
bennett_status bennett_unload(bennett_program_t *p) {
  assert(stage++ == 14 && p == program);
  return BENNETT_OK;
}
unsigned top(unsigned);
int main(void) {
  assert(top(11) == EXPECTED);
  assert(stage == 15);
  puts("launch protocol and result: ok");
  return 0;
}
