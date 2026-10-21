# Embedding correctness

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Concurrent ML workloads can silently corrupt results

The recorded Core ML embedder using all compute units produced wrong vectors without throwing while on-device FoundationModels generated on the GPU; concurrent prediction could also deadlock. The adopted CPU/Neural Engine route removed the observed corruption in the reported trials. Test output correctness under the actual competing workload, not just single-request latency.

[studywright doc/components/embedding.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/doc/components/embedding.md). Scope the workaround to the recorded model/runtime/hardware; a finite passing campaign is not universal safety for every Core ML backend.

## Model compatibility includes preprocessing semantics

Equal tensor dimensions and unit-length vectors do not establish compatibility. Check checkpoint, tokenizer family, pooling, normalization, sequence limits and serialization. Token budgets must count the full input, not its already-truncated form. A fixed-length Core ML adapter should not add a second inconsistent padding/truncation pass.

[studywright doc/components/embedding.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/doc/components/embedding.md). Also capture environment-sensitive floating-point serialization and the distinction between value identity and byte identity. Keep the actual model configuration with the artifact.
