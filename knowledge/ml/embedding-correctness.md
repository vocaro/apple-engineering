# Embedding correctness

These mechanisms and lessons apply when the stated capability is present. Original measurements
establish their recorded platform and workload; they do not establish universal behavior on
later operating systems or in a different application.

## Concurrent ML workloads can silently corrupt results

A Core ML sentence embedder configured with all compute units shared the GPU path with on-device
FoundationModels. Embeddings computed while the language model generated were silently corrupted
(cosine 0.64 to 0.82 against fixture vectors in 5 of 5 runs, nothing thrown), and concurrent
prediction could deadlock. With `.cpuAndNeuralEngine`, 0 of 5 runs corrupted. A single embedding
cost about 18 ms instead of 9 ms, but batch ingestion was faster on that route (64 chunks in
448 ms concurrently against 708 ms serially on the GPU path). Observed on a macOS 27.0 beta,
August 2026.

Test output correctness under the actual competing workload, not only single-request latency,
and pin the compute-unit choice in a test. Scope the workaround to the recorded model, runtime
and hardware: a finite passing campaign is not universal safety for every Core ML backend. Keep
the operational rule as well: run one model workload per machine, because the workaround does
not stop two generative processes from starving each other ([FoundationModels and Private Cloud
Compute](foundation-models.md)).

Core ML already parallelizes inside a prediction, so outer concurrency buys less than core
counts suggest: concurrent embedding during ingestion measured 1.39× on an iPad Air (M3) over
128 chunks on an iPadOS 27 beta with identical vectors, too little to justify an out-of-order,
cancellation-cooperative loop.

## Model compatibility includes preprocessing semantics

Equal tensor dimensions and unit-length vectors do not establish compatibility. The checkpoint
identity, dimension and maximum sequence length decide whether two embedders produce
interchangeable vectors; pooling and normalization are declared constants that both producers
must reproduce. Validate all of them when an index loads (schema version, model, dimension,
normalization, pooling, maximum sequence length and every vector's dimension), and refuse a
mismatch: a mismatched checkpoint silently corrupts retrieval. A recorded identity that is
absent means unknown and never matches; never backfill it from the embedder now running.

- **Read pooling from the model's configuration.** Reading a CLS-pooled model with mean pooling
  returns plausible unit vectors that rank badly, which no shape check sees.
- **Read tensor names from configuration**, feed token-type ids only when the model declares
  them, and check that the tokenizer's family (WordPiece or BPE) matches the model.
- **Count with the same tokenizer that truncates**, in the embedder's own vocabulary without
  added special tokens, so a counted budget can never disagree with truncation.
- **Pad and truncate once.** Core ML needs fixed-length inputs; let one tokenizer configuration
  own padding and truncation, with no second pass in the adapter. Count the full input across
  zero-stride overflow windows, so chunking never mistakes a truncated count for the original
  length.
- **Make embed-time truncation unreachable.** Segment sentences with `NLTokenizer`, which
  survives abbreviations and section numbers that shred a regex, hard-split any over-budget
  sentence on word boundaries, and re-count every piece.
- **Natural Language is not a substitute embedder.** `NLEmbedding` provides English-only
  sentence vectors, and `NLContextualEmbedding` provides no sentence vector.

Keep the actual model configuration with each artifact.

## Embedding bytes depend on the execution environment

Embedding was deterministic within a Core ML execution environment, not across environments. A
process that cannot open `IOSurfaceRootUserClient`, such as one inside an agent's default
sandbox, took the CPU path with last-bit differences (median 8 ulp, at most 1.8e-7). Six-decimal
serialization turned those into ±1e-6 on about 2% of components, so the vector file, the index
fingerprint and the package manifest changed while retrieval did not. Repeated Core ML
predictions also differed at the Float32 level with the same source, text, chunks and
checkpoint. Observed on a Mac17,6 with macOS 27.0 (26A428) and Xcode 27.0 (27A266a), September
2026.

- Name the build environment and refuse to build in a process that disagrees with it.
- Treat exact vector bytes, index fingerprints and manifests as capture identities of one build,
  not content identities. Freeze a content digest and the chunk-text topology when the claim is
  about content.
- A Core ML semantic identity that normalizes protobuf map ordering and the package manifest's
  UUIDs and order, while keeping the parsed specification, operation graph and compiled MIL
  exact, is stable across exports. Prove it with two full exports and repeated compiles, not
  synthetic byte swaps.
- Re-score from retained vectors. Re-embedding recorded text on another machine can flip a
  verdict that sits at a similarity threshold.

## Summation order and unstable sorts reorder near ties

`cblas_sgemv` and `vDSP_mmul` sum in a different order from a per-vector `vDSP_dotpr` scan and
land 1 ulp away, which reorders near-ties and turns an exact parity test into a tolerance.
Swift's `sort` is not stable, so equal scores can come back in any order. Pin tie order (for
example, corpus order among equal scores) and keep the same kernel on both sides of a parity
test, so retrieval parity stays bit-identical at every k.

## Rerank inside the retrieved set, not beside it

Dense embeddings are strong at paraphrase and weak at vocabulary; BM25 is the reverse. Fusing
the two full rankings raised rank-1 precision but cost recall at the k the engine feeds the
model (hit@8 fell from 0.75 to 0.66 on one handbook), because fusion promotes what both rankers
like and evicts what only the dense ranker found. Reranking the dense top-k with BM25 leaves the
retrieved set identical, so recall cannot regress by construction, and gained 13 points of
hit@1. For retrieval-augmented generation, recall at the retrieval k is the constraint and
rank-1 precision the objective. Assert the invariant in the measurement: recall at every k at or
beyond the rerank depth is bit-identical between the arms.

## Probe what a checkpoint encodes with a crossed design

To ask whether a checkpoint can separate sentences that differ in one property, such as the name
a sentence is about, measure the cone: the mean pairwise cosine within a set of sentences that
differ only in that property. One minus that cosine is the whole budget any property-sensitive
rule has to spend. Cross the factors (for example, name language × frame language), because
either factor alone is confounded; in one multilingual checkpoint the frame's language moved the
cone from 0.880 to 0.950 while the name's language moved it by 0.009. Run an English-only
checkpoint as the control: showing no frame effect at all is what absent geometry looks like,
and it reveals an attractive score in another language as compression rather than competence.
