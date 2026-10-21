# Packaging

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Swift package distribution checks

An immutable revision-based consumer, separate tests for extracted packages, dependency-closure checks and meaningful negative controls.

[PDFReflowLib tools/check_revision_package.py](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/tools/check_revision_package.py) and [EPUBLib scripts/check-modules.py](https://github.com/vocaro/EPUBLib/blob/b63d9027c4d89b16c9b980f3e9dd9ec9ec172d50/scripts/check-modules.py). Keep declared module/product contracts local; a local-path client alone is insufficient.

## Distribution artifact inspection

Read actual signatures and entitlements, inspect packaged privacy/resource bundles, verify extension boundaries and check absence of development hooks in the built archive.

[Pagepour scripts/validate-mac-archive.py](https://github.com/vocaro/Pagepour/blob/e8cce638223f4751f4365b61ade888c3eeefb4bd/scripts/validate-mac-archive.py), [PDFReflowLib tools/check_privacy_manifest.py](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/tools/check_privacy_manifest.py) and StudyWright’s release checker family. App IDs, resource requirements, reason-API catalogues and store claims remain configurable and require maintenance.
