# Voiceover

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Simulator VoiceOver

Muted speech capture, readiness waits, step execution, cursor/rotor observations, transcripts, strict assertions and restoration; separately package guarded cursor activation.

[EPUBLib doc/testing.md](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/doc/testing.md#simulators), [EPUBLib scripts/simulator_voiceover_activation.py](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/scripts/simulator_voiceover_activation.py) and its Python/Objective-C probe tests. The activation module is qualified only for arm64 iOS 27.2 build 24B5110a and the pinned VoiceOver binary; retain fingerprints, instruction checks, canaries and stock negative controls.

## Hosted Mac VoiceOver

Speech observer, navigation driver, session grammar, batched settings, transcript capture, runner provenance and guarded manual dispatch.

[EPUBLib doc/testing.md](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/doc/testing.md#hosted-mac-sessions) and [EPUBLib scripts/hosted-run.py](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/scripts/hosted-run.py). Keep reader fixtures and app build/launch adapters local; disposable-runner preparation must never run on the workstation.
