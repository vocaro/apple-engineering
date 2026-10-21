# Scenes and recovery

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Durable recovery and actor isolation solve different failures

Persist lifecycle before work, keep immutable content versions, reconcile checksummed manifest generations and preserve damaged/future-schema data. After every suspension, confirm that the object being updated still exists and has the same authority; an actor does not make a multi-await operation transactional. Two individually atomic files are not an atomic pair.

[studywright doc/components/ingestion.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/doc/components/ingestion.md). Capture the manifest/sidecar example and recovery controls as patterns; do not prescribe one storage schema for all apps.

## Scene restoration is not just view reconstruction

Define app-owned shared services, per-scene reader state and stable identities separately. StudyWright observed that restored iOS scenes retain their session ID without replaying the expected user activity, requiring its own identity record. A disconnected scene is not necessarily discarded. Pagepour uses aggregate app scene phase so one backgrounded window does not interrupt work while another is active.

[studywright doc/architecture.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/doc/architecture.md#app-screen-and-testing-boundaries) and [Pagepour doc/mobile-windows.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/doc/mobile-windows.md). Recheck the actual restoration/activation callbacks on each platform; a capability such as multiple-window support may also be insufficient for the current fold/display state.
