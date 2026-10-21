# Framework lifetimes

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Framework safety includes object destruction and font lifetime

PDFKit's attributed-text extraction (`PDFSelection.attributedString`,
`PDFPage.attributedString`) can end the process with an Objective-C exception, an
`NSInvalidArgumentException` for a nil `NSFont`, when separate documents are read on several
threads at once. Observed on macOS 27.0
(26A428) with PDFKit 1537, September and October 2026, with public SDK calls alone; the first
attributed page strings two threads built together aborted about 3% of aligned trials.

A lock around the extraction calls is not enough. The attributed strings and the fonts their
runs carry are autoreleased, so one thread freeing a just-finished extraction's objects races
another thread's PDFKit call already inside the lock. Serialize extraction with one gate shared
by every instance in the process:

- Run each protected extraction inside its own `autoreleasepool` and drain it before unlocking,
  so the next waiter enters PDFKit after the previous results are freed.
- Hold the gate only for the synchronous framework calls, never across progress callbacks, OCR,
  graphics work, writing or an `await`.
- Make test code's fonts, Core Text drawing and PDFKit reads through the same gate, and fail the
  build with a static check on any such call outside it.
- Wait for the gate with timed attempts that observe task cancellation. A waiter occupies a
  cooperative-pool thread; see [Swift concurrency](swift-concurrency.md).

The gate trades concurrent throughput for safety and covers only the library's own calls. A
finite passing campaign is bounded evidence, not proof that all concurrent PDFKit use is safe.

Evidence: [PDFReflowLib measurements/pdfkit-gate-drain](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/pdfkit-gate-drain/record.md).

## A host's font work can abort a gated PDFKit read

A gate orders only the reads that take it. On the Mac, a host thread working with text during a
gated extraction still aborted it. Observed on macOS 27.0 (26A428) with Xcode 27.0 (27A266a),
September 2026:

- Making fonts in the face the PDF uses aborted the gated read in nearly every process. Fonts
  in other faces aborted none.
- A host's own PDFKit attributed reads aborted one side or the other in nearly every process.
- System-font text measured and drawn with Core Text, or SwiftUI `Text` rendered to an image,
  aborted it rarely.

On iOS and iPadOS 27.0 (24A435) devices and in the iOS 27 simulator nothing aborted, with or
without a gate. Those zeros bound only the tested devices, fixture and denominators.

Holding one live font of the PDF's face for the whole run prevented every such abort, and the
SDK-only reproduction too. Any size of the face worked. Another face, even of the same family,
did not, and neither did a font of the face made and released before the run. The mechanism, a
face's last live font torn down on one thread while PDFKit asks for another size of it on
another, is inferred from which held font prevents the abort. It was not observed.

Apply a face hold within these limits:

- Hold installed faces, which a host can also make, for the life of the process. Releasing them
  at the end of each job tore the face down under readers still using it.
- Hold embedded faces for the job, adding each face the attributed runs carry. No host can name
  them, so the first read of an embedded face happens before the hold has it.
- A first-use race remains: a host making the exact face in the moments a process first uses it
  still aborted some reads. Once a face had been used, even if let go, it aborted none.
- Keep the gate and its drain. Whether a held face makes the drain unnecessary is untested.

Evidence: [PDFReflowLib measurements/held-faces](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/held-faces/record.md).

## Concurrency campaigns need controls and complete records

A stress campaign against a framework's thread safety:

- Compare the main thread, one background thread run serially, and several threads started
  together. No framework document, selection or attributed string crosses threads, and each
  iteration opens its own document inside its own autorelease pool.
- Build an SDK-only control from the framework calls alone, with no library source, that can
  reproduce the abort. It is the positive control for the campaign's ability to see the failure.
- To test host interference, run the gated reader while the main thread repeats one kind of
  host work (fonts in the same face or others, system-font text, SwiftUI `Text`, the host's own
  framework reads), with the ungated reader as the control.
- Use a new output directory per campaign. Keep every child's exit code, standard output and
  error, and input, producer and binary identity. Never retry a failed trial. On a timeout,
  kill and reap the child's process group.
- A zero exit without a complete, matching positive-control receipt is a failure.
- Report a passing campaign with its denominators. It bounds the risk; it does not prove safety.

## PDFKit leaks every attributed string it returns

Observed on macOS 27.0 (26A428), September 2026, in release builds: every
`PDFSelection.attributedString` result leaks with its runs, fonts and attribute dictionaries.
`leaks` reports them as `NSConcreteMutableAttributedString` roots allocated under that call.
Only Apple can release them, so make fewer requests:

- Request one attributed string for the union of a page's line selections and slice each line
  out of it. That left about a twelfth of the leaked objects, with byte-identical output.
- First check that the union's plain text can be sliced back into the original lines, in order.
  When it cannot, fall back to one request per line rather than making an unusable request.
- Bound growth with the leak count and the default malloc zone, not the physical footprint,
  which swings by hundreds of MiB as the allocator reclaims freed pages.

Evidence: [PDFReflowLib measurements/pdfkit-repeated-conversions](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/pdfkit-repeated-conversions/record.md).

## Repeated conversions in one process accumulate framework-retained objects

An app that converts several documents in one process keeps whatever the frameworks retained or
leaked from each. One fresh process per conversion does not show it, so measure both:

- Run the public API several times in one process over pinned inputs. After every round, print
  the physical footprint, peak RSS and default malloc zone, and on the Mac a `leaks` count.
- Provide the same harness for an iOS simulator.
- Measure memory in a process of its own. Package test suites run in parallel in one process
  and cannot attribute memory, so in the suite check the request shape (one attributed request
  per page) instead of the bytes.

See [measurement](../../guides/measurement.md) for fresh-process memory gates.

## PDFKit loads a tagged document's whole structure tree on first text layout

Observed on macOS 27 and on an iPhone with iOS 27, September 2026: the first PDFKit text-layout
call on a page that carries `/StructParents`, in a document whose catalog has
`/MarkInfo /Marked true`, loads the document's entire structure tree.

- `numberOfCharacters`, `string`, `attributedString`, `selection(for:)` on any rectangle and
  `characterBounds(at:)` all trigger it. Rendering a thumbnail does not.
- On a large tagged handbook it allocated about 489 MiB of small objects, once per process.
  Later pages cost under 4 MiB, including after the document was reopened.
- Releasing the document freed most of it, but about 204 MiB of empty, fully fragmented
  small-allocation regions stayed resident, and `malloc_zone_pressure_relief` did not return
  them.
- Hiding the structure tree from PDFKit changes the extracted text, so it is not a mitigation.

Budget the first text layout of a tagged document as the extraction peak, on devices too.

## Streaming requires explicit ownership and backpressure

Keep framework objects in a small window and carry values forward:

- Keep only a few framework page objects alive, reopen the document between passes, and carry
  value types forward, never framework pages or selections. Release indexes built for
  extraction when extraction ends.
- Separate spatial evidence from the logical output model. The model holds URLs and
  identifiers, never decoded images or large byte buffers. Spill intermediate pages to disk.
- Let the consumer take parts as the producer makes them, so neither side holds the whole
  document. Stream assets straight into archive entries. A persistent model or a second
  consumer needs its own explicit lifetime contract.
- Retain the workspace until the consumer finishes.
- Deliver progress through awaited callbacks for ordering and backpressure, and never hold an
  unrelated framework lock across one (see [Swift concurrency](swift-concurrency.md)).

Bound disk use while packaging. Remove each staged entry, closing its handle first, as soon as
the archive writer has archived it; keep a resource that several entries reference until its
last entry is archived; remove all staging on cancellation or failure. Packaging then needs at
most `B + L + H` logical bytes, for staged entry bytes `B`, largest entry `L` and archive
overhead and compression expansion `H`, instead of every entry beside the finished archive.
Many small assets approach one copy of the output, but one large entry can approach two
(`L <= B`). A caller holding only an output-byte budget reserves twice that budget plus
overhead, filesystem allocation rounding, and space for the source and any temporary page store.

## An autorelease pool does not release what the run loop retains

Observed on macOS 27, October 2026: synchronous AppKit text layout, with each page made inside
an autorelease pool, left native text views and their TextKit layouts retained by AppKit's
run-loop blocks. Turning the run loop released them. A test process can therefore keep running
for minutes after its last test passed while that work drains.

- Turn the run loop between batches of AppKit view work that should free memory.
- Wait for the process's exit status, not the suite's "passed" line. When redirecting output,
  run with `NSUnbufferedIO=YES` or under `script -q`, so the final summary is not lost in a
  buffer if the process is stopped.

## Native progress trees tie completion to object lifetime

Foundation's OS 27 progress composition (`ProgressManager`, `ProgressReporter`, the noncopyable
`Subprogress`), probed with real Foundation objects on macOS 27.0 (26A428) with Xcode 27.0
(27A266a) and in the iOS 27 simulator, September 2026:

- Weighted child allocations reproduce fixed stage weights.
- Releasing an unfinished child completes its allocation: a parent at 0.2 advanced to 1 when its
  child at 2 of 10 units was released. Scope exit is not evidence that the work finished.
- A retained reporter keeps its child alive at its fraction after the manager variable is
  cleared. Releasing the reporter then completes the parent.
- Raising a total lowers the fraction: 5 of 10 becoming 5 of 20 moves 0.5 to 0.25. Monotonic
  estimates need a policy.
- Count mutation is synchronous with no awaited client callback, and an observed reporter is
  current state, not an ordered event stream. Conforming to `Observable` delivers no events.

Use a progress tree for a composed UI estimate, with explicit ownership of every child and
reporter, and decide success from the returned result or thrown error, never from the fraction
reaching 1. Keep an ordered, awaited callback where the client must see every stage in order.
Probe tests retain successful children until their fractions are checked, so deinitialization
cannot disguise incomplete work.

Evidence: [PDFReflowLib measurements/progress-composition](https://github.com/vocaro/PDFReflowLib/blob/dc89a4eccecb99943661709887fd2a61a1a51b29/measurements/progress-composition/record.md).
