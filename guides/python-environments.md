# Python environments

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Python native-dependency preflight

A cached wheel can carry Gatekeeper quarantine into every new worktree. Whichever process first
imports a quarantined native extension gets a blocking macOS dialog whose default button deletes
the library. The environment then fails as a dependency bug, such as
`cannot import name '_imaging' from 'PIL'`, rather than as the security prompt it was, and the
dialog takes the keyboard from the owner and every other session.

Prepare an environment before anything imports from it:

1. Sync the locked environment with an absolute project path, so the tool cannot select an
   environment from the invoking shell's directory or variables:
   `uv sync --project /ABSOLUTE/PROJECT --locked`.
2. Inspect every native file with the system interpreter, importing nothing. The toolkit's
   inspector reads the `com.apple.quarantine` attribute of every file in the environment's `bin`
   and of every `.so` and `.dylib`, wheel-private libraries included; it exits 0 when clean, 1
   when something is quarantined and 2 when it cannot inspect:

   ```sh
   /usr/bin/python3 "$VOCARO_ENGINEERING_ROOT/src/python/vocaro_engineering/native_python.py" \
     /ABSOLUTE/PROJECT/.venv
   ```

3. On 1, repair once by reinstalling the exact locked bytes from fresh downloads
   (`uv sync --project /ABSOLUTE/PROJECT --locked --reinstall --no-cache`), then inspect again.
   On 2, or when the repair or the second inspection fails, stop before any import and report
   it.
4. Put the synced environment's `bin` first on PATH, so nested shell gates that call `python3`
   cannot fall back to the host interpreter.

Never remove the quarantine attribute, and never disable Gatekeeper or another security check.
Run tests through the wrapper that performs this preflight rather than through the test runner
directly. The toolkit implements inspection only; the sync and repair stay in each project's
adapter, which knows its environment's contents.

## Dependency identity in receipts

A receipt that pins a whole lockfile and project file identifies the entire development
environment, so a change to a development tool makes every receipt stale even where the measured
producer never imports that tool. Pin a projection instead: the runtime dependency set resolved
from the lock and project files (each package's name, version, source, edges and artifact
hashes, plus the project's runtime specifiers, Python floor and build system), narrowed to what
the producer imports, or widened to the development extra when the recorded value is itself a
development tool's verdict.

Historical receipts keep their whole-file identities, which resolve at their recorded revision.
A change to a runtime dependency requires fresh qualification of the behavior that depends on
it, without rewriting the older observation.

## Native packages follow the OS

Native wheels can stop loading on a new macOS: on macOS 27 (2026), scipy 1.15's `_propack`
extension did not load, while scipy 1.16.3 did. Pin such packages to the range observed to work,
record why beside the pin, and assert that development-only packages stay out of the shipping
closure ([packaging](packaging.md#dependency-license-gates)).
