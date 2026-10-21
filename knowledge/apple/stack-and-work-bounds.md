# Stack and work bounds

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## A depth limit does not bound stack or total work

Treat input as untrusted and give each resource its own ceiling: nesting depth, node count, text
length in UTF-16 units, geometric extent, output items and input bytes. One limit does not stand
in for another. Layout, speech, drawing, retry passes, table occupancy, cache hits and callback
work each consume something different, and derived outputs, such as an accessibility reading,
obey the same bounds as the layout and leave out content past them.

A depth limit bounds the levels, not what each level costs:

- An unoptimized (debug) Swift build gives every level of a recursion the function's whole
  frame, with a slot for every value any branch holds. Frames differ between builds and change
  with each edit: one recursive function took 13,872 bytes a level in debug and 5,168 in
  release, and a dispatch function's debug frame reached 201,520 bytes.
- Bound retry passes separately from the work inside each pass.
- Parse time can grow faster than depth. SwiftSoup 2.9.6's HTML parse, measured in August
  2026, was quadratic in nesting depth (2,000 levels in 1.33 s, 20,000 in over two minutes),
  and its recursion overflowed the stack between 2,000 and 4,000 levels. Cap nesting far below
  that (256 was the chosen cap) and parse on a large stack as well.
- Fixed fixtures at one depth are scoped measurements, not a universal safe depth. Other fonts,
  attributes, stretched operators, width constraints or callbacks reach the stack sooner.
- Trusted host callbacks, such as speech composers and image providers, run inside the
  library's budgets but outside any sandbox it can enforce. Require bounded output from them.
- Refuse document type declarations before parsing, so no entity expands and nothing external
  loads (see [document parsing](document-parsing.md)).

## Work budgets charge cached work its original cost

A cache that makes repeated work free also hides it from a work budget. Charge a cache hit the
cost of the work it replaces: a cached table its original descendant count and measured grid
work, a requested text range its length whether or not the range was cached.

- A unit counter measures neither elapsed time nor framework-internal cost such as Core Text's
  paragraph resolution and shaping. Long paragraphs can still take substantial time.
- Narrow inputs can exhaust a work budget before the input limit. That is a bounded refusal, not
  a fault.
- Share only a small counter object between engines that keep their own caches. A retained
  recipe that holds the counter, not its parent's cache, keeps no source cache alive and forms
  no cache, recipe and engine ownership cycle.
- Pin an algorithm's cost in tests by counting its work, not timing it (see
  [measurement](../../guides/measurement.md)).

## A remaining-stack guard keeps a reserve for work it cannot see

Library code runs on the caller's thread. It neither enlarges the caller's stack nor moves work
to another thread, and the caller may be a cooperative-pool thread with about 512 KiB of stack
(see [Swift concurrency](swift-concurrency.md)). Before each recursive step, compare the current
stack position with a floor and refuse cleanly once it is passed:

- Compute the floor once per entry: the stack top from `pthread_get_stackaddr_np`, its size from
  `pthread_get_stacksize_np`, plus a fixed reserve above the bottom. When the address of a local
  is not inside the range those calls describe, return no floor rather than a wrong one.
- Size the reserve for what runs between checks and is not checked itself: assembly, Core Text
  shaping, font operations and host callbacks. 128 KB is one measured choice.
- Keep the check to one comparison of a local's address with the floor, cheap enough for every
  element.
- The guard can refuse before the depth ceiling. Report that as an input-limit outcome, distinct
  from a bug.

## Small recursive frames and heap cursors keep depth cheap

- Walk single-child chains and other long linear structures with heap cursors, or with an
  explicit stack of your own, such as for a chain of CSS custom-property references, so a long
  chain needs no deeper call stack than a short one.
- Keep what a level decides in a function it calls, one that returns before the recursion goes
  on. The frame repeated at every level is then the small one: moving one level's decisions out
  cut a debug frame from 13,872 to 640 bytes.
- Keep large temporaries (style, preparation and placement values) outside recursive functions,
  and keep large inherited values on the heap with copy-on-write instead of copying them into
  every frame.
- Read a frame's size from the object file, debug and release separately: the size the
  prologue passes to `___chkstk_darwin` (or subtracts from `sp`) plus the registers it saves.
  Disassemble one function with `objdump -d --disassemble-symbols=SYMBOL`, giving the mangled
  symbol with its leading underscore. `-warn-long-function-bodies` reports type-checking time,
  not stack.

## Darwin pads a requested thread stack size

A requested `Thread.stackSize` or `pthread_attr_setstacksize` does not give exactly that stack:
on macOS 27.0 and iOS 27.0 (October 2026), new pthreads received 12 KB more than requested.
Cooperative-pool threads report 536,576 bytes, which is 512 KiB plus 12 KiB; that they share the
padding is an inference from the sizes, not a documented relation. For a test that must run on
exactly `N` bytes of stack, allocate the stack yourself:

1. `mmap` `N` bytes plus two guard pages, `PROT_READ | PROT_WRITE`, `MAP_PRIVATE | MAP_ANON`.
2. `mprotect` the first and last pages `PROT_NONE`, so an overrun faults instead of writing over
   neighboring memory.
3. Call `pthread_attr_setstack` with the region between the guard pages and `N`, then
   `pthread_create`.
4. On the worker, assert that `pthread_get_stacksize_np(pthread_self())` equals `N` before doing
   the work.
5. Join the thread, then `munmap` the whole region.

To measure how much of a stack the work used, fill the stack with a known pattern before the
thread starts and, after it ends, find the lowest word that no longer holds the pattern.

## Compare a small worker against a reference worker in debug and release

Establish a depth claim by running the same inputs on an exactly sized small worker and on a
large reference worker, for example 512 KB against 8 MB, in both debug and release builds:

- Compare everything the work produces: geometry, item counts, ink bounds, rendered pixels and
  derived outputs such as spoken readings. Repeat the small-worker run to check determinism.
- Add exact smaller stacks (for example 128 KB and 256 KB) and a sweep of requested stack sizes
  as safe-rejection controls. A smaller worker may refuse a bounded input, but it must refuse
  cleanly.
- An optional depth sweep that reports the deepest successful chain per shape supplements the
  fixed assertions and does not replace them. Keep its output with the compiler and platform it
  ran on, and remeasure stack-sensitive results after compiler or platform changes.
- When a suite's own deep tests would run on pool threads, run that work on a dedicated thread
  with a large painted stack, such as 8 MiB, the size of a macOS main thread, and fail the test
  when it uses more than half. Assert the production path's headroom separately against the
  real pool stack size (see [Swift concurrency](swift-concurrency.md)).
- Pass an optional sweep's flag to iOS test processes with xcodebuild's `TEST_RUNNER_` prefix
  (see [simulator testing](../../guides/simulator-testing.md)).

Evidence: [PDFReflowLib measurements/deep-recursion-test-stack](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/deep-recursion-test-stack/record.md).
