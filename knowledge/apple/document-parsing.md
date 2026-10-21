# Document parsing

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Unicode and hostile archive paths

Separate decoded archive keys from encoded URL references. Find syntax delimiters at the byte/scalar level rather than assuming a Swift Character is one code point; combining marks can attach to a delimiter. Define normalization and duplicate identity deliberately. Bound expansion, input work and nested parser work separately.

[EPUBLib doc/architecture.md](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/doc/architecture.md#publication-model). Applicable to archive/import tools generally; EPUB’s compatibility rules, allowed names and numeric limits remain its own.

## Parser choice can change text

Preserve tests for text that platform parsers discard or normalize: EPUBLib uses a streaming libxml2 reader to preserve U+FEFF that Foundation XMLParser drops in callbacks. Structural text, recovered HTML and computed visible text are distinct products and need explicit contracts. Restore parser callbacks and error handlers rather than changing the host’s process-wide behavior.

[EPUBLib doc/architecture.md](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/doc/architecture.md#structural-text) and [EPUBLib doc/text-extraction.md](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/doc/text-extraction.md#contract). Record actual parser/version behavior and sentinel fixtures; do not assume every parser is interchangeable after a successful parse.

## Accessibility observation can change layout

A TextKit 2 geometry query or accessibility snapshot can finish lazy layout and move previously estimated positions. Preserve anchors against the actually drawn viewport; recheck hit tests and visible rows after observation and scrolling. A diagnostic observer is not necessarily passive.

[EPUBLib doc/native-viewer.md](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/doc/native-viewer.md#layout). The document distinguishes UIKit and AppKit behavior and links the reproductions. Relevant to long native text views, search and accessibility implementations.
