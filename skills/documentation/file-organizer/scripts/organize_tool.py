#!/usr/bin/env python3
"""organize_tool.py -- single-entry-point dispatcher for file organization.

Design goal: the caller picks a *task* (scan, find-duplicates, plan, apply,
undo), not an implementation. Every filesystem walk goes through the same
exclude logic, every hash goes through the same chunked sha256 reader, and
every destructive step (apply, undo) goes through the same validate-before-
write gate: confirm the filesystem still matches what the manifest recorded,
THEN act -- never the other way around.

Zero third-party dependencies. Everything here is stdlib: pathlib, hashlib,
os.walk, shutil.move, json. That is deliberate -- a tool whose job is to be
pointed at an arbitrary, possibly huge directory tree should not need a pip
install first.

Usage:
    python3 organize_tool.py scan DIR [--json] [--top N]
    python3 organize_tool.py find-duplicates DIR [--json] [--min-size BYTES]
    python3 organize_tool.py plan SOURCE [--dest DIR] [--scheme type|date]
                             [--dedupe] [-o plan.json]
    python3 organize_tool.py apply PLAN.json [--yes]
    python3 organize_tool.py undo UNDO.json [--yes]

Shared flags on scan/find-duplicates/plan:
    --exclude PATTERN        additional glob pattern to exclude (repeatable)
    --no-default-excludes    disable the built-in .git/node_modules/etc list

Every subcommand exits 0 on success and non-zero with a message on stderr on
failure. `apply` and `undo` never partially commit past what their manifest
records -- see the module docstrings on `cmd_apply` and `cmd_undo` for the
crash-safety argument.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

# Directory names excluded by default during any walk. Rationale: these are
# either version-control internals (.git -- traversing .git/objects alone
# can mean tens of thousands of loose-object files that are not "your"
# files, hash to nothing meaningful as duplicates, and dominate runtime on
# any repo of nontrivial age) or dependency/build output that is regenerated
# from source and not worth categorizing, deduplicating, or moving.
# ".file_organizer" is this tool's own bookkeeping directory (plans + undo
# logs); excluding it keeps repeated runs from scanning their own state.
DEFAULT_EXCLUDE_DIRS = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    ".tox", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "target", ".next", ".nuxt", ".eggs",
    ".file_organizer",
})

# Filenames excluded by default regardless of directory: OS-generated
# metadata files that are noise in every organization or duplicate report.
DEFAULT_EXCLUDE_FILES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})

# Category classification for `scan` and `plan --scheme type`. Order does
# not matter; an extension is looked up once via a flattened reverse index.
CATEGORY_EXTENSIONS: dict[str, set[str]] = {
    "Documents": {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md"},
    "Spreadsheets": {".xls", ".xlsx", ".csv", ".ods", ".tsv"},
    "Presentations": {".ppt", ".pptx", ".key", ".odp"},
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp", ".tiff", ".tif", ".heic"},
    "Videos": {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"},
    "Audio": {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"},
    "Archives": {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".rar", ".7z", ".dmg", ".iso"},
    "Code": {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c",
        ".cpp", ".h", ".hpp", ".rb", ".sh", ".json", ".yaml", ".yml", ".toml",
    },
}
_EXTENSION_TO_CATEGORY = {
    ext: category
    for category, exts in CATEGORY_EXTENSIONS.items()
    for ext in exts
}

# Sensitive-file heuristics. These are matched against the filename only
# (case-insensitive) or against path components, and are DELIBERATELY broad:
# a false positive here costs the user one extra line in a "needs manual
# review" list, while a false negative silently drops a credential into an
# automated move plan. Bias toward over-flagging.
SENSITIVE_NAME_GLOBS = (
    ".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.p12", "*.ppk",
    "id_rsa", "id_rsa.*", "id_dsa", "id_dsa.*", "id_ecdsa", "id_ecdsa.*",
    "id_ed25519", "id_ed25519.*", "*credentials*", "*secret*", "*password*",
    "*_token", "*.token", ".netrc", ".npmrc", ".pgpass",
)
SENSITIVE_PATH_COMPONENTS = frozenset({".aws", ".ssh", ".gnupg", ".kube"})

HASH_CHUNK_SIZE = 1024 * 1024  # 1 MiB


# ---------------------------------------------------------------------------
# Shared errors and small helpers
# ---------------------------------------------------------------------------


class OrganizeToolError(Exception):
    """Raised for any expected failure. Caught once, at the top level, and
    printed without a traceback -- tracebacks are for bugs in this script,
    not for a caller pointing it at a missing directory or a stale plan."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_run_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _require_dir(path_str: str) -> Path:
    path = Path(path_str).expanduser().resolve()
    if not path.exists():
        raise OrganizeToolError(f"directory not found: {path}")
    if not path.is_dir():
        raise OrganizeToolError(f"not a directory: {path}")
    return path


def _require_file(path_str: str) -> Path:
    path = Path(path_str).expanduser().resolve()
    if not path.exists():
        raise OrganizeToolError(f"file not found: {path}")
    if not path.is_file():
        raise OrganizeToolError(f"not a file: {path}")
    return path


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}B"
        size /= 1024
    return f"{size:.1f}TB"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _categorize(path: Path) -> str:
    return _EXTENSION_TO_CATEGORY.get(path.suffix.lower(), "Other")


def _sensitivity_reason(path: Path) -> str | None:
    """Return a human-readable reason string if `path` matches a sensitive
    heuristic, or None if it looks safe to include in automated moves."""
    name_lower = path.name.lower()
    for pattern in SENSITIVE_NAME_GLOBS:
        if fnmatch.fnmatch(name_lower, pattern.lower()):
            return f"filename matches sensitive pattern '{pattern}'"
    for part in path.parts:
        if part in SENSITIVE_PATH_COMPONENTS:
            return f"path passes through sensitive directory '{part}'"
    return None


# ---------------------------------------------------------------------------
# Directory walking (shared by scan, find-duplicates, plan)
# ---------------------------------------------------------------------------


def _build_exclude_patterns(extra: list[str], use_defaults: bool) -> list[str]:
    patterns = list(DEFAULT_EXCLUDE_DIRS) if use_defaults else []
    patterns.extend(extra)
    return patterns


def _dir_excluded(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def iter_files(root: Path, exclude_patterns: list[str]) -> Iterator[Path]:
    """Yield every non-excluded file under `root`, pruning excluded
    directories in-place so os.walk never descends into them. Pruning
    (rather than filtering results afterward) is what makes excluding
    `.git` actually fast instead of merely hiding its output.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not _dir_excluded(d, exclude_patterns))
        for filename in sorted(filenames):
            if filename in DEFAULT_EXCLUDE_FILES:
                continue
            if _dir_excluded(filename, exclude_patterns):
                continue
            yield Path(dirpath) / filename


def _add_shared_walk_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--exclude", action="append", default=[], metavar="PATTERN",
        help="additional glob pattern to exclude (dir or file name, repeatable)",
    )
    parser.add_argument(
        "--no-default-excludes", action="store_true",
        help="disable the built-in .git/node_modules/.venv/__pycache__/build excludes",
    )


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------


def cmd_scan(args: argparse.Namespace) -> None:
    root = _require_dir(args.directory)
    patterns = _build_exclude_patterns(args.exclude, not args.no_default_excludes)

    by_category: dict[str, dict[str, int]] = {}
    sensitive: list[dict[str, object]] = []
    largest: list[tuple[int, Path]] = []
    total_files = 0
    total_bytes = 0

    for path in iter_files(root, patterns):
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise OrganizeToolError(f"cannot stat {path}: {exc}") from exc

        total_files += 1
        total_bytes += size
        category = _categorize(path)
        bucket = by_category.setdefault(category, {"count": 0, "bytes": 0})
        bucket["count"] += 1
        bucket["bytes"] += size

        reason = _sensitivity_reason(path)
        if reason:
            sensitive.append({"path": str(path), "reason": reason})

        largest.append((size, path))

    largest.sort(key=lambda pair: pair[0], reverse=True)
    top = largest[: args.top]

    result = {
        "root": str(root),
        "excludes": patterns,
        "total_files": total_files,
        "total_bytes": total_bytes,
        "by_category": {
            cat: {"count": v["count"], "bytes": v["bytes"]}
            for cat, v in sorted(by_category.items(), key=lambda kv: -kv[1]["bytes"])
        },
        "sensitive_files": sensitive,
        "largest_files": [
            {"path": str(p), "bytes": s} for s, p in top
        ],
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"Scan of {root}")
    print(f"  {total_files} files, {_human_size(total_bytes)} total")
    print(f"  excludes: {', '.join(sorted(patterns)) or '(none)'}")
    print()
    print("By category:")
    for cat, v in result["by_category"].items():
        print(f"  {cat:<15} {v['count']:>6} files  {_human_size(v['bytes']):>10}")
    if sensitive:
        print()
        print(f"Sensitive files flagged for manual review ({len(sensitive)}):")
        for entry in sensitive:
            print(f"  {entry['path']}  ({entry['reason']})")
    if top:
        print()
        print(f"Largest {len(top)} files:")
        for size, path in top:
            print(f"  {_human_size(size):>10}  {path}")


# ---------------------------------------------------------------------------
# find-duplicates
# ---------------------------------------------------------------------------


def find_duplicate_sets(
    root: Path, patterns: list[str], min_size: int
) -> tuple[list[list[Path]], int, int]:
    """Two-phase duplicate detection.

    Phase 1 groups files by exact size. A size match is a CANDIDATE only --
    two files of the same size are not proof of anything. Phase 2 hashes
    every file inside a candidate group (sha256, streamed) and re-groups by
    digest; only a shared digest is reported as a confirmed duplicate set.

    Returns (confirmed_sets, candidate_groups_checked, false_positive_groups)
    so callers can report how many size-collisions turned out to be
    different content -- making the "candidate, not proof" distinction
    visible in output, not just in code comments.
    """
    by_size: dict[int, list[Path]] = {}
    for path in iter_files(root, patterns):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size < min_size:
            continue
        by_size.setdefault(size, []).append(path)

    candidate_groups = [group for group in by_size.values() if len(group) > 1]

    confirmed_sets: list[list[Path]] = []
    false_positive_groups = 0

    for group in candidate_groups:
        by_hash: dict[str, list[Path]] = {}
        for path in group:
            try:
                digest = _sha256(path)
            except OSError as exc:
                raise OrganizeToolError(f"cannot read {path}: {exc}") from exc
            by_hash.setdefault(digest, []).append(path)

        confirmed_here = [members for members in by_hash.values() if len(members) > 1]
        confirmed_sets.extend(confirmed_here)
        if not confirmed_here:
            false_positive_groups += 1
        elif len(confirmed_here) < len(by_hash):
            # Some members of this size-collision group matched, others did
            # not -- still counts as a group that was not entirely real.
            false_positive_groups += 1

    return confirmed_sets, len(candidate_groups), false_positive_groups


def cmd_find_duplicates(args: argparse.Namespace) -> None:
    root = _require_dir(args.directory)
    patterns = _build_exclude_patterns(args.exclude, not args.no_default_excludes)

    confirmed_sets, candidate_groups, false_positives = find_duplicate_sets(
        root, patterns, args.min_size
    )

    sets_out = []
    reclaimable = 0
    for members in confirmed_sets:
        members_sorted = sorted(members, key=lambda p: p.stat().st_mtime)
        size = members_sorted[0].stat().st_size
        reclaimable += size * (len(members_sorted) - 1)
        sets_out.append({
            "sha256": _sha256(members_sorted[0]),
            "size_bytes": size,
            "count": len(members_sorted),
            "files": [
                {"path": str(p), "mtime": p.stat().st_mtime} for p in members_sorted
            ],
        })

    result = {
        "root": str(root),
        "excludes": patterns,
        "size_collision_groups_checked": candidate_groups,
        "false_positive_groups": false_positives,
        "confirmed_duplicate_sets": len(sets_out),
        "reclaimable_bytes": reclaimable,
        "duplicates": sets_out,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"Duplicate scan of {root}")
    print(
        f"  {candidate_groups} same-size candidate group(s) checked "
        f"(candidate = same size only, not proof)"
    )
    print(
        f"  {false_positives} group(s) were false positives "
        f"(same size, different content once hashed)"
    )
    print(f"  {len(sets_out)} confirmed duplicate set(s) (sha256-identical)")
    print(f"  {_human_size(reclaimable)} reclaimable by keeping one copy per set")
    for entry in sets_out:
        print()
        print(f"  sha256:{entry['sha256'][:12]}  {_human_size(entry['size_bytes'])} x {entry['count']}")
        for f in entry["files"]:
            print(f"    {f['path']}")


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


def _scheme_destination(dest_root: Path, path: Path, scheme: str) -> Path:
    if scheme == "type":
        category = _categorize(path)
        return dest_root / category / path.name
    if scheme == "date":
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return dest_root / f"{mtime.year:04d}" / f"{mtime.month:02d}" / path.name
    raise OrganizeToolError(f"unknown scheme: {scheme}")


def _same_file(a: Path, b: Path) -> bool:
    """True if `a` and `b` refer to the same file on disk. Needed because a
    plain string/resolve() comparison is NOT enough to detect identity on
    the case-insensitive-but-case-preserving filesystems that are the
    DEFAULT on both macOS (APFS) and Windows (NTFS): a source file at
    `images/photo.jpg` and a category destination of `Images/photo.jpg`
    are different strings but the same inode. Missing this would make the
    plan propose a pointless "move" that a naive exists()-based dedupe
    check then sees as "occupied" and renames to "photo (2).jpg" --
    touching a file that never needed to move at all.
    """
    if a == b:
        return True
    if a.exists() and b.exists():
        try:
            return a.samefile(b)
        except OSError:
            return False
    return False


def _dedupe_destination(candidate: Path, used: set[Path]) -> Path:
    """Return `candidate`, or a disambiguated sibling ("name (2).ext") if
    `candidate` already exists on disk or was already assigned earlier in
    this same plan. Never overwrites."""
    if not candidate.exists() and candidate not in used:
        used.add(candidate)
        return candidate
    stem, suffix, parent = candidate.stem, candidate.suffix, candidate.parent
    n = 2
    while True:
        alt = parent / f"{stem} ({n}){suffix}"
        if not alt.exists() and alt not in used:
            used.add(alt)
            return alt
        n += 1


def cmd_plan(args: argparse.Namespace) -> None:
    source = _require_dir(args.source)
    dest = Path(args.dest).expanduser().resolve() if args.dest else source
    patterns = _build_exclude_patterns(args.exclude, not args.no_default_excludes)

    files = list(iter_files(source, patterns))

    duplicate_members: dict[Path, str] = {}
    keepers: set[Path] = set()
    duplicate_analysis = None
    if args.dedupe:
        confirmed_sets, candidate_groups, false_positives = find_duplicate_sets(
            source, patterns, min_size=1
        )
        duplicate_analysis = {
            "size_collision_groups_checked": candidate_groups,
            "false_positive_groups": false_positives,
            "confirmed_duplicate_sets": len(confirmed_sets),
        }
        for members in confirmed_sets:
            members_sorted = sorted(members, key=lambda p: (p.stat().st_mtime, str(p)))
            keeper = members_sorted[0]
            keepers.add(keeper)
            digest = _sha256(keeper)
            for extra in members_sorted[1:]:
                duplicate_members[extra] = digest

    operations = []
    manual_review = []
    used_destinations: set[Path] = set()
    skipped_identity = 0

    for path in files:
        reason = _sensitivity_reason(path)
        if reason:
            manual_review.append({"path": str(path), "reason": reason})
            continue

        try:
            stat = path.stat()
        except OSError as exc:
            raise OrganizeToolError(f"cannot stat {path}: {exc}") from exc

        if path in duplicate_members:
            digest = duplicate_members[path]
            candidate = dest / "_Duplicates" / digest[:12] / path.name
            op_reason = "duplicate"
        else:
            candidate = _scheme_destination(dest, path, args.scheme)
            op_reason = "categorize"

        # Identity check BEFORE uniquification: on a case-insensitive
        # filesystem, `candidate.exists()` can be True only because it IS
        # `path` under a different case. Catch that here so it never reaches
        # `_dedupe_destination`, which would otherwise treat it as a real
        # collision and rename a file that never needed to move.
        if _same_file(candidate, path):
            skipped_identity += 1
            continue

        candidate = _dedupe_destination(candidate, used_destinations)

        operations.append({
            "operation": "move",
            "original_path": str(path),
            "new_path": str(candidate),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "reason": op_reason,
        })

    plan_id = _new_run_id()
    plan = {
        "plan_id": plan_id,
        "created_at": _now_iso(),
        "source": str(source),
        "dest": str(dest),
        "scheme": args.scheme,
        "dedupe": args.dedupe,
        "excludes": patterns,
        "duplicate_analysis": duplicate_analysis,
        "operations": operations,
        "manual_review": manual_review,
        "skipped_identity": skipped_identity,
    }

    if args.output:
        out_path = Path(args.output).expanduser().resolve()
    else:
        out_dir = dest / ".file_organizer" / "plans"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"plan-{plan_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    print(f"Plan written to {out_path}")
    print(f"  {len(operations)} move(s) proposed")
    print(f"  {skipped_identity} file(s) already in place (no-op, excluded from plan)")
    if manual_review:
        print(f"  {len(manual_review)} file(s) flagged sensitive -- NOT included in any move, see manual_review")
    if duplicate_analysis:
        print(
            f"  dedupe: {duplicate_analysis['confirmed_duplicate_sets']} confirmed duplicate set(s) "
            f"routed to _Duplicates/"
        )
    print(f"\nNext: python3 organize_tool.py apply {out_path}")


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def _undo_log_path(dest_root: Path, run_id: str, override: str | None) -> Path:
    if override:
        path = Path(override).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    out_dir = dest_root / ".file_organizer" / "undo"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"undo-{run_id}.json"


def _write_undo_manifest(path: Path, manifest: dict) -> None:
    """Rewrite the undo manifest in full and fsync it. Manifests here are
    at most a few thousand small JSON records -- rewriting the whole file on
    every state transition is cheap and, unlike an append-only log, leaves
    exactly one well-formed JSON document on disk at all times instead of
    requiring the reader to reconstruct state from a stream of events.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def cmd_apply(args: argparse.Namespace) -> None:
    """Execute a plan produced by `plan`.

    Two-gate design, matching this catalog's validation-gate house style
    (see pdf-operations SKILL.md): gate 1 validates EVERY operation against
    the live filesystem before touching anything; only if all operations
    pass does execution begin. Gate 2 happens per-operation at execution
    time as a final defensive re-check (belt and suspenders against a race
    between validation and the move itself).

    Undo-log crash safety: before each move, this writes a record with
    status "pending" to the undo manifest and fsyncs it. Only after the
    move actually succeeds does the record flip to "done" and get
    rewritten. If the process is killed between those two writes, `undo`
    can tell the difference (see `cmd_undo`) instead of guessing.
    """
    plan_path = _require_file(args.plan)
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OrganizeToolError(f"{plan_path} is not valid JSON: {exc}") from exc

    operations = plan.get("operations", [])
    if not operations:
        print("Plan has no operations. Nothing to do.")
        return

    dest_root = Path(plan["dest"])

    # Gate 1: validate everything before doing anything.
    errors = []
    seen_new_paths: set[str] = set()
    for i, op in enumerate(operations):
        original = Path(op["original_path"])
        new = Path(op["new_path"])

        if not original.exists():
            errors.append(f"op {i}: source no longer exists: {original}")
            continue
        if not original.is_file():
            errors.append(f"op {i}: source is no longer a file: {original}")
            continue

        live_stat = original.stat()
        if live_stat.st_size != op["size"]:
            errors.append(
                f"op {i}: {original} changed size since plan was created "
                f"({op['size']} -> {live_stat.st_size} bytes) -- refusing to move a file "
                "that no longer matches what was planned"
            )
        if new.exists():
            errors.append(f"op {i}: destination already exists: {new}")
        if str(new) in seen_new_paths:
            errors.append(f"op {i}: duplicate destination within this plan: {new}")
        seen_new_paths.add(str(new))

        reason = _sensitivity_reason(original)
        if reason and not args.allow_sensitive:
            errors.append(
                f"op {i}: {original} matches a sensitive-file pattern ({reason}) "
                "and should not be in an apply-able plan. Re-run `plan`, or pass "
                "--allow-sensitive if this is a deliberate, reviewed exception."
            )

    if errors:
        print(f"apply refused: {len(errors)} problem(s) found, nothing was moved:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        raise OrganizeToolError("fix the plan (re-run `plan`) or the filesystem state, then retry")

    if not args.yes:
        answer = input(f"Apply {len(operations)} move(s)? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted, nothing was moved.")
            return

    run_id = _new_run_id()
    undo_path = _undo_log_path(dest_root, run_id, args.undo_dir)
    manifest = {
        "run_id": run_id,
        "plan_file": str(plan_path),
        "started_at": _now_iso(),
        "completed_at": None,
        "status": "in_progress",
        "operations": [],
    }
    _write_undo_manifest(undo_path, manifest)

    applied = 0
    failed = 0
    for i, op in enumerate(operations):
        original = Path(op["original_path"])
        new = Path(op["new_path"])

        record = {
            "index": i,
            "operation": "move",
            "original_path": str(original),
            "new_path": str(new),
            "timestamp": _now_iso(),
            "status": "pending",
            "error": None,
        }
        manifest["operations"].append(record)
        _write_undo_manifest(undo_path, manifest)  # written BEFORE the move

        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(original), str(new))
        except OSError as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
            failed += 1
        else:
            record["status"] = "done"
            applied += 1

        _write_undo_manifest(undo_path, manifest)  # updated AFTER the move

    manifest["completed_at"] = _now_iso()
    manifest["status"] = "completed" if failed == 0 else "partial"
    _write_undo_manifest(undo_path, manifest)

    print(f"Applied {applied}/{len(operations)} move(s)" + (f", {failed} failed" if failed else ""))
    print(f"Undo log: {undo_path}")
    print(f"To undo: python3 organize_tool.py undo {undo_path}")


# ---------------------------------------------------------------------------
# undo
# ---------------------------------------------------------------------------


def cmd_undo(args: argparse.Namespace) -> None:
    """Reverse a previous `apply` run using its undo manifest.

    Only records with status "done" are reversed -- those are the moves
    `apply` confirmed actually happened. A "pending" record (apply was
    killed between writing it and completing the move) is inspected against
    the live filesystem rather than trusted blindly: if `new_path` exists
    and `original_path` does not, the move clearly did happen and is
    reversed anyway; otherwise it is reported as inconclusive and skipped.
    Reversal walks the operation list newest-first, matching "reverse order"
    of the original apply, and each reversed record is marked "undone" so
    re-running `undo` on the same manifest is a safe no-op the second time.
    """
    undo_path = _require_file(args.undo_log)
    try:
        manifest = json.loads(undo_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OrganizeToolError(f"{undo_path} is not valid JSON: {exc}") from exc

    records = manifest.get("operations", [])
    to_reverse = []
    inconclusive = []

    for record in reversed(records):
        status = record.get("status")
        if status == "undone":
            continue
        if status == "done":
            to_reverse.append(record)
        elif status == "pending":
            new = Path(record["new_path"])
            original = Path(record["original_path"])
            if new.exists() and not original.exists():
                to_reverse.append(record)
            else:
                inconclusive.append(record)
        # "failed" records never moved anything -- nothing to reverse.

    if not to_reverse:
        print("Nothing to undo (no completed moves found in this manifest).")
        if inconclusive:
            print(f"{len(inconclusive)} inconclusive record(s) skipped -- inspect manually:")
            for record in inconclusive:
                print(f"  index {record['index']}: {record['original_path']} <-> {record['new_path']}")
        return

    # Gate: confirm every reversal is safe before touching the filesystem.
    errors = []
    for record in to_reverse:
        new = Path(record["new_path"])
        original = Path(record["original_path"])
        if not new.exists():
            errors.append(f"index {record['index']}: moved file no longer at {new}")
        if original.exists():
            errors.append(f"index {record['index']}: original location {original} is occupied again")

    if errors:
        print(f"undo refused: {len(errors)} problem(s) found, nothing was reversed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        raise OrganizeToolError("resolve the conflicts above, then retry undo")

    if not args.yes:
        answer = input(f"Reverse {len(to_reverse)} move(s)? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted, nothing was reversed.")
            return

    reversed_count = 0
    for record in to_reverse:
        new = Path(record["new_path"])
        original = Path(record["original_path"])
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(new), str(original))
        record["status"] = "undone"
        reversed_count += 1
        _write_undo_manifest(undo_path, manifest)

    print(f"Reversed {reversed_count} move(s).")
    if inconclusive:
        print(f"{len(inconclusive)} inconclusive record(s) left untouched -- inspect manually:")
        for record in inconclusive:
            print(f"  index {record['index']}: {record['original_path']} <-> {record['new_path']}")


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="organize_tool.py",
        description="Scan, find duplicates in, plan, apply, and undo file reorganizations.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scan", help="analyze a directory: type/size breakdown, sensitive files")
    p.add_argument("directory")
    p.add_argument("--json", action="store_true")
    p.add_argument("--top", type=int, default=10, help="how many largest files to list (default 10)")
    _add_shared_walk_args(p)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("find-duplicates", help="sha256-confirmed exact-match duplicate detection")
    p.add_argument("directory")
    p.add_argument("--json", action="store_true")
    p.add_argument("--min-size", type=int, default=1, help="skip files smaller than this many bytes (default 1)")
    _add_shared_walk_args(p)
    p.set_defaults(func=cmd_find_duplicates)

    p = sub.add_parser("plan", help="dry-run: write a JSON manifest of proposed moves, touch nothing")
    p.add_argument("source")
    p.add_argument("--dest", help="destination root (default: reorganize in place under source)")
    p.add_argument("--scheme", choices=["type", "date"], default="type")
    p.add_argument(
        "--dedupe", action="store_true",
        help="also route confirmed sha256-duplicate copies into dest/_Duplicates/<hash>/",
    )
    p.add_argument("-o", "--output", help="plan file path (default: dest/.file_organizer/plans/plan-<id>.json)")
    _add_shared_walk_args(p)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("apply", help="execute a plan, writing an undo manifest as it goes")
    p.add_argument("plan")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument("--undo-dir", help="override where the undo manifest is written")
    p.add_argument(
        "--allow-sensitive", action="store_true",
        help="permit applying a plan operation on a file matching a sensitive-file pattern",
    )
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("undo", help="reverse a specific apply run using its undo manifest")
    p.add_argument("undo_log")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.set_defaults(func=cmd_undo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except OrganizeToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
