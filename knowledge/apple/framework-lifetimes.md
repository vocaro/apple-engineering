# Framework lifetimes

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Framework safety includes object destruction and font lifetime

The PDFKit workaround serializes extraction and drains autoreleased results before unlocking; locking only the calls left races. Holding a face and controlling its release changed the observed failures, while unrelated host CoreText/SwiftUI work remained relevant. Document why process isolation was chosen and where its guarantees stop.

[PDFReflowLib doc/decisions/0002-pdfkit-extraction-gate.md](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/doc/decisions/0002-pdfkit-extraction-gate.md) and [PDFReflowLib doc/decisions/0016-a-conversion-holds-the-faces-it-reads.md](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/doc/decisions/0016-a-conversion-holds-the-faces-it-reads.md). These records retain residual first-use races and distinguish inferred mechanisms from observations. Do not generalize to all PDFKit operations or OS versions.

## Streaming requires explicit ownership and backpressure

Separate spatial evidence from a logical output model; spill intermediate pages, stream blocks/assets into the writer, and retain the workspace until the consumer finishes. Awaited callbacks preserve ordering but must not hold unrelated framework locks. Measure repeated conversions as well as one fresh process because framework-retained objects can accumulate.

[PDFReflowLib doc/architecture.md](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/doc/architecture.md#serialization-and-resource-lifetime), [PDFReflowLib doc/memory-testing.md](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/doc/memory-testing.md#repeated-conversions-in-one-process) and [PDFReflowLib measurements/pdfkit-repeated-conversions/record.md](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/measurements/pdfkit-repeated-conversions/record.md). These are pipeline/lifetime patterns, not permission to move PDF reconstruction into the general toolkit.
