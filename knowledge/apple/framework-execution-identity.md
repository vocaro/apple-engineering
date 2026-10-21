# Framework execution identity

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Vision keeps one compile per executable name on macOS

Observed on macOS 27.0 (26A428) with Xcode 27.0 (27A266a), September 2026: Vision compiles its
document-recognition models (`RecognizeDocumentsRequest`) into a cache keyed by the running
executable's file name, `~/Library/Caches/<name>/com.apple.e5rt.e5bundlecache`, and every later
process of that name reuses the compile.

- A renamed copy of the same bytes is a different recognizer, and a copy under the same name in
  another directory is the same one. Identical bytes under another basename recognized eleven
  pages of one document differently.
- Separate compiles can read one raster very differently. A compile's programs come in a few
  discrete variants, and one program decided whether a page read as joined prose or as line
  fragments. No raster resolution from 120 to 300 dpi, and no banding, recovered the fragment
  reading.
- The first reading under a never-used name took about 29 s for a one-word image; the next
  process's took 0.13 s.
- The cache directory's presence does not establish a warm or identical compile.

This is a macOS observation. On iOS and iPadOS 27.0 (24A435) devices, the first request under a
fresh executable name took 0.18 to 0.29 s, which does not establish a cold compile: no private
cache state was inspected or reset. Do not assume the macOS cache behavior on iOS.

## The code-signing identifier also rewrites Vision's compile

Observed on the same host, 2026-09-28: a process whose code-signing identifier differs from the
one that compiled a name's cache recompiles it in place, and the next process signed as before
recompiles it again. The same identifier reuses the compile whatever the binary's bytes or
directory.

- SwiftPM release builds are signed with the product name.
- `swift build` and `swift run` debug builds are signed with the product name plus a
  40-hex-digit suffix, so under the product's name they rewrite its cache. A debug run's first
  recognized page took 93 s against 1.6 s for the release run before it.
- A `swiftc` probe is signed with its own file name. Copied in under the product's name, it
  rewrote the shared compile and changed what later runs of the product read.

Every session on the host shares that cache. Run only the release build under a product's name.
Give probes and debug tools a name of their own, or re-sign one with `codesign -i` to the
product's identifier when it must read with the product's compile. Record each compiled
program's digest before and after every run, and flag a comparison whose runs did not all read
with one unchanged compile: it cannot tell a recognition change from a compile change. Two
byte-different compiles can still read alike, so a differing compile is a caveat, not a verdict.

Evidence: [PDFReflowLib measurements/apple-feedback-vision-determinism](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/apple-feedback-vision-determinism/record.md#what-rewrites-a-names-compile-2026-09-28).

## Recognition comparisons hold the executable name fixed

- Freeze each binary under comparison into a directory of its own, keeping its basename, with
  its supporting bundles beside it, and record its hash.
- Build the baseline's release binary once and give every before-and-after comparison that
  binary.
- Where the name cannot be held fixed, compare with recognition disabled.
- A renamed executable that passes content gates is still not change-specific evidence for the
  pages it recognized.
- A control on one host establishes a sensitivity on that host. It is not a determinism
  guarantee for other builds or machines.

Evidence: [PDFReflowLib measurements/cli-name-recognition-control](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/cli-name-recognition-control/record.md).

## Vision can read one page several stable ways on one build

With no source, binary, path or option change, Vision's reading of a page can differ between
runs on one host. Observed on macOS 27.0 (26A428), September 2026: one page read as joined prose
in one run and as line fragments in the next, and another lost its recognition entirely.
`RecognizeDocumentsRequest` returned several distinct recognitions of one page, each
byte-identical whenever it recurred, and a further one appeared after four consecutive captures
had shown only the expected state.

- Attribute a difference to a change only where a second run of the baseline's own binary,
  captured the same way, does not also produce it. Refuse a control whose binary hash differs
  from the baseline's: it measures another tree's difference and would charge it to the host.
- In a deterministic gate, declare each observed recognition as a state and fail on an
  undeclared one, naming it. Recording one observation instead fails whichever run meets
  another, and regenerating it only moves which run fails.
- Record OS-owned values that move no measured outcome without comparing them (see
  [OS drift](../../guides/os-drift.md#os-owned-values-in-deterministic-gates)).

## Execution environment can change rasters and recognition

The same binary run inside a sandboxed agent process and in the normal host session on one Mac
(macOS 27.0, 26A428, September 2026) produced different output, while two different binaries
agreed within each environment. The drift tracked the environment, not the source revision.

- Parsed pages and decoded RGB images differed between the environments.
- Inside the sandbox no Metal device was available, and Vision failed with "Failed to create
  CVPixelBuffer" where the host recognized the page.
- Core ML shows the same dependence: a process that cannot open `IOSurfaceRootUserClient`
  takes a CPU path with last-bit differences (see
  [embedding correctness](../ml/embedding-correctness.md)).

Name and enforce the execution environment of every measured run. An OS string or a
caller-supplied context label does not establish comparable capabilities. Run one compiled
capability probe (Metal device, a known recognition) immediately before each run, against the
same input and launch environment, recapture it when its identity changes, and refuse stale,
failed or mismatched probe evidence. A probe samples one instant; it does not attest the run.

Evidence: [PDFReflowLib measurements/raster-environment](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/raster-environment/record.md).

## A warm-up recognition proves only its own reading

- Warm Vision up in the executable that will do the work, with the same language,
  language-correction and compute options. On macOS another executable warms another cache.
- Require the complete known word, and treat request errors, cancellation and a wrong or empty
  reading as failures the app can retry.
- A correct known word does not certify complete prose recognition, model identity, cache
  reuse or background execution. Recognition can report success while leaving part of a page
  unread, so measure what it returned against the ink on the raster it was given.
- Vision's compile can fail outright under host load (`e5rt_e5_compiler_compile call failed`,
  then `unknownError`), and the readings that needed it get nothing. Decide whether Vision could
  read with an independent probe after the test, never with the test's own expectations, and
  report the test unmeasured when the probe fails (see [evidence](../../guides/evidence.md)).
