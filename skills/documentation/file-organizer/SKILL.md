---
name: file-organizer
description: Scan, dedupe, plan, apply, and undo file reorganizations.
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [file-organizer, deduplication, cleanup, sha256, undo]
    category: documentation
    related_skills: [pdf-operations]
---

# File Organizer

Programmatic organization of a messy directory tree: analyzing what is
actually in it, finding exact-duplicate files by content (not name or size
guesswork), and moving files into a type- or date-based structure -- always
as a two-step dry-run-then-apply, with every apply producing a manifest that
can genuinely reverse it. This is general file-format tooling, the one
deliberate exception in an otherwise DevOps/SRE-focused catalog, included
because "clean up this directory" is a task an agent gets asked to do
directly on a user's machine and deserves the same rigor as any other file
manipulation here.

## When to Use

Use when asked to analyze, deduplicate, or reorganize a real directory:
a Downloads folder, a Documents tree, an old Projects directory before
archiving, or any pile of files where "sort this out" needs to become a
concrete, reviewable, reversible set of file moves rather than a series of
ad hoc `mv` commands run by hand.

## One script, five subcommands, one undo format

Every operation routes through `scripts/organize_tool.py`:

```
python3 scripts/organize_tool.py scan DIR [--json] [--top N]
python3 scripts/organize_tool.py find-duplicates DIR [--json] [--min-size BYTES]
python3 scripts/organize_tool.py plan SOURCE [--dest DIR] [--scheme type|date] [--dedupe] [-o plan.json]
python3 scripts/organize_tool.py apply plan.json [--yes]
python3 scripts/organize_tool.py undo undo-log.json [--yes]
```

`scan` and `find-duplicates` are read-only and safe to run at any time.
`plan` is also read-only -- it writes a JSON manifest describing proposed
moves and touches nothing else. `apply` is the only subcommand that moves
files, and it is the only one that writes an undo manifest. `undo` reverses
one specific `apply` run using that manifest.

Zero third-party dependencies: `hashlib`, `pathlib`, `os.walk`, and
`shutil.move` from the standard library only, so this works identically on
Linux and macOS without a compatibility note or a `pip install` first. The
original inspiration for this skill (a widely-shared prompt-only "file
organizer" pattern) shelled out to BSD `md5`/`find` flags that silently
behave differently or fail outright on Linux -- there is no such split here.

## The undo log is a real, load-bearing artifact -- not a promise

The single most important property of this tool: **`apply` never performs a
move without first durably recording what it is about to do, and `undo` can
prove, from that record, whether a given move actually happened.**

Concretely, the undo manifest (JSON, one file per `apply` run, written to
`<dest>/.file_organizer/undo/undo-<run_id>.json` by default) is a list of
per-operation records:

```json
{
  "index": 3,
  "operation": "move",
  "original_path": "/abs/path/before.pdf",
  "new_path": "/abs/path/after/before.pdf",
  "timestamp": "2026-08-03T23:30:42+00:00",
  "status": "done",
  "error": null
}
```

`apply` writes each record with `status: "pending"` and fsyncs it **before**
performing the move, then rewrites it as `"done"` (or `"failed"` with an
`error` string) immediately after. That ordering means a process kill
mid-run leaves an unambiguous trail: a `"pending"` record with no matching
`"done"` tells `undo` the move may or may not have completed, and `undo`
resolves that by checking the live filesystem (does `new_path` exist and
`original_path` not exist?) rather than guessing from the log alone.

`undo` reverses `"done"` records in **reverse order** -- newest move first
-- moving each file from `new_path` back to `original_path`, then marks the
record `"undone"` and rewrites the manifest. That makes re-running `undo` on
the same log file, after it already succeeded, a safe no-op instead of a
double-reversal or an error. Records with `status: "failed"` are skipped
(nothing moved, nothing to reverse), and inconclusive `"pending"` records
that can't be resolved against the filesystem are left alone and printed
for manual inspection rather than acted on.

Both `apply` and `undo` validate every operation against the live
filesystem **before** touching anything (existence, size match, destination
not already occupied) and refuse the entire run -- not just the bad
operation -- if any check fails. This is the same validation-gate house
style used throughout this catalog (see `pdf-operations`'s "The
validation-gate pattern" section): a plan that is half-stale should produce
zero moves, not a partially-reorganized directory that is harder to reason
about than the mess you started with.

## Default excludes, and why they are not optional-by-omission

`scan`, `find-duplicates`, and `plan` all prune these directory names before
descending into them: `.git`, `node_modules`, `.venv`, `venv`,
`__pycache__`, `.tox`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`,
`dist`, `build`, `target`, `.next`, `.nuxt`, `.eggs`, plus this tool's own
`.file_organizer` bookkeeping directory. `.DS_Store`, `Thumbs.db`, and
`desktop.ini` are skipped as files regardless of directory.

The reason this is a default rather than left to the caller: pointing a
naive duplicate-finder or organizer at a real project directory without
excluding `.git` means hashing and reporting on `.git/objects` -- often
tens of thousands of loose objects that are Git's internal representation,
not "your files," that produce meaningless "duplicate" reports (many Git
objects legitimately share content) and can turn a five-second scan into a
multi-minute one. The same applies to `node_modules` and `.venv`, which are
regenerable dependency trees, not user content.

Override with `--no-default-excludes` (disables the whole built-in list) or
add more patterns with repeated `--exclude PATTERN` (glob-matched against
directory and file basenames). There is currently no way to *re-include* a
single name from the default list while keeping the rest -- pass
`--no-default-excludes` and re-supply the ones you still want via
`--exclude` if you need a partial override.

## Duplicate detection: candidate vs. confirmed

`find-duplicates` (and `plan --dedupe`, which uses the same function
internally) runs two phases:

1. **Group by exact file size.** A size match is a *candidate*, not proof
   -- reported in the summary as "size-collision groups checked," never as
   "duplicates."
2. **Hash every file in each candidate group with sha256** (streamed in
   1 MiB chunks, so a multi-gigabyte video does not get loaded into
   memory) and re-group by digest. Only a shared sha256 digest is reported
   as a **confirmed duplicate set**.

The output explicitly states how many size-collision groups turned out to
be false positives (same size, different content) so the candidate/proof
distinction is visible in the report, not just implied by which section a
file landed in. `plan --dedupe` uses confirmed sets only: it keeps the
oldest-by-mtime file where the scan found it and routes every other
sha256-identical copy to `<dest>/_Duplicates/<digest-prefix>/<name>`
instead of deleting anything -- deletion is not a capability this tool has
at all, by design (see Anti-patterns).

## Sensitive files never enter an automated plan

Before `plan` assigns a destination to any file, it checks the name against
a deliberately broad set of heuristics -- `.env`/`.env.*`, `*.pem`, `*.key`,
`*.pfx`/`*.p12`, `id_rsa`/`id_dsa`/`id_ecdsa`/`id_ed25519` (and their
`.pub`-adjacent variants), anything with `credentials`, `secret`, `password`,
or `token` in the name, `.netrc`, `.npmrc`, `.pgpass`, and any path that
passes through a `.aws`, `.ssh`, `.gnupg`, or `.kube` directory -- and, on a
match, routes the file into the plan's `manual_review` list with a reason
string instead of into `operations`. `apply` independently re-checks every
operation against the same heuristic as a second line of defense (in case a
plan was hand-edited) and refuses to run unless `--allow-sensitive` is
passed explicitly.

These patterns are intentionally over-broad -- a name like
`meeting-notes-password-reset.md` will get flagged even though it holds no
actual secret. That is the correct failure direction: the cost of a false
positive is one extra line in a review list; the cost of a false negative
is a credential silently relocated (or, in a careless downstream workflow,
archived/uploaded) by an automated tool. Nothing in `manual_review` is ever
touched by `apply`.

## Anti-patterns

- **Deleting instead of moving.** This tool has no delete capability
  anywhere in it, on purpose. `plan --dedupe` moves extra copies of a
  confirmed duplicate into `_Duplicates/`, it never removes them --
  deletion is not reversible the way a move is, and an undo log that
  promised to restore a deleted file would be lying.
- **Treating same-size or same-name matches as duplicates.** Report them,
  if at all, as candidates explicitly labeled as such. Only a matching
  sha256 digest over the full file content is a confirmed duplicate.
- **Running `find-duplicates` or `plan` without excludes on a directory
  that contains `.git` or `node_modules`.** It will "work," slowly, and
  bury the useful output in noise. Use the defaults; only reach for
  `--no-default-excludes` when you specifically need to inspect one of
  those trees.
- **Hand-editing a plan's `operations` list to add a file that was in
  `manual_review`.** `apply` re-validates against the same sensitive-file
  heuristic and will refuse the entire run unless you pass
  `--allow-sensitive` -- treat needing that flag as a signal to look at the
  file again, not as a hoop to jump through.
- **Assuming `apply` succeeded because it printed "Applied N/N."** Check
  the undo log's `status` field regardless -- `"partial"` means some
  operations failed partway (permissions, a file that vanished between the
  validation gate and the actual move) and the printed summary already
  says so, but a script consuming this tool's output should check the
  manifest, not just the exit code.
- **Trusting a `"pending"` undo record as proof nothing happened.** It
  means `apply` was interrupted between writing the record and completing
  the move -- `undo` resolves this by checking the live filesystem, but a
  human reading the raw log should not assume either way without doing the
  same check.
- **Re-running `plan` and manually reusing an old `apply` run's undo log
  against the new plan's moves.** Each undo log corresponds to exactly the
  operations recorded inside it at `apply` time; it has no knowledge of any
  other plan.

## Reference

- `scripts/organize_tool.py` -- the dispatcher covering scan,
  find-duplicates, plan, apply, and undo
- Related: `pdf-operations` (same validation-gate house style, applied to a
  different file format)
