# Maintenance

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Shared-machine operating rules

A short common policy covering owned processes, device identity, foreground input, debugger restrictions, current operational rules and preservation of peer work.

[EPUBLib AGENTS.md](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/AGENTS.md) and [Pagepour AGENTS.md](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/AGENTS.md). Keep actual host inventory and authorization outside the generic rules.

## Concurrent Git integration

Fixed base commits for comparisons; explicit staging; respect for concurrent edits; verification of the integrated tree; confirmation that an issue’s fix actually reached main.

[EPUBLib AGENTS.md](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/AGENTS.md#branches) and [PDFReflowLib tools/check_closing_commits.py](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/tools/check_closing_commits.py). Evaluate PR versus direct-main integration as a potential portfolio default with justified exceptions.

## Documentation and evidence ownership

Current behavior in subject documents; repeatable procedures in runbooks; issue/release evidence at its owning destination; historical observations preserved by revision.

[EPUBLib AGENTS.md](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/AGENTS.md#where-a-write-up-goes) and [studywright AGENTS.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/AGENTS.md#issue-workflow). Promote a common information policy; parameterize storage paths and preserve historical records.

## Documentation checks

Exact-case local links, instruction-size checks, snippets taken from compiled examples, generated test counts, fixture notices and historical-issue exceptions.

[studywright scripts/lint-docs.sh](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/scripts/lint-docs.sh), [EPUBLib scripts/check-docs.py](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/scripts/check-docs.py) and [PDFReflowLib tools/update_doc_counts.py](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/tools/update_doc_counts.py). Reuse checker engines; keep paths, markers and exceptions local.
