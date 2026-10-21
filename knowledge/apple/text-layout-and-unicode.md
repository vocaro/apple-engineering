# Text layout and unicode

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Logical text recovery is different from forward bidi layout

Recovering the logical order of text a framework has already laid out, such as PDFKit's
extracted lines, is an inverse problem with its own compatibility rules: numbers, neutrals and
reversed runs follow what the framework observably did, not what a forward resolver would
produce. A standards-conforming forward bidi resolver is therefore not a drop-in replacement
for that recovery, and a deliberately limited forward resolver claims no UAX #9 conformance.
Keep the two behind separate interfaces, with the compatibility path and its evidence at the
adapter boundary, so a standards backend cannot silently replace measured recovery policy.

- Keep grapheme, scalar and UTF-16 permutations explicit, and remap attributes through them
  rather than re-deriving ranges.
- Test that styles survive a permutation when they change at every UTF-16 unit, including
  inside combining sequences and supplementary characters, beside the documented number and
  bracket exceptions.

## Bidi wrapping needs paragraph context and physical geometry

Resolve and shape each selected line from the full logical paragraph. Shaping a substring on its
own loses the surrounding number, neutral and directional-control context.

- Keep the whole attributed paragraph in one `CTTypesetter` and make each line with
  `CTTypesetterCreateLineWithOffset` over its logical range, so a directional control that
  opened before the range is still active.
- Choose line ranges as whole logical words, so combining sequences and Arabic joining contexts
  are never cut inside a word. No-break spaces bind their neighbors.
- Text with inline attachments stays one logical paragraph. Core Text places atomic attachments,
  such as inline images, alongside the text's per-line visual runs.

Moving an RTL structure is different from reflecting its glyphs. Core Text shapes each run with
Arabic joining, Hebrew order, combining marks and Unicode mirroring; numbers stay left to right,
and Latin letters, digits and images keep their drawing orientation when the component holding
them moves. Physical-side metrics do not mirror either:

- Corner kerning samples the physically adjoining corners: a script to the left of its base uses
  the base's left corners and the script's right ones.
- A right-side italic correction stays right-side clearance. It does not become a left overhang
  when the same glyph acquires a left-side attachment.
- Accent attachment and slant are glyph geometry, not reflected child coordinates.

Write bidi expectations from UAX #9, not from Core Text. Use a purpose-built font with known
advances and a distinct glyph ID for each Arabic joining form, list the expected visual glyph
sequence for each case, and never derive it from the library or from another Core Text line.
System fallback fonts are not a glyph-ID oracle. Cover embedded numbers, neutral punctuation,
bracket mirroring, overrides and isolates (RLO/PDF, LRI/PDI), NBSP and narrow NBSP, and
embedding context that survives a soft line boundary.

## Font and image metrics have different units

Keep font design units, em values, points, device pixels, an image's pixels and its intrinsic
logical size distinct, and convert at named boundaries.

For OpenType variation deltas, read the instance Core Text actually selected:

- Request axis values, then take the selected font's actual axis coordinates, normalize them in
  `fvar` axis order and apply the `avar` mapping before interpolating deltas from the `GDEF`
  item variation store. Evaluate the default instance too. A requested axis the font lacks has
  no effect.
- Variation deltas are in design units; Device-table deltas are in device pixels.
- Missing, unsupported, out-of-range or truncated adjustment data keeps the unadjusted value.
  Malformed normalization data disables variation adjustment rather than guessing.

For device corrections, keep geometry resolution-independent by default:

- Make the device scale an explicit layout-time input. Pixels per em is the font size in points
  times output pixels per point, rounded to an integer.
- Freeze corrections into the layout. Drawing an existing layout into a context at another scale
  keeps its measured positions and bounds; rebuild the layout to choose another scale.
- Metric corrections are not glyph-outline grid fitting.

For images:

- Intrinsic logical size is the pixel size divided by the image's scale, or an explicit logical
  size whose aspect ratio may differ from the pixels.
- Host-supplied attachment metrics, such as an italic correction or accent attachment, are in
  intrinsic logical points, never pixels or em units. Validate each field independently.
- Horizontal metrics scale with rendered width divided by intrinsic logical width; changing only
  the height does not alter them.
- Never infer font-like metrics from an image's pixels, its text or its alternative text.

The units are defined by the OpenType [MATH](https://learn.microsoft.com/en-us/typography/opentype/spec/math),
[Device and VariationIndex](https://learn.microsoft.com/en-us/typography/opentype/spec/chapter2#device-and-variationindex-tables),
[variation store](https://learn.microsoft.com/en-us/typography/opentype/spec/otvarcommonformats)
and [coordinate normalization](https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview)
specifications. macOS 27.0 and iOS 27.0 install STIX Two Math (October 2026), so an OpenType
MATH font is available there without bundling one.

## Content language steers glyph choice and line breaking

The Core Text language attribute (`kCTLanguageAttributeName`) steers glyph selection and line
breaking: Han characters in a run tagged `ja` take their Japanese forms. Typesetting and speech
need some language, so take it from the nearest declared language of the text and use a
container's default only as a hint where none is declared. Keep text generated from language,
such as quotation marks around a quotation or case mapping (Turkish dotted and dotless `i`),
tied to a declared language rather than the hint. An empty language tag means unknown and sets
neither.

## Spoken localization must preserve authored content and actual language

Select one complete vocabulary provider before traversal, compose every structural reading
through it, and return the language actually selected so the host chooses the matching voice.

- Matching. Normalize underscores and case (`qaa_zz` becomes `qaa-ZZ`) without adding likely
  subtags. Ignore Unicode and private-use extensions and ICU `@keywords`: `en-GB-u-nu-latn` and
  `en_GB@calendar=gregorian` select `en-GB`. Foundation also normalizes three-letter aliases
  (`fra`, `deu`, `spa`). This is a bounded policy, not a full BCP 47 registry lookup.
- Fallback. Try the exact canonical tag, then the bare language, then the default language for
  the whole reading. Never try a sibling region, strip only part of a script and region pair,
  or borrow default-language words into a selected language.
- Completeness. An incomplete or malformed provider is ineligible, with no partial fallback. A
  new language inherits no default-language vocabulary.
- Reporting. Return the canonical selected tag, not the requested one.
- Composition. Every structural composition belongs to the provider, so word order and
  agreement are per language. Operands arrive already spoken, in source order. Markup supplies
  neither grammatical gender nor the language of an author's token.
- Regions. A regional variant inherits a complete base explicitly and overrides only the terms
  and compositions its evidence supports. Put a regional substitution in the vocabulary, never
  in a rewrite of the finished reading, which would also change author text containing the word.
- Isolation. Providers are pure and thread-safe; catalogs are immutable values passed per call,
  with no global registration. Composer callbacks are trusted host code that must return bounded
  output (see [stack and work bounds](stack-and-work-bounds.md)).

## VoiceOver speaks the language each item and range names

VoiceOver chooses a voice for the language it is given. On iPhone and iPad, give each
accessibility element the language of its words with `accessibilityLanguage`, and mark each part
in another language with `accessibilitySpeechLanguage` in its attributed label. In the iOS 27.0
simulator (October 2026), VoiceOver spoke a French phrase inside an English sentence in a French
voice, and without the attributes spoke everything in its English voice.

- Name the element's language as the one most of its characters are in. Whitespace takes the
  language of the words before it.
- Name no language for an empty tag or for `und`, `mis`, `mul` and `zxx`, which select no voice.
- Characters VoiceOver is not given, such as hidden text or words of an image kept from
  assistive technology, weigh nothing in that majority.

Evidence: [EPUBLib issue #65](https://github.com/vocaro/EPUBLib/issues/65#issuecomment-6164353724).

## Sentinel languages test plumbing, not pronunciation

Test a vocabulary extension API through its public interface, without `@testable`, using a
complete sentinel provider in an RFC 5646 private-use language such as `qaa`. A sentinel is not
a translation; it proves selection and composition. Cover exact script and region matching,
base-language and whole-default fallback, malformed and incomplete providers, registration
precedence, per-call isolation, the reported selected tag, literal author text, and small
thread stacks.

Localized wording needs its own evidence, ranked: a rule for the actual construct, then a test
in the requested language, then a symbol name. Check what an upstream test exercises; one
upstream "Spanish" test ran the English path. Upstream agreement is wording evidence, not proof
of human review, since some upstream entries cite machine translation. Keep "source-supported"
and "validated by a native speaker" as distinct statuses. Listening with host voices and
screen-reader users is usability QA for novel descriptions, not a blanket gate on every sourced
word.

## Primary-strength collation is available through public Foundation APIs

Foundation's `.diacriticInsensitive` comparison option removes marks before language tailoring
can give them primary weight, so it equates Swedish `å` with `a` and Turkish `ö` with `o`, and
the public comparison API has no strength setting. To get primary-strength (base sensitivity)
results with public APIs:

- Compare the strings twice under the locale's collation: once with two distinct private-use
  suffixes appended, and once with the suffixes swapped. If the order flips, the primary
  sequences are equal; if it holds, they differ.
- This works because the Unicode collation algorithm compares all primary weights before any
  secondary or tertiary weight, and private-use characters have independent consecutive implicit
  primary weights with no decompositions or locale contractions.
- Choose suffixes absent from both strings, picking a fresh pair when the text contains them;
  that also stops a primary prefix from straddling the suffixes.
- Compare NFC-normalized copies, so canonically equivalent Hangul and kana match at a window's
  end, and keep offsets in the authored text.
- Do not fold case or width first. Folding changes collation inputs and breaks expansions such
  as `ßs` against `sß`; case and width already vanish at primary strength.

A key prefilter is valid only for collations whose equivalence classes have been recorded. Send
other languages, and text outside the recorded classes, straight to the collator and merge those
candidates in reading order. An unqualified collation then compares every window, which can take
seconds per megabyte.

## Language detection needs spread samples and a letter-density floor

`NLLanguageRecognizer` answers confidently about whatever it is given.

- Sample the whole document with a bounded, deterministic, evenly spread set, for example a
  doubling stride, never a prefix. Front matter is the part most likely to disagree with the
  body, such as a translated title page or an abstract in another language. Avoid randomness so
  a document classifies the same on every device.
- Call a document mixed by tallying samples whose own answer is another language, with a
  minimum count and share, never from the recognizer's runner-up probability.
- Give a sample a vote only above a letter-density floor. A page of frequencies, part numbers
  and citations is Latin script with no language in it, and the recognizer calls it English;
  measured body text sat above 0.5 letters per character and such pages near 0.15.
- Discover a framework's language support from the framework, not a hardcoded list, and cache
  the answer for the process; an OS update needs a new process.
- Framework language tags can match only exactly. On macOS 27 (October 2026), Vision document
  recognition configured French for `fr-FR`, but bare `fr` matched no request identity and the
  recognizer kept its default. Report such a fallback rather than silently substituting a
  region.

## Spelled numerals parse and format through ICU per locale

Read numerals spelled in words with `NumberFormatter`'s `.spellOut` style in the text's own
locale, with lenient parsing, instead of a word table per language.

- Parsing decides where a numeral may start; formatting decides what it may span. ICU spells 100
  as "one hundred" but does not parse a bare "hundred".
- Adjacent standalone small numerals need an explicit composition rule: "runway two five" is two
  numbers, not 25.
- Take grouping and decimal separators from `Locale`. "2.550" is two thousand five hundred fifty
  in Spanish and German; French groups with a narrow no-break space and Swiss German with an
  apostrophe.
- Match digit runs by Unicode decimal digit, so Arabic-Indic and Devanagari numerals count.
- Canonicalize with exact string arithmetic. `NumberFormatter` returns a lossy `Double` for a
  long identifier.

`NLTagger`'s `.nameType` scheme on Spanish text found a personal name in every probe, correct
answers included, so it does not separate proper nouns there.

## Format characters are not whitespace

A Unicode format character (General Category Cf, such as U+FEFF used as a word joiner) is not
`White_Space`, so whitespace collapsing passes it through and it reaches extracted text exactly
as the source wrote it. An embedding tokenizer typically drops it, but string comparison does
not: "1", U+FEFF, "0" is not "10". Remove format characters from every side of a lexical
comparison, inside the comparison only, and keep the original bytes in stored text and records.
Decide per input path whether import strips U+FEFF, and record it; parser choice can also keep
or drop it (see [document parsing](document-parsing.md)).

## Unicode tables differ between runtimes

Each runtime classifies characters from its own Unicode tables. In October 2026, Swift 6.4
(Xcode 27.1, macOS 27.0) and Python 3.12's `unicodedata` (Unicode 15.0) disagreed on 16 Basic
Multilingual Plane code points that newer Unicode assigns as letters and 15.0 leaves unassigned.
A rule implemented in two runtimes needs a parity test over every code point its inputs
contain, recomputed from each runtime's own tables, that fails when an input brings in a
disputed code point.

Evidence: [studywright measurements/audits/judge-quote-blank-rule-parity-2026-10-14](https://github.com/vocaro/studywright/blob/f1d1178e03949b2a6fb20dc6d85618988c0d01b2/measurements/audits/judge-quote-blank-rule-parity-2026-10-14/readme.md).
