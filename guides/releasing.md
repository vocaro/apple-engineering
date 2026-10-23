# Releasing

A release gives one verified revision of a library a version number and says what changed since
the previous release. This guide covers Swift package libraries. An app's version and build numbers, archive, export and upload are in
[packaging](packaging.md#mac-app-store-export-and-testflight-upload).

## Versions

Consumers pin a library by revision (`revision:` in a manifest, or SwiftPM's resolved file), not
by version, and move when they choose ([updating and rolling back](adoption.md#updating-and-rolling-back)).
A release is a named, verified point that consumers and records can cite; it moves no consumer.

- Name versions `MAJOR.MINOR.PATCH`, with no `v`: the tag for 0.3.1 is `0.3.1`.
- Before 1.0 there is no source-compatibility promise, so the number says what kind of change a
  release holds. A release that adds public API, or changes a public declaration, dependency,
  deployment floor or persisted format incompatibly, raises the minor version. A patch holds
  only fixes and adds no public API.
- Persisted contracts, such as stored identities, bookmark and location formats and the
  artifacts consumers keep, are separate from source compatibility. A release keeps them or
  migrates them explicitly, and its notes say which.
- Never move or delete a published tag: consumers and records cite it. Correct a mistake with
  the next patch release.

## The changelog

`CHANGELOG.md` at the repository root lists what changed, newest first: `## Unreleased` at the
top, then one section per release headed `## X.Y.Z — YYYY-MM-DD`.

- A change adds its entry at the top of "Unreleased" in the commit that makes it: one sentence
  and a link to its issue, or to its pull request where there is no issue. The detail stays on
  the issue.
- Write what a consumer sees change, not how the code changed.

## Preparing a release

1. Start from the current `main` and read the base commit once
   ([concurrent Git integration](maintenance.md#concurrent-git-integration)). Choose the version
   from the "Unreleased" entries.
2. Make one commit, `Release NAME X.Y.Z`, that only prepares the release:
   - rename `## Unreleased` to `## X.Y.Z — YYYY-MM-DD` and put an empty `## Unreleased` above it;
   - update every tracked file that names the current version, such as an installation line in
     the README or a sample app's `MARKETING_VERSION` (`git grep -nF OLD_VERSION` finds them);
   - update the stated platform requirements if the deployment floor moved.

   Code, tests and documents land before it, in commits of their own.
3. Run the release gate on that commit, through admission: the project's exclusive `gate` lane
   (`python3 scripts/eng run gate`). It runs every suite the project's testing runbook requires
   for a release, on every supported platform, in debug and optimized builds, with the
   documentation and spelling checks. Every required test passes, with none skipped and none
   unmeasured; check the executed counts ([honest outcome states](evidence.md#honest-outcome-states)).
   Only a commit whose gate passed is tagged, so nothing else records the run.
4. An edit during or after the run invalidates it. If the gate fails, land the fix in its own
   commit, make the release commit again on top of it and run the gate again.
5. Integrate the release commit by the project's route. On a `direct-main` project, push it only
   onto the `main` you tested ([concurrent Git integration](maintenance.md#concurrent-git-integration)).
   If `main` moved, rebase, move any entries that arrived in "Unreleased" into the release's
   section, run the gate again and push that. Through a pull request, the merge must leave
   `main` holding the tested tree; if it does not, run the gate again on `main`'s commit.

## Tagging and publishing

Once `main` holds the release commit:

1. Tag that commit with an annotated tag, and push the tag:

   ```sh
   git tag -a X.Y.Z -m "NAME X.Y.Z" COMMIT
   git push origin X.Y.Z
   ```

2. Write the release notes in an untracked file in the checkout and check their spelling with
   `python3 scripts/eng spelling NOTES.md`; a path outside the checkout, or one Git ignores, is
   not read. Publish them from the tag, then delete the file:

   ```sh
   gh release create X.Y.Z --verify-tag --title X.Y.Z --notes-file NOTES.md
   ```

The notes hold, in order:

- a sentence or two on what the release is for;
- its changes: the entries of the changelog's section for it;
- requirements and compatibility: the deployment floor, and whether public API, dependencies
  and persisted formats changed, with what a consumer must do where they did;
- links to the changelog at the tag and to the comparison with the previous release
  (`https://github.com/OWNER/REPO/compare/PREVIOUS...X.Y.Z`).

The notes do not describe how the release was verified: a release is tagged only on a
commit its gate passed. What was run for one change stays on its issue.
