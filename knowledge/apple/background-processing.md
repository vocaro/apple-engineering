# Background processing

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Continued-processing lifecycle

Request submission, scheduler acceptance and a runtime grant are distinct states. Capture concrete identifier registration, per-attempt identity, bounded grant waits, late-grant rejection, cancellation, expiration and recovery.

[Sources/PDFReflowKit/ContinuedProcessingSession.swift](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/Sources/PDFReflowKit/ContinuedProcessingSession.swift) and [measurements/background-grant/record.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/measurements/background-grant/record.md). The current 30-second grant wait is an application policy supported by those measurements, not an iOS guarantee.

## Progress, stalls and scheduler diagnosis

Distinguish deadlock, long setup, expensive work and CPU starvation. Preserve the methods for journaling expiration at its actual callback, measuring runnable threads versus CPU use, and correlating task progress with scheduler and power logs.

[measurements/background-stall/record.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/measurements/background-stall/record.md), [measurements/continue-question/record.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/measurements/continue-question/record.md) and [scripts/continued-processing-log.py](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/scripts/continued-processing-log.py). Staging large files and polling them can perturb the workload through indexing and file-service activity. Observed stall intervals are not universal deadlines.

## Background compute eligibility and quality

A background task grant, a supported compute device, a signed entitlement and acceptable output quality are separate requirements. Document CPU/GPU/Neural Engine distinctions and the failed or unavailable approaches.

[measurements/ios-gpu-background/record.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/measurements/ios-gpu-background/record.md) and [README.md](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/README.md). Record OS, device, signing and workload; a foreground capability probe alone does not qualify a background pipeline.

## System-provided background UI

Explain the continued-processing activity already provided by iOS, how Stop reaches the expiration path, what a custom Live Activity would add, and how old failed-task cards can confuse a later observation.

[measurements/continued-processing-activity/record.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/measurements/continued-processing-activity/record.md) and [measurements/continue-question/record.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/measurements/continue-question/record.md). Preserve differences between observed controls, ambiguous gestures and untested behavior.

## Shared implementation

BackgroundTaskLib owns the domain-independent state machine. PDFReflowKit retains
conversion-status mapping, application-specific messages and compute admission. A
grant does not select an artifact protection class or persist work across a restart.
