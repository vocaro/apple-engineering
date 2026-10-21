# Simulator testing

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Simulator lifecycle

Explicit UDIDs, completed boot, headless install/launch/capture, bounded commands and cleanup scoped to owned devices. Provide separate disposable-device and reserved-pool adapters.

[EPUBLib scripts/test-ios.sh](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/scripts/test-ios.sh) and [Pagepour doc/device-testing.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/doc/device-testing.md#reuse-the-simulator-pool). Their lifecycle policies deliberately differ.

## XCTest execution discipline

Build once, run copied test manifests against explicit destinations, forward environment into the test process, verify executed IDs/counts and preserve terminal results.

[EPUBLib scripts/run-voiceover-simulator.py](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/scripts/run-voiceover-simulator.py) and [MathMLLayout doc/testing.md](https://github.com/vocaro/MathMLLayout/blob/8e038411260803c3b272dff590129516e7d846d7/doc/testing.md#worker-depth). A zero-test success is unavailable coverage.

## Multiple displays and fold poses

Explicit pose changes, measured viewport checks, active-display discovery, same-phase screenshot collection, nonblack/geometry checks and hash-bound receipts.

[Pagepour scripts/simulator-capture/README.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/scripts/simulator-capture/README.md) and [Pagepour scripts/duo-pose/README.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/scripts/duo-pose/README.md). Device/runtime adapters remain versioned; an image filename or requested pose does not prove the captured display.

## Destination identity spelling

Use the canonical uppercase UUID when passing a simulator identifier to xcodebuild. In the
2026-10-20 StudyWright adapter check, simctl accepted the lowercase UUID while xcodebuild
refused that destination despite listing the same device in uppercase. The shared lifecycle
helper validates and emits the canonical UUID. This is a destination lookup observation, not
a failure of the tests or simulator runtime.
