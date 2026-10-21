# App extensions

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## App extension memory and hardware qualification

Describe the physical-device memory probes, jetsam evidence and entitlement experiment before recommending an extension as a process boundary.

[measurements/converter-extension-693/record.md](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/measurements/converter-extension-693/record.md). The tested app-defined ExtensionKit extension had a 35 MiB limit on the tested iPhone and iPad running 27.2 build 24B5110a; the tested iPad entitlement did not raise it. The simulator enforced no such limit. This is not a blanket limit for every extension point or OS.

## Extension process lifetime and XPC

Document process reuse, connection lifetime, explicit completion, cancellation while running, confirmation of process exit and a watchdog for a session that never answers.

[measurements/converter-extension-693/record.md](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/measurements/converter-extension-693/record.md#check-5-lifetime). In the measured host, `invalidate()` withdrew the hold and could suspend rather than terminate the process; cancelling a suspended session produced a dead-session reuse failure. Preserve the reproducer and failed path.

## Extension packaging, linking and shared containers

Capture the multiplatform XcodeGen macOS runpath failure, static versus dynamic package linkage in app-hosted tests, resource-bundle loading, signing identity and App Group checks.

[measurements/converter-extension-693/record.md](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/measurements/converter-extension-693/record.md#check-6-linking). Successful development launch is distinct from App Store/TestFlight acceptance; store validation remained a separate step in that record.
