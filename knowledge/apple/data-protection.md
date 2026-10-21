# Data protection

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Data protection during locked execution

Explain why a task can have runtime yet lose access to its inputs or output staging, how working-directory file protection is set, and how to verify the actual app under lock.

[Sources/PDFReflowKit/JobDirectory.swift](https://github.com/vocaro/PDFReflowLib/blob/4a625316a5b4a4aafea5134dfcfec1a6991e9cbd/Sources/PDFReflowKit/JobDirectory.swift) sets the shared conversion job directory to `completeUntilFirstUserAuthentication`. That is the selected working-file policy for these clients; another product must assess its data requirements rather than copy the protection class automatically. StudyWright also records two API traps: retaining the exclusive creating descriptor for a completeUnlessOpen staging file, and passing a typed FileProtectionType rather than a raw string through an untyped attributes dictionary. [studywright doc/components/ingestion.md](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/doc/components/ingestion.md)

## Shared implementation

FileProtectionLib provides typed attributes, class read-back, directory creation and
exclusive creating descriptors. Its caller selects protection classes and migration
policy. StudyWright and conversion working directories intentionally differ.
