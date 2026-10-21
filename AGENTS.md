# Shared engineering repository

Read agents/core.md and the capability relevant to the change. This repository is private;
private project code and qualification evidence must not be published publicly. Keep the
Python core standard-library only. Source lives in src/python, src/swift and src/objc.
Runtime libraries have separate repositories and do not import this toolkit.

Run `python3 -m unittest discover -s tests -v` for Python changes. Preserve original upstream
regression suites when extracting code. Test positive and negative controls and wrappers.
Never run Mac VoiceOver, launch a debugger, or take over the owner's screen here. Shared
resource actions consult current policy. Stage explicit file lists; integrate onto main.
