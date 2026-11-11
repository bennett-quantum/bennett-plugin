# R process argument bytes

The R producer supports the §19.2 main ABI with zero, two or three parameters.
When an entry uses argv or envp, `build.json.entry_initialisation.arguments`
is `bennett-argv-bytes-1`. Its CC stub declares `bennett.argv.bytes` service
version `1`. This is a launch adapter protocol; it adds no ISA instructions or
ISA layout fields.

The host supplies one packed little-endian payload:

| Offset | Field |
| --- | --- |
| 0 | argc, unsigned i32 (the nonnegative C argc) |
| 4 | reserved, i32 zero |
| 8 | envp element count, unsigned i64 |
| 16 | complete payload size, unsigned i64 |
| 24 | argc target-pointer-width offsets, followed by a zero sentinel |
| following argv | envp-count target-pointer-width offsets, followed by a zero sentinel |
| following vectors | null-terminated argument and environment string bytes |

Each nonzero offset is relative to the payload start and points into its string
bytes. Equal string contents still have their own process argument entries.
No native pointer is a transport value. Both pointer vectors are present even
when empty. A two-parameter native main obtains envp from native `environ`.

The first request exposes a zeroed 24-byte header. The host replies with the
complete payload; ISA hostcall truncation copies the header while its returned
length supplies the allocation size. The CC stub allocates that many bytes in
the normal device heap, then issues a second request exposing that zeroed
allocation. The host repeats the exact payload. The stub checks the returned
length, declared size, vector extents, sentinel entries and string offsets,
then relocates the vector entries to device addresses. Malformed replies trap
before entering source code. Ordinary heap limits govern storage; no separate
argument-size limit is imposed. Storage survives the source entry and exit
cleanup and is freed when the whole-program launch returns. Whole-run reversal
undoes the hostcall overwrites, relocation, source mutations and allocation.

The plugin's generated host stub implements both replies, using the supplied
argv/envp strings and freeing its native serialization buffer afterwards.
Other launch adapters must implement this service when the build record names
this protocol. Entries that never read pointer parameters retain the existing
`bennett.argv` header request. Runtime process preparation and normal-return
exit handling remain in the linked entry wrapper; byte import does not replace
them or suppress cleanup.

`tests/r_process_arguments.py` runs the actual emitted R program forwards and
backwards with nonempty vectors, and executes its generated host stub against
the pinned VM with real native argument vectors.
The same regression covers 32- and 64-bit device pointer vectors, empty argv,
empty strings, empty envp, and the pinned musl process-preparation/atexit/stdio
closure. The normal-return wrapper calls the published exit path exactly once.
The musl fixture supplies the empty static-link finalizer-array bounds for its
program, while retaining its registered atexit callback and stdio flush.

The process closure also retains typed indirect-call candidates under dialect
§14.2. N23 records each variadic call's fixed-parameter count so that a
nonvariadic implementation reached through a variadic alias (the published
`_fini` default) receives its fixed arguments and ignores the va block. This
preserves the runtime body and its actual source ABI rather than emitting an
ISA call with the wrong argument count.
After a runtime writes the exit EH record, a non-returning control transfer
propagates the pseudo-exception instead of entering the compiled noreturn loop.
The launch catches its selector only after normal exit handlers and stdio flush.
