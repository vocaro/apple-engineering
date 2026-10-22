# External validation

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

These methods supply expectations that do not come from the implementation under test. General
expectation rules are in [evidence](evidence.md); domain rules, such as rendering, fonts and
baseline policy, stay in the owning library.

## Harness scope and claims

An external validation harness establishes a reproducible baseline against independently
specified expectations without changing production code or claiming complete conformance.

- Exclusion records explain what was not imported; they are not a denominator for a conformance
  percentage.
- Only reference engines actually run support a claim. An adapter for another engine is not a
  claim of equivalent support.
- Run the pinned subset offline in the regular suite, in debug and release builds. Keep broader
  corpus, browser and fuzz runs on demand.

## Importing upstream assertions

Import individual assertions, each with its provenance:

- the upstream assertion name and URL and the specification section;
- the original and normalized input, their SHA-256 and every transformation;
- the expected value and the upstream tolerance.

Ship the original upstream files and license. Repackage a fixture only in ways that keep the
measured data byte-identical (for a font converted from WOFF, its MATH table and glyph metrics),
record the original and repackaged hashes and check them at test time.

Take expectations from the upstream numeric expressions, not from the library's own data reader
or regenerated screenshots. Keep the upstream tolerance and check that it exceeds raster
quantization, as a 1-point tolerance does against 0.25-point quantization. State the report's
coordinate convention, for example points relative to the baseline with y down, which negates
Core Graphics' y-up coordinates.

When a reference measures a colored box that the subject's own drawing can cover, measure in an
extra pass that draws the foreground transparently and preserves every layout dimension. Keep
the ordinary opaque drawing for bounds checks and images.

The importer accepts only reviewed expression and assertion forms and never executes upstream
JavaScript. Its pins reject source and fixture hash mismatches. Changing the upstream revision
is an explicit source review: inspect the assertions, fonts, license and normalization, rerun
debug and release builds, regenerate the reference comparison, review the gallery and keep the
original failures.

## Reports

A per-case report records the input manifest's hash, the platform, font identity, per-case
errors and the pixel origin of each PNG. Reject oversized images with a separate batch raster
budget. Ink bounds, advances and reference boxes are distinct measurements.

Every report must match the supplied manifest's hash and contain each case ID exactly once;
`validate_reports` in `src/python/vocaro_engineering/validation.py` checks this. Regenerate
older reports that lack pixel-origin metadata before drawing overlays.

Geometry decides standards outcomes; pixels are for review. A review gallery shows the source
markup, engine metadata, side-by-side images, baseline-aligned overlays, absolute difference
maps, outcome filters and numeric discrepancies. Antialiasing, hinting and box conventions cause
harmless image differences, and cross-engine width differences are observations, not automatic
failures. Bitmap drawing can put ink outside layout bounds; the allowance is in
[raster contracts](../knowledge/apple/raster-contracts.md).

## Browser reference oracles

- Pin the browser automation tool together with its browser revisions (Playwright with its
  pinned browsers), and record the browser version actually run.
- Load every fixture font explicitly, the fallback included, and wait for `FontFace.load()` and
  `document.fonts.ready` before measuring.
- Parse input as XML into an isolated DOM that admits only allowlisted elements and attributes.
  External resources, event handlers, scripts, DOCTYPE and entity declarations do not run.
- Report unsupported elements, namespaces, attributes and constraints, such as width-limited
  line breaking the adapter does not implement, as per-case reference errors. Never remove them
  silently, and never count them as library failures.

## Independent decoder oracles

Decode expectations from the actual data with an independent, pinned tool, such as fontTools for
font tables. Record each field's units: em units, percentages and design units stay distinct.
State what the oracle does not cover, and test that behavior with synthetic fixtures; a
static-font oracle says nothing about variable-instance selection or device corrections.

Bind the oracle to the hash of the installed system table it describes, because system fonts
change with OS updates. A mismatch is a visible skip, never a substitution of another font's
values, and a require flag turns it into a failure. To update, decode the installed table into a
temporary oracle, review the changes, then replace the pinned one. Never regenerate an oracle
with the library's own decoder.

## Synthetic fixture oracles

When no independent decoder covers a behavior, generate a fixture whose expected output follows
from its construction:

- Generate a small public-domain (CC0) font with a pinned generator and tool version:
  rectangular glyphs with known extents and advances, and a distinct glyph ID for each
  contextual form (Arabic isolated, initial, medial and final). Pin its checksum.
- Write expected visual glyph sequences from the specification (the Unicode Bidirectional
  Algorithm, UAX #9, for bidi), never by invoking the library or another line of the same text
  engine. Cover numbers inside right-to-left text, mirrored brackets, embeddings and isolates
  across a line boundary, and no-break spaces.
- Do not use system fallback fonts as a glyph-ID oracle.
- Run the fixture tests offline in the regular suite with no download; the generator is
  optional.

The Core Text behavior these fixtures exercise is in
[text layout and Unicode](../knowledge/apple/text-layout-and-unicode.md).

## Outcome classification and reviewed discrepancies

Classify every differential or reviewed outcome, with specific evidence, as a pass, a bug, an
intentional difference, an unsupported feature, invalid or out-of-bounds input, or an unsuitable
reference or test. A failed reference assertion is an unsuitable reference or test. Input-limit
errors, available-stack limits included, are their own category. Robustness success stays
unreviewed for visual quality. In validation-only work, file unexpected failures for a separate
production fix.

Never re-baseline automatically:

- A reviewed-outcome record keeps the original upstream expectation, reports the case as a bug
  and asserts that the observed value has not changed. It survives re-import with its
  classification, issue link and observed value.
- A strict mode fails against the original expectation.
- A newly passing or changed discrepancy needs review.
- A review may change only the classification, issue link and observed value, never the
  expectation. Reject entries for absent case IDs and for observations that already satisfy the
  assertion.
