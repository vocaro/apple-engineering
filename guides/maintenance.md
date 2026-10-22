# Maintenance

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Shared-machine operating rules

The rules themselves are in the [common rules](../agents/core.md) and the
[current host policy](../policies/shared-host.md); this section adds how to apply them. Actual
host inventory and authorizations stay outside the generic rules.

- Rules change, and a worktree keeps the copy of each instruction file its branch was cut with.
  Before a step that uses something every session shares (the hosted runner, a device, the
  Mac's screen), run `python3 scripts/eng policy refresh` and read the project's rule as it
  stands on `main`: `git show origin/main:AGENTS.md`.
- A task handed over by another session is that session's request, not the owner's. Where a rule
  says "unless the owner asks", ask the owner.
- Own what you start and stop only that: processes, simulators, devices, settings and files.
  Preserve every other session's work, including a run that looks idle.
- Give every simulator and device command the canonical uppercase UDID of a device you own or
  have reserved; never select by name or `booted`.
- Take no foreground input, Mac VoiceOver session or debugger on the shared Mac without the
  explicit authorization the policy requires. Do not open a live simulator view or any tool that
  takes control of a simulator's screen unless the owner asked to watch: such a tool asks the
  owner to approve each device, and a disposable device is new on every run.
- Before proposing a physical device, say what it would show that a simulator cannot. A check
  said to need a finger usually needs a timing or an input that a UI test can make.
- Record what automation cannot reach as not verified, and leave it to the owner.

[Shared host](shared-host.md) holds the mechanisms: admission, reservations, supervision and
inspection without a debugger.

## Concurrent Git integration

Every session's worktree shares one `.git`, and `main` gains commits many times a day.

**Name the base commit.** Another session's `git fetch` moves `origin/main` in your worktree. To
squash, rebase or compare, read the commit your branch is based on once, with
`git merge-base HEAD origin/main`, and use that commit rather than the ref. A
`git reset --soft origin/main` made after the ref had moved staged main's new commits as
deletions. A patch made with `git diff origin/main -- FILES` to take a session's own change out
of a tree held another pull request's changes as well, and the tree a test then ran on was
neither main's nor the branch's. To take your own change out, reverse the patch of your own
commit, and check that the diff against the base is empty before calling the tree main's.

**Check what a brief says against what is there now.** A pull request a brief names as open may
have merged since the brief was written; look before building on its branch, and once it has
merged, build on `main`. A test merged since your branch was cut may pin a decision the owner
has since reversed; hold it against the decision recorded on the issue before changing the test
or your code.

**Fetch before the last verification, and do not chase `main`.** When `main` moves faster than a
full verification runs, verifying again after each rebase never ends. Land, or open the pull
request, once the tests pass on a commit that holds `main`; merge `main` again when it
conflicts; and say which commit each run used.

**Keep evidence off branches.** What a probe or spike found goes on the issue or in the subject
document it bears on. Code worth having again goes on the issue as a patch, with the commit it
applies to. "Still on the remote" is not a way to find something.

**Verify the integrated tree.** Two changes that each pass can fail together. Cherry-pick each
finished change onto the branch that will be pushed and run the gate there, not in the
worktrees. When several branches are ready at once, one gate can serve them: merge them onto
`main` in a local branch that is not pushed, keep each branch's changelog line, run the gate
there, and say on each pull request which commit ran and which heads it held. A filtered run on
one platform does not stand in for another platform's suites.

**Commit handed-over patches before integrating them.** An agent told to leave its work
uncommitted hands over one patch per issue, made against the base commit, with the order it
applies in. In a worktree at that base, `git apply --index PATCH` and `git commit` each in
order, then cherry-pick the commits. A cherry-pick leaves the base, branch and picked versions
of every conflicted file in the index for a three-way merge and carries the change's message and
its closing line; `git apply` refuses a patch whole where the branch has changed the same lines.
Shared records (generated counts, allow tables, issue-state snapshots) conflict in the same
places on every pick: regenerate them from their sources after each pick rather than merging by
hand ([documentation checks](#documentation-checks)).

**Push only onto the `main` you tested.** Immediately before pushing to a direct-main
repository:

```sh
git fetch origin
git merge-base --is-ancestor origin/main HEAD && git push origin HEAD:main
```

If `origin/main` is not an ancestor, rebase onto it, run the gate again on the rebased tree, and
push that. Never force-push `main`. A repository's `integration` setting in `engineering.json`
(`direct-main` or `pull-request`) says which route it uses.

**An issue is closed by what `main`'s tree holds.** Not by a commit somewhere that names it, not
by a branch that would fix it, and not by a merge that records such a branch as merged.

- A commit says `Closes #N` only if it is meant to land on `main` with its content, and only
  when the person landing it is entitled to close that issue. Work in flight says `Refs #N`. The
  closing commit folds the facts that still describe the product into the owning document.
- A merge whose tree equals its first parent's tree brings no content, whatever its parents say.
  Every commit it introduces is recorded as merged and absent from the tree, and an issue whose
  every `Closes` sits in that set is closed by nothing.
- An abandoned branch's issues are reopened, or left closed only with a comment naming the
  commit that holds the unported fix, so the next person learns it before starting.

A closing-commit check holds this mechanically from Git alone, offline: it finds each empty
merge, fails one that strands a closure claim unless a recorded reconciliation names it, notes
one that strands nothing, and passes an issue also claimed by a commit the tree holds. It
refuses a shallow clone, which cannot show whether a merge brought content, and it cannot see an
issue closed by hand on GitHub against a branch commit.

GitHub closes an issue when a `Closes` commit reaches `main` on the server, so fixes committed
to a local `main` leave their issues open and looking untouched. Before choosing work, list the
open issues a local commit already closes; each number printed is work to gate and push, not to
redo:

```sh
comm -12 <(git log --format=%B main | grep -oE 'Closes #[0-9]+' | grep -oE '[0-9]+' | sort -u) \
  <(gh issue list --state open --limit 200 --json number --jq '.[].number' | sort)
```

## Documentation and evidence ownership

Each kind of information has one home:

- What a system does, why, and its limits: the document for its subject. A repository has one
  document per subject, never one per issue or per release.
- How to run or repeat something: the subject's runbook, with probe scripts and their inputs in
  its probe section.
- What was run: a comment on the issue with the commit, the machine, the counts, the
  measurements and what was left unverified. A document links to that comment and does not
  repeat it.
- A release's verification: its release notes.
- Open work: an issue, never a document.

Documents describe the system as it is, in the present tense. The narrative of a change lives in
Git history; dated narrative belongs only in designated logs and measurement records. A build
number attached to a measurement is a fact about the measurement. Re-measure a figure before
documenting it, and give the build, corpus and configuration it was measured on. Put the current
result and the outstanding gaps first; label older pending text as historical and link failed or
superseded attempts to the final result, keeping their original revisions and outcomes.

**Measurements are records.** A measurement directory holds each experiment's record and the
small summaries it quotes. Raw captures (logs, archives, renders, converted outputs) stay out of
the tree, or are regenerated from the commands the record gives. A gate can cap what a change
adds there, counting committed, staged, unstaged and untracked additions against the base
branch. Tooling that a gate runs lives outside the records directory.

**Records cite commits and paths in prose, and stay frozen.** A record names the commit, paths
and identities it measured, as measured. The only later edit is a one-line pointer at the top
when a file it names has moved or been removed. No manifest binds records to paths, no gate
fails when a cited path moves, and historical paths and hashes are never rewritten. Documents
that need the current truth state it themselves and link to the record for how it was
established. A run's evaluation receipt is a local consistency check binding one run to its own
outputs, not a signed attestation; a historical receipt that lacks required evidence is
recaptured, not annotated.

**Decision records** state Context, Decision, Consequences and Evidence, take the next number,
and are listed in an index. A decision that supersedes another says so in both; neither is
deleted. Decision records are dated history, so checks that keep documents current exempt them.

**A ruled-out register** lists each rejected approach with its ruling and evidence, including
the build and corpus. An entry is removed only when new evidence overturns it, with the
overturning measurement recorded in the same commit.

**Deferring work keeps its coverage.** Deferring, parking or deprioritizing a class of work
means not starting it now. It never removes corpus cases, contracts, gates, tests or fixtures,
and a deferred area's cases still have to pass. Record the deferral on the issues it concerns;
removing coverage is a decision of its own, asked for and recorded as one.

**Issues.** The issue body is the goal as filed; later updates are comments, not body rewrites,
so the thread stays a record. Give each issue one kind of work. When research must precede
implementation, file two issues linked as blocked-by rather than one, so status and closure stay
unambiguous. File a defect with where it was found, the commit and exact command, what was
observed and expected, and the evidence; file only what was measured, and call a suspicion one.

**Agent entry points stay small.** Keep `AGENTS.md` under 32 KiB: Codex's default
`project_doc_max_bytes` silently truncates past that, and Claude Code warns above 40,000
characters. State a rule there and put its runbook, mechanism and evidence in the owning
document.

## Documentation checks

`python3 scripts/eng docs check [PATHS]` runs the shared check in
`src/python/vocaro_engineering/docs.py`. With no paths it reads the root Markdown files and
those under `doc`, `guides`, `knowledge`, `agents` and `policies`. It checks that:

- every local Markdown link resolves inside the checkout;
- the link's spelling matches the tracked name exactly, compared against Git's names because a
  case-insensitive APFS volume resolves a wrong-case path, and for untracked files component by
  component;
- every `AGENTS.md` is under 32 KiB (it fails at 32,768 bytes).

It skips code blocks fenced with three backticks, web URLs and same-document links. It does not
check `#fragment` anchors, in the same file or another, so a renamed heading passes; review
anchors or add a project check for them. It does not mask inline code or `~~~` fences, and it
has no exemption list. Project checks add what a repository needs:

- **Snippets from compiled examples.** A document's code sample lives between
  `<!-- snippet:NAME -->` and `<!-- /snippet -->` and is regenerated from a
  `// snippet:start NAME` … `// snippet:end NAME` region of source that compiles. The check
  fails on a stale snippet, `--write` regenerates, and a minimum snippet count guards against a
  check that silently matched nothing.
- **Documented builds.** Compile every command a runbook prints, exactly as written, with only
  the output moved into scratch. Frozen records are exempt: they print the build they measured.
- **Generated counts.** Test and case counts live between `<!-- counts:NAME -->` markers and are
  computed from the suites, never from the text: a static Swift `@Test` count is checked against
  `swift test list` after the candidate's own debug build, because `--skip-build` in a warm
  checkout lists a previous candidate's products. A conflict confined to a region is resolved by
  regenerating; one that also touches prose is reported. A region present twice fails: a merge
  kept both sides. Counts still typed in prose are held to the contract they describe, and a
  phrase in a form the check cannot read fails rather than passing unread.
- **Fixture notices.** Notices name every fixture; a duplicated section or list (what a merge
  leaves), a list naming a missing fixture, a list behind its directory, a fixture of no listed
  family and a cited path the tree does not hold all fail.
- **Closed-issue citations.** A document may not cite a closed issue as the live tracker for a
  gap. Each allowed citation carries its reason, and an allowance no document cites fails. A
  checked-in issue-state snapshot keeps the check offline, so it never passes because the
  network was down; it prints the snapshot's age and fails the first citation of an issue newer
  than the snapshot. Refresh the snapshot in a commit of its own after a push closes a cited
  issue. A refresh learns every closure, not only its own, so run the check on the refreshed
  snapshot and push only a pass.
- **Exemptions.** Documents frozen by committed receipts and append-only logs whose dated
  entries name moved files get explicit, documented exemptions rather than rewrites.

## Spelling check

`python3 scripts/eng spelling [PATHS]` finds British spellings anywhere in a project's text,
identifiers included, and exits 1 on any. With no paths it reads every tracked text file, which
is what a push carries; named paths also read untracked files Git does not ignore, so a page is
checked before it is published from disk. Gate pushes on it: the words arrive one at a time and
are invisible in review.

It splits each run of letters at camelCase, snake_case and SCREAMING_CASE boundaries and judges
each subword whole, by pattern (-ise, -yse, -our, -tre, -bre and doubled-l inflections) and by
an irregular list, with a list of American words that only look British. Its positive controls
run before any file is read, so a detector that stopped detecting fails instead of passing as a
clean tree. Exit 2 means nothing was checked. The rules and what each exemption was learned from
are in `src/python/vocaro_engineering/spelling.py`.

It already exempts other projects' British-spelled API names, such as Apple's `isCancelled` and
Unity's `MonoBehaviour`, URLs, a list item's first `<em>` (a cited title) and a line marked
`spelling: keep` with a reason, such as a decoder reading a name stored before a rename. A
project lists the rest in engineering.json's `spelling`, each mapped to its reason: `skip` for
paths of recorded observations or retained upstream text (a key ending in `/` is a directory),
`exemptPhrases` for a standard's terms, `exemptRuns` for whole identifiers another project
named, and `exemptTokens` for proper names. Fix a hit by spelling the word the American way;
never widen a pattern to make one go away.

## Portable negative controls

An isolated checkout may itself live under a temporary directory. A test of a destination
outside permitted temporary roots must choose an actually excluded parent, rather than assume
the repository directory is excluded. Assert rejection before any write; a read-only existing
parent supplies a safe negative control. Preserve the positive temporary-directory and symlink
controls. The [StudyWright integration record](https://github.com/vocaro/studywright/issues/488)
captures the regression found while moving development methods into this toolkit.

Dependency-graph contracts also need explicit updates when a module moves. Keep the exact
shipping dependency closure and test-only exclusions enforced after accepting a new provider;
removing the negative controls would lose the boundary the extraction is meant to preserve.
