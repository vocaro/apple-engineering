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
