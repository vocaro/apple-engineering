# Accessibility

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Command submission is not completion

Distinguish accepted commands from observed navigation/paint effects. Serialize actions that must be ordered; read current state when queued work executes; reject stale work after close or replacement. Already submitted actions cannot be undone merely by cancelling their caller.

[EPUBLib doc/architecture.md](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/doc/architecture.md#engine-contract) and [EPUBLib doc/reader-controls.md](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/doc/reader-controls.md#commands-appearance-and-state). Transfer the lifecycle contract to other asynchronous UI/service APIs without adopting reader-specific commands.

## Native renderer containment needs more than a byte limit

resvg integration combines a Rust-side unwind boundary with invalidation of a failed tree, guarded access and explicit failure returns. An inner C ABI that aborts cannot be rescued by a catch outside it. Independent work/geometry budgets also address expensive successful rendering and repeated reference expansion.

[EPUBLib scripts/resvg-panic-boundary.py](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/scripts/resvg-panic-boundary.py), [EPUBLib scripts/resvg-panic-boundary.rs](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/scripts/resvg-panic-boundary.rs) and [EPUBLib doc/native-viewer.md](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/doc/native-viewer.md#limitations). Preserve the exact vendored version and controls; caught panics do not establish containment of stack exhaustion, allocation failure or every renderer defect.
