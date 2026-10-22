# Swift concurrency

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Cooperative-pool threads have small stacks

Swift concurrency runs tasks, default actors' jobs and Swift Testing tests on threads of the
cooperative pool. On macOS 27.0 (26A428) with Xcode 27.0 (27A266a) and Swift 6.4, September
2026, `pthread_get_stacksize_np` reported 536,576 bytes for those threads, against 8 MiB for a
macOS process's main thread. An actor on the default executor, and library code it calls, runs
with about half a megabyte of stack.

- A debug build of an app runs library work on the pool too, so the headroom there is the
  library's to keep, not only the test suite's.
- A recursion that fits in release can overrun a pool stack in debug, where every level carries
  the function's whole frame. A test that overruns one ends the whole suite with SIGBUS, naming
  no test.
- Run deep-recursion tests on a thread of their own. For async work, give the task a
  `TaskExecutor` that runs its jobs on a dedicated thread and enter it with
  `withTaskExecutorPreference` (SE-0417). Every job of the task then runs on that thread,
  including a default actor's and every nonisolated async function the task calls. Wait for the
  thread to end from another thread, because the task may still be running on it.
- Assert the production path's headroom separately: run the deepest supported input on a stack
  of its own and fail when it uses more than a set share of the pool's stack size, read with
  `pthread_get_stacksize_np` from a detached task rather than assumed.

See [stack and work bounds](stack-and-work-bounds.md) for exact-size worker stacks, stack
measurement and the remaining-stack guard.

Evidence: [PDFReflowLib measurements/depth-limit-pool-stack](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/depth-limit-pool-stack/record.md).

## Blocking waiters occupy cooperative threads

The cooperative pool has one thread per CPU core at a priority (18 on a Mac with 6 performance
and 12 efficiency cores, observed September 2026) and adds no thread when one blocks. A
synchronous wait, such as a lock, `DispatchSemaphore.wait`, `DispatchGroup.wait`,
`DispatchQueue.sync` or a timed `NSLock.lock(before:)`, occupies its thread for the whole wait.
Enough waiters, from concurrent work or parallel tests, occupy every thread, and other work at
their priority then runs only when one of them gets through.

- A gate stays live under a full pool only if its holder runs synchronously on its own thread
  and waits for nothing: no `await`, continuation, semaphore or task inside the gate.
- Never let a gate's holder wait for work that needs a pool thread. A test that held a gate on a
  dispatch thread until its own task signaled it deadlocked whenever enough other tests reached
  the gate, and only its fail-safe ended the hold. Take such steps on threads of their own.
- `NSLock.lock()` cannot observe task cancellation. Try the lock once; when it is contended,
  wait in short timed `lock(before:)` intervals, checking cancellation between them, and check
  again after acquiring.
- A canceled waiter returns while the holder continues, and a framework call already running
  cannot be interrupted. The wait interval is a cancellation-check policy, not a latency
  guarantee.

Evidence: [PDFReflowLib measurements/extraction-gate-full-pool](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/extraction-gate-full-pool/record.md).

## Releasing many tasks onto a gate at once can starve the pool

Work that holds many tasks at their start and then releases them together moves them all onto a
blocking resource at once. A live-framework availability probe that ran before each test held
every such test until the framework had loaded, then released them together onto a shared gate
while another test held it. Every pool thread waited, the holding test's next step could not
run, and that suite failed in about two thirds of runs. With the probe after the test, or an
equally long sleep in its place, it failed none.

Avoid synchronized starts in front of a blocking resource, and run availability probes after
the work they judge (see [evidence](../../guides/evidence.md)).

## Awaited callbacks give ordering and backpressure

An awaited callback lets the client suspend, including a hop to `MainActor`, while the producer
waits for it before continuing. That gives ordered events, no overlapping callbacks for one
operation, backpressure, and a completion event that arrives only after the result exists.

- Wrapping the call in an unstructured `Task { await callback(...) }` detaches it and loses all
  of these. Keep a regression that fails under that mutation, for example by requiring every
  callback to have entered and returned, in order, before the operation returns.
- Do not hold a framework lock across the callback.
- A callback is an event; an observed progress object is current state (see
  [framework lifetimes](framework-lifetimes.md)).
