# Shared host

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Heavy-work admission

One host-wide resource namespace for builds, suites, conversions and exclusive measurements, with bounded concurrency and resource-specific locks.

[PDFReflowLib tools/heavy_slot.py](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/tools/heavy_slot.py), [studywright scripts/gate-lock.sh](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/scripts/gate-lock.sh) and Pagepour’s duplicate implementation. Preserve compatibility with existing lock paths during migration.

## Device reservations

Ownership records, real mutual exclusion, explicit handoff, process handles, original settings, bounded windows and independent restoration checks.

[Pagepour doc/device-testing.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/doc/device-testing.md#reserve-and-hand-off-shared-devices) and [Pagepour scripts/run-mobile-ui-session.py](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/scripts/run-mobile-ui-session.py). The existing JSON handoff is explicitly not a mutex. Keep personal device IDs and live reservations outside Git.

## Process supervision

Distinct tool/connection/behavior deadlines, unique logs, owned process groups, PID start identities and continued supervision after a tool yields or times out.

[studywright scripts/warm_push.py](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/scripts/warm_push.py) and [EPUBLib scripts/run-voiceover-simulator.py](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/scripts/run-voiceover-simulator.py). Do not infer termination from a missing parent or expired observation wait.

## Long pre-push checks

An idle SSH transport can close while its local pre-push hook continues running. Follow the
owned hook to its terminal result before starting more work. Record the exact commit, clean
tree and each complete gate result; a transport failure does not establish a test failure.
For a long push, a per-command SSH ServerAliveInterval can keep the transport active without
changing other sessions' SSH configuration. A retry follows the repository's hook policy and
publishes only the verified commit; never infer that interrupted or missing checks passed.

## Checkout provisioning and publication

Idempotent bootstrap, verified missing-input restoration, isolated writable environments, stable warm build paths and publication of an immutable tested commit.

[studywright doc/testing.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/doc/testing.md#provisioning-a-checkout) and [studywright doc/testing.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/doc/testing.md#persistent-push-checkout). Extract primitives first; the publication transaction and gate commands are substantially project-specific.

## Inspecting system code without starting it

Use `dyld_info -disassemble` on an on-disk framework or
`lldb -b -o "target create BINARY" -o "disassemble -n METHOD"` without a run command.
An image present only in the dyld shared cache may not be available to target-create by path.
To see calls made into code you own, log from that code. Never start or attach a debugger to
answer a framework question on the shared workstation; developer-password dialogs take the
owner's keyboard. If one appears, stop your processes and leave the dialog for the owner.

## Ending a coordinated command

Use the supplied `eng run` or resource CLI for commands. They return the child's status after
leaving admission normally. If using Admission directly, leave the context before raising
SystemExit for a nonzero result. An exception inside the context retains its uncertain guard,
by design, because the coordinator cannot infer whether that exception left children running.
A recovery checks the recorded process birth and descriptor nonce: a free owned descriptor or
a later foreign acquisition establishes that the old lock was released. Preserve every foreign
reservation. Time passing alone establishes none of this.

Legacy shell gates authenticate inherited exclusive admission for their exact lock namespace.
The coordinator does not export a lock opt-out into the suite: regression fixtures retain
independent real locks. A process wrapper must forward the admission descriptors, as the
shared process supervisor does; copying the token environment alone does not transfer ownership.

The default macOS pool uses the system's canonical user temporary directory, as reported by
getconf DARWIN_USER_TEMP_DIR, independently of a command's private TMPDIR. It keeps the old
pdfreflow-heavy-slots path. HEAVY_SLOT_DIR is an explicit namespace override for isolated tests;
using a separate command scratch directory must not multiply the host's build budget.
