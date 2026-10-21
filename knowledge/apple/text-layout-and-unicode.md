# Text layout and unicode

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Logical text recovery is different from forward bidi layout

Keep grapheme/UTF-16 permutations and attribute remapping explicit. A standards-conforming forward bidi resolver is not automatically a replacement for recovering the logical order of PDFKit’s observed output. Preserve compatibility evidence at the adapter boundary.

[PDFReflowLib doc/bidi-boundary.md](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/doc/bidi-boundary.md). BidiKit explicitly makes no general UAX 9 conformance claim for its limited resolver; PDF-specific source recovery remains outside the value-only package.

## A depth limit does not bound stack or total work

Layout, speech, drawing, retry passes, table occupancy, cache hits and callback work can consume different resources. Use explicit counters, iterative traversal where appropriate and measured small-stack coverage. Retained recipes/caches also need ownership boundaries to avoid cycles and hidden repeated work.

[MathMLLayout doc/limits.md](https://github.com/vocaro/MathMLLayout/blob/8e038411260803c3b272dff590129516e7d846d7/doc/limits.md#bounds). Its documented 64-level fixtures are scoped measurements, not a universal safe depth for arbitrary fonts, attributes, stacks or compiler builds. Trusted host callbacks remain outside a parser’s sandbox.

## Bidi wrapping needs paragraph context and physical geometry

Keep logical ranges and full-paragraph bidi context when shaping selected lines; independently shaping substrings can lose surrounding number/neutral/control context. Moving an RTL structure is different from reflecting its glyphs. Physical left/right alignment, glyph slant, accent attachment and local direction overrides need explicit rules.

[MathMLLayout doc/line-breaking.md](https://github.com/vocaro/MathMLLayout/blob/8e038411260803c3b272dff590129516e7d846d7/doc/line-breaking.md) and [MathMLLayout doc/directionality.md](https://github.com/vocaro/MathMLLayout/blob/8e038411260803c3b272dff590129516e7d846d7/doc/directionality.md). This complements the PDF inverse-recovery lesson rather than prescribing the same bidi algorithm to both.

## Font and image metrics have different units

Distinguish font design units, em values, points, pixels, intrinsic logical image size and output scale. Resolve variable-font metrics from the actual selected CoreText instance. Freeze optional device corrections into layout rather than changing measured geometry while drawing at another scale; do not infer font-like attachment metrics from arbitrary image pixels or alt text.

[MathMLLayout doc/fonts.md](https://github.com/vocaro/MathMLLayout/blob/8e038411260803c3b272dff590129516e7d846d7/doc/fonts.md#math-value-adjustments) and [MathMLLayout doc/images.md](https://github.com/vocaro/MathMLLayout/blob/8e038411260803c3b272dff590129516e7d846d7/doc/images.md). Useful for graphics/rendering APIs generally; supported OpenType formats and dimension limits remain implementation-specific.

## Spoken localization must preserve authored content and actual language

Select a complete vocabulary with explicit locale fallback, compose structural readings through that provider, and return the language actually selected so the host chooses the matching voice. Regional word substitution belongs in the vocabulary, not a rewrite of the finished reading that could alter author text. Mixed-language accessibility also needs per-range speech language where supported.

[MathMLLayout doc/speech-locales.md](https://github.com/vocaro/MathMLLayout/blob/8e038411260803c3b272dff590129516e7d846d7/doc/speech-locales.md) and [EPUBLib doc/native-viewer.md](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/doc/native-viewer.md#input-and-accessibility). Sentinel-language fixtures prove provider plumbing; they do not prove natural pronunciation or human acceptance.
