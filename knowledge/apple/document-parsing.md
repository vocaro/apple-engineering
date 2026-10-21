# Document parsing

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

These lessons apply to importers, readers and extractors of untrusted documents: ZIP archives
such as EPUB, XHTML and HTML, MathML, SVG and PDF. Unless a line says otherwise they were
observed with the macOS 27.0 (26A428) and iOS 27.0 SDKs in 2026. Layout is in [TextKit
layout](textkit-layout.md), depth and work limits in [stack and work
bounds](stack-and-work-bounds.md), other Unicode lessons in [text layout and
Unicode](text-layout-and-unicode.md), and framework object lifetimes in [framework
lifetimes](framework-lifetimes.md).

## Archive paths need byte-level delimiters and deliberate normalization

- Keep decoded archive keys apart from encoded URL references. A literal `#`, `%` or `?` in a
  file name means something else in a reference, so decode neither before using it.
- A ZIP entry name is UTF-8 when general-purpose bit 11 is set, but `zip` and `ditto` on a Mac
  leave the flag clear. Read a name that is well-formed UTF-8 as UTF-8 with or without the flag,
  and decide deliberately what any other name is (code page 437, or refused when the flag claims
  UTF-8).
- Find `/`, `\`, `:`, `#`, `?` and `.` as bytes or scalars, as an archive and a file system read
  them. A Swift `Character` joins a delimiter with a following combining mark, variation
  selector or joiner, and with a preceding prepended mark such as U+0600. Read by bytes, `../`
  followed by U+0301 is a `..` segment followed by a name that begins with the mark; read by
  `Character` it is no `..` at all.
- These compare by `Character`: `split(separator:)`, `hasPrefix` and `contains` on a `String`,
  and Foundation's `components(separatedBy:)` and `range(of:)` without `.literal`. Split a path
  in its `utf8` or `unicodeScalars` view, or pass it whole to `URL` or `FileManager`.
- Swift's `String ==` is canonical equivalence, so a name's precomposed and decomposed forms are
  one path. Decide whether two entries equal after normalization are duplicates and whether a
  reference in either form names an entry. Foundation hands the file system each name's
  canonical decomposition, not its bytes.
- `URL.pathComponents` drops a byte-order mark (U+FEFF) that opens a name, and reports `..` for
  a name of U+FEFF and two dots, though the file system is given the whole name. Inspect a
  path's bytes or scalars, not its `URL` components.

A path that passes these checks can still need the host's own decision before it is written to
disk: names of dots and default-ignorable characters, such as `..` followed by a zero-width
joiner, which APFS keeps as names but a file system that ignores those characters could read as
`..`; names that begin with a dot or hold control characters or a colon; Windows device names
and a closing dot or space; length limits; names a file system holds equal, by case or as a file
and a folder of one name. Check a path again after any conversion: compatibility normalization
and legacy code pages turn other characters into `/`, `\`, `.` and `:`. Keep symbolic links out
of the destination.

## Normalize text by scalar and by byte, not by Character

- Collapse ASCII white space by its byte. A space followed by a combining mark is one
  `Character`, and trimming or collapsing by `Character` loses the mark. Normalizing on Unicode
  scalars keeps a mark after a space or a no-break space.
- Foundation's `whitespacesAndNewlines` counts the zero-width space (U+200B). Use it to decide
  whether a value is nothing but white space, not to strip characters the author wrote inside
  one.
- A format character (category Cf), such as U+FEFF used as a word joiner, is not white space, so
  a white-space collapse keeps it and it reaches extracted text; what that means downstream is
  in [text layout and Unicode](text-layout-and-unicode.md).
- A key derived from text, such as a font obfuscation key, follows its own specification's rule,
  byte by byte, not the reading normalization.

## Element IDs compare code units, Swift strings do not

`getElementById`, CSS `#id` selectors, SVG references and XML IDs compare an ID code unit for
code unit, so `caf&#xE9;` and `cafe&#x301;` are two IDs. A `String`-keyed table merges them. Key
ID tables by a type that compares and hashes the UTF-8 bytes, and look one up from a `String`
through it. Class names and attribute values in a selector still compare as strings.

## Parser choice can change text

- Foundation's `XMLParser` drops U+FEFF, literal and as a numeric reference, from its character
  callbacks; Apple's streaming libxml2 reader keeps it. Keep sentinel tests for characters a
  parser discards or normalizes, and record the parser and version actually used.
- Structural text (every text node in document order, including elements HTML does not display),
  text recovered through an HTML parser and computed visible text are three different products.
  Say which one an API returns.
- libxml2 writes each message to standard error unless a handler takes it, and raises some, such
  as an encoding converter's error, with no parser context to take them. For each call into
  libxml2, set the calling thread's generic and structured error handlers to one that keeps
  nothing and put the thread's own back after, rather than changing process-wide behavior or the
  host's handlers.
- Apple's libxml2 stops at 257 levels of nesting whatever limit the caller sets. Report a halt
  there as an exceeded limit, not as partial text.
- libxml2 reports and then reads on past names that Namespaces in XML forbids: an element or
  attribute name that begins or ends with a colon or holds a second one, and a processing
  instruction's target with a colon. Decide whether those are errors.
- libxml2 2.14, as bundled with lxml, decodes HTML5 named references. Older libxml2 parses HTML
  4 and reports every HTML5 or MathML element as an unknown tag: tolerate that diagnostic alone,
  and exclude inputs whose parse could differ. The system libxml2's HTML parser reads named
  references from HTML 4's table. In a native reader, read them from the HTML Standard's table
  yourself and turn them into numeric references before an XML parse, rather than loading a
  DTD.
- `NSAttributedString`'s HTML import is WebKit-backed: one conversion loaded 121 Mach-O images,
  WebCore and JavaScriptCore among them. It is not bound to the main thread and fetched no
  subresources, but it has no main-content detection and a large attack surface. `WKWebView`
  extraction runs the document's scripts. `XMLParser` rejects the malformed markup most of the
  web is. For web pages use a parser that implements the HTML Standard's tree building.

## libxml2's HTML parser is not the HTML Standard

Recovering malformed XHTML through libxml2's forgiving HTML parser gives libxml2's tree, which
is not always the HTML Standard's:

- A `<` that opens no tag (`x < y`, `p <.05`) is text in HTML; libxml2 alone discarded what
  followed it. In HTML a tag opens only before an ASCII letter, `/`, `!` or `?`.
- libxml2 can end a script or style at an end tag that directly follows its start tag, reads
  `<!-->` as a comment that is still open, and, where a self-closing `<html/>`, `<head/>` or
  `<body/>` is out of place, ignores it and lets its `/>` close the element that is open, which
  can end the body early. What it then builds after the body lands in a second body or a new
  root.
- In HTML an early `</body>` or `</html>` closes nothing, a comment also ends at `--!>`, and an
  `&#` with no digit stays literal.
- Its named references are HTML 4's.
- Give it UTF-8. Decode UTF-16, UTF-32 and declared encodings first, so that an unclosed tag
  cannot change a document's characters. It does not read an HTML `<meta charset>`.

Where the difference matters, repair the input with a bounded pass that follows the HTML
Standard, and test the recovered tree against it.

## Screen untrusted markup before any parser sees it

- Nothing in the document executes: no script engine, no web view. Count scripts and disclose
  them.
- Refuse document type declarations, entity declarations and internal subsets in any encoding
  before parsing, so that no entity expands and nothing external loads. Tell real declaration
  syntax from comments, CDATA, processing instructions and quoted identifiers. An ordinary
  external DOCTYPE identifier may be allowed but is never fetched.
- Decode UTF-16, UTF-32 and declared legacy encodings (UTF-7, SCSU and EBCDIC among them) with
  the parser's own converters before inspecting markup. Refuse an ambiguous switch from an
  initially detected wide encoding, and an encoding you cannot decode.
- Cap attribute occurrences per element, namespace declarations and duplicates included, with a
  linear preflight before strict or recovery parsing. In HTML, treat a script or style end
  marker as markup even inside an apparent quoted value or comment, because malformed raw-text
  endings move libxml2 into another context.
- Treat markup left open at the end of the input, a tag cut in half or a comment, CDATA section
  or declaration never closed, as unsafe: that is where a scan and a parser most easily disagree
  about what the bytes are.
- Bound input bytes, depth, nodes, text units, extent and output items independently, and bound
  what references expand separately from the input's size. Derived outputs, such as spoken text,
  obey the same bounds.
- Resolve every reference inside the opened snapshot, and never fetch. A component that cannot
  judge a reference, such as an image `src` inside a formula, passes it through as written; the
  host resolves it against the document and refuses what the document may not load.

## Bound archive work by decoder calls, not by output alone

A small output does not bound work. Repeated empty streams, overlapping or repeated local
headers, and one stream shared through several headers multiply the work an archive costs.

- Charge each local header its exact size (30 fixed bytes, its name and its extra field) against
  the archive's byte count during the directory scan.
- zlib's `inflate` continues until its input is used up, its output is full or the stream ends.
  Call the consumer after every call, including those that produce nothing, with at most one
  chunk of input and of output per call. Charge one chunk per consumer call against the
  archive's bytes plus the bytes actually produced, with one partial-chunk allowance per entry.
  After admitting `E` entries and producing `O` bytes from an archive of `A` bytes, successful
  calls are bounded by `floor((A + O) / chunk) + E`.
- That bounds processing steps without observing the decoder's input offset, stops repeated and
  shared streams, and still reads streams that end early or declare sizes beyond the archive.

## Apple's Compression inflater is not deterministic on damaged streams

ZIPFoundation 0.9.20 inflates through Apple's Compression framework. For some Deflate streams
whose block header is damaged, that decoder read stack memory it had not set, so the same
archive was refused one way on one open and another way on the next (macOS 27, 2026). The
system's zlib refused the same streams as damage on every open, as it does a stream cut short.
Inflate untrusted archives with zlib, and keep a seeded mutation run that opens each mutant
several times in one process, so that nondeterminism shows as a difference between opens.

## Native renderer containment needs more than a byte limit

Observed with resvg 0.48.1, a Rust SVG renderer, behind its C API:

- A panic that reaches an `extern "C"` function aborts the process before any catch outside it
  can run. Wrap each exported function in `catch_unwind` around an inner function with the Rust
  ABI, and build the release profile with `panic = "unwind"`.
- After a caught panic, dispose of the parsed tree under a per-handle lock, and have every later
  call on that handle return its defined failure (false, an empty size). Keep the host's panic
  hook, so the diagnostic still reaches standard error. The lock is never poisoned, because no
  unwind crosses the guard.
- Caught panics do not contain stack exhaustion, allocation failure or an abort, and do not
  bound expensive rendering that succeeds.
- Screen costs before rendering, from the pinned renderer's own sources: what it builds again
  per shape, per text run, per marker vertex and per reference. Overcharge rather than model,
  and refuse an input where telling a cheap case from a costly one would mean reimplementing the
  renderer, as for a reflecting or repeating linear gradient, which can panic when it has no
  length. Count text in the renderer's own units (Rust `str::chars`), per run and across the
  drawing, counting again wherever a reference expands it.
- The renderer follows masks, clip paths and `<use>` by calling itself on the process stack and
  guards against loops only in part. Count references toward the depth limit, and refuse
  reference loops it does not unlink.
- Derive the screen again whenever the vendored version changes.

The resource-conversion cost measurements are in an [EPUBLib issue
comment](https://github.com/vocaro/EPUBLib/issues/176#issuecomment-6159294552).

## PDFKit's text layer and page model have gaps

Observed on macOS 27 (PDFKit 1537 on macOS 27.0 26A428 where a build was recorded):

- PDFKit's page string can hold U+FFFC where a page places content of another PDF (`/PlacedPDF`
  marked content). Repair narrowly and fail open: merge recovered text only when it is nonempty
  and every source code mapped, with bounded CMap and ToUnicode parsing, and otherwise keep
  PDFKit's string byte for byte.
- PDFKit substitutes fonts: an embedded font reports Helvetica as both its family and its font
  name. For headings, font size is the only typographic signal left.
- PDFKit has no API for where an image is drawn. An image XObject painted by `Do` fills the unit
  square, so the current transformation matrix at `Do` is its placement rectangle. Walk the
  content stream with `CGPDFScanner`, tracking `q`, `Q` and `cm`, and descend into Form XObjects
  applying each `/Matrix`, or a page full of images reports none. Count inline images (`BI`,
  `ID`, `EI`) apart, and keep "no images" apart from "never descended".
- PDF user space has y increasing upward, so a caption below its figure has the lower y.
- Concurrent first builds of `PDFPage.attributedString` ended the process; see [framework
  lifetimes](framework-lifetimes.md).

## Core Graphics silently drops some JBIG2 masks

Measured on macOS 27.0 (26A428), October 2026, against poppler 26.04.0 and MuPDF 1.28.2:

- For some JBIG2 image masks `CGPDFStreamCopyData` returns a full-length buffer of 0xFF bytes, a
  mask that shows nothing, and `drawPDFPage` draws the page without the ink, reporting nothing.
  Ten of 1,677 measured masks failed so; poppler and MuPDF decode them all.
- Every failing mask has a symbol dictionary that refines or aggregates symbols and whose count
  of input and new symbols is an exact power of two, and a synthetic stream with a count of four
  fails the same way. That is what a decoder gives when it reads one bit too many at a power of
  two; the cause is inferred, not confirmed.
- An all-0xFF result is also what a blank mask decodes to, so the signature alone decides
  nothing. Decode the stream independently to tell a blank mask from a failed one.
- Core Graphics returns a JBIG2 stream only decoded. To find its encoded bytes, open the
  document over a data provider that records what Core Graphics reads, and take the stream's
  data from where decoding began for its stated `/Length`, checked against `endstream`.
- Core Graphics crashed when a process's first JBIG2 decodes through that call were made on two
  threads at once, and not once one had finished. Serialize them.

The measurements are in a [PDFReflowLib
record](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/jbig2-mask-repair/record.md)
(private).

## Vision document recognition gives line order, not structure

Observed on macOS 27 in 2026, on public-domain textbooks and scans; the figures were not
recorded with an OS build:

- `RecognizeDocumentsRequest` returns ordered lines (`DocumentObservation`), so the caller need
  not sort text boxes. Its order beats a bounding-box sort, but against a born-digital
  document's own character order its lines sat in the author's relative order 0.809 and 0.908 of
  the time on two two-column documents, with 18.7% column switches against PDFKit's 4.3%.
  PDFKit's order is the text layer; do not route born-digital pages through Vision for order.
- Vision exposes no heading level. `isTitle` fired once per page, on the first line in reading
  order whatever it was (on one page a figure caption), and paragraph grouping is
  undifferentiated.
- A request cancelled at a deadline may keep its suspended task alive until the process exits.
  Give each page a deadline that does not await the cancelled request.
- The first recognition in a process cost about 55 s and later pages about 0.35 s each.
  Resolution had no measurable effect on clean text between 100 and 300 DPI. Budget warm-up
  apart from throughput in any timing. How Vision caches its compiled models, and why the
  executable's name can change its output, is in [framework execution
  identity](framework-execution-identity.md).
- Recognition can succeed with part of a page unread. Measure the writing on the raster handed
  to Vision against the lines returned, recognize the page again in overlapping bands when the
  reading does not account for the page, and keep whichever reading covers more.

## Measure extraction against a naive and a reference extractor

Extraction quality needs no model and runs in seconds, so measure it before blaming retrieval or
generation:

- Report three arms per document: the extractor that ships, a naive one (such as pypdf), and a
  reference pipeline. A metric where the shipped arm sits with the naive one and far from the
  reference names a missing cleanup rule; where all three agree the number describes the
  document.
- Score every arm over the same pages, or say which are sampled: rare events such as column
  inversions disappear from a sample.
- Keep detection measures apart from residual ones. A header and footer detector run again on
  stripped text finds whatever now sits at the page edge and never converges. To ask whether a
  cleanup rule worked, check whether the strings it removed still reach the chunks.
- Ask whether a keyed passage is in the extracted text before asking how retrieval ranks it. A
  key no chunk contains is extraction damage; report it apart from ranking rates.
- Build the index you score in the same session from the arm you ship, and say which arm built
  it.
- Gate an extractor relative to the naive one (fail when it loses a passage the naive one kept),
  not absolutely: a passage every arm misses is the document's problem, and a gate nobody can
  make green gets switched off.
