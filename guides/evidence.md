# Evidence

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Public and private destinations

Review source and payloads before publishing a record. Private integration logs, personal
device identities and raw private transcripts belong in their private owning project or the
private apple-engineering-evidence archive. Public articles and issues can retain reviewed
methods, source identities, results and limits. Private provenance links are supplemental;
public contributors must be able to run the tools without those records. See
[public access](public-access.md) for the repository boundary.

## Evidence collection

Sequential xcresult export, before/after app/test/manifest identities, allowlisted retention, redaction, source reconstruction, hash indexes and offline observer replay.

[Pagepour scripts/reader-evidence/README.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/scripts/reader-evidence/README.md) and [studywright doc/testing.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/doc/testing.md#python-tests-and-historical-evidence). Keep evidence profiles local and retain original observations; hashing a later build cannot establish what ran earlier.

## Honest outcome states

Separate passed, failed, skipped and unmeasured; require an independent positive control before blaming a missing framework capability; make opt-in tests visibly skip.

[PDFReflowLib tools/run_swift_tests.py](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/tools/run_swift_tests.py) and [studywright doc/testing.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/doc/testing.md#measurement-gates). Preserve failures; infrastructure unavailability cannot become green coverage.

## Independent correctness checks

Expectations from standards and independent decoders, preserved upstream assertions, seeded fuzzing, optimized-build tests and explicit worker-stack coverage.

[MathMLLayout doc/external-validation.md](https://github.com/vocaro/MathMLLayout/blob/8e038411260803c3b272dff590129516e7d846d7/doc/external-validation.md) and [MathMLLayout doc/testing.md](https://github.com/vocaro/MathMLLayout/blob/8e038411260803c3b272dff590129516e7d846d7/doc/testing.md). Share importer/report/gallery patterns; MathML geometry and fonts remain MathMLLayout’s domain.

## Corpus provenance

Manifest-driven official-source retrieval, committed identities, byte verification, offline gates, licence notices and owner-supplied paths for blocked automated downloads.

[EPUBLib AGENTS.md](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/AGENTS.md#test-corpora), [PDFReflowLib doc/corpus.md](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/doc/corpus.md) and [studywright AGENTS.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/AGENTS.md#security-licenses-and-dependencies). Share eligible public corpus definitions where consumers adopt them; current collection approvals and source-use restrictions do not transfer automatically.

## OS and model drift measurements

Record OS/toolchain/input identities, use served positive controls, compare on the same platform, retain typed errors, use repeated trials and separate deterministic gates from costly qualification.

[studywright doc/measuring.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/doc/measuring.md#7-when-to-run--the-os-release-regression-protocol) and [studywright AGENTS.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/AGENTS.md#development-and-verification). An optional FoundationModels module can carry the model-specific knowledge; spending grants, quota state and launch commitments remain local.
