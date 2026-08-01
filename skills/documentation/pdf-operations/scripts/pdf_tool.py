#!/usr/bin/env python3
"""pdf_tool.py -- single-entry-point dispatcher for common PDF operations.

Design goal: the caller picks a *task* (extract-text, merge, split, rotate,
watermark, encrypt, decrypt, extract-images, ocr), not a *library*. Each
subcommand internally selects the library that actually does the work
(pypdf for structural edits, pdftotext/pdfplumber for extraction,
pytesseract + pdf2image for OCR) so nothing upstream of this script has to
know pypdf from pdfplumber from qpdf.

House style (see SKILL.md's "The validation-gate pattern" section for the
full writeup): every subcommand validates its inputs BEFORE touching the filesystem and
fails with a specific, actionable message. None of these commands catch a
broad exception and continue -- a corrupt PDF, a missing password, or a
bad page range must stop the run, not produce a silently wrong file.

Usage:
    python3 pdf_tool.py extract-text input.pdf [-o output.txt] [--pages 1-3,5]
    python3 pdf_tool.py merge a.pdf b.pdf c.pdf -o merged.pdf
    python3 pdf_tool.py split input.pdf --outdir out/ [--ranges 1-3,4-6]
    python3 pdf_tool.py rotate input.pdf -o rotated.pdf --angle 90 [--pages 1,3]
    python3 pdf_tool.py watermark input.pdf -o out.pdf --text "DRAFT"
    python3 pdf_tool.py encrypt input.pdf -o out.pdf --user-password secret
    python3 pdf_tool.py decrypt input.pdf -o out.pdf --password secret
    python3 pdf_tool.py extract-images input.pdf --outdir images/
    python3 pdf_tool.py ocr input.pdf -o output.txt [--dpi 300]

Each subcommand exits 0 on success and non-zero with a message on stderr
on failure. There is no "partial success" exit path.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class PdfToolError(Exception):
    """Raised for any expected failure. Caught once, at the top level, and
    printed without a traceback -- tracebacks are for bugs in this script,
    not for a caller passing a bad path."""


def _require_file(path_str: str) -> Path:
    path = Path(path_str)
    if not path.exists():
        raise PdfToolError(f"input file not found: {path}")
    if not path.is_file():
        raise PdfToolError(f"not a file: {path}")
    return path


def _open_pdf_reader(path: Path):
    """Open a PDF with pypdf and translate the common parse failure modes
    into PdfToolError with a message that says what to do next, instead of
    letting a raw pypdf exception (or worse, a silent empty reader) escape.
    Does not touch encryption -- callers that need to require/accept a
    password should go through `_load_reader` instead; callers that need to
    probe `.is_encrypted` before deciding what to do (e.g. `encrypt`, which
    has no `--password` flag of its own) should call this directly.
    """
    from pypdf import PdfReader
    from pypdf.errors import EmptyFileError, PdfReadError

    try:
        return PdfReader(str(path))
    except EmptyFileError as exc:
        raise PdfToolError(f"{path} is empty or not a PDF") from exc
    except PdfReadError as exc:
        raise PdfToolError(
            f"{path} could not be parsed as a PDF ({exc}). "
            "If this file came from a scanner or a lossy transfer, check "
            "it isn't truncated before assuming it's corrupt."
        ) from exc


def _load_reader(path: Path, password: str | None = None):
    """Open a PDF via `_open_pdf_reader` and additionally require/apply a
    password when the file is encrypted, translating a missing or wrong
    password into a PdfToolError instead of a raw pypdf exception.
    """
    reader = _open_pdf_reader(path)

    if reader.is_encrypted:
        if password is None:
            raise PdfToolError(
                f"{path} is password-protected. Pass --password (or "
                "--user-password for the encrypt/decrypt subcommands)."
            )
        result = reader.decrypt(password)
        if result == 0:
            raise PdfToolError(f"the password provided for {path} is wrong")

    return reader


def _parse_page_spec(spec: str, page_count: int) -> list[int]:
    """Parse a 1-based, comma-separated page/range spec ("1,3-5,8") into a
    sorted, deduplicated list of 0-based page indexes. Raises PdfToolError
    on anything out of range rather than silently clamping or skipping --
    a typo'd page number should stop the run, not quietly drop a page.
    """
    indexes: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", chunk)
        if not match:
            raise PdfToolError(f"invalid page spec segment: '{chunk}'")
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        if start < 1 or end < start:
            raise PdfToolError(f"invalid page range: '{chunk}'")
        if end > page_count:
            raise PdfToolError(
                f"page {end} requested but the document only has {page_count} pages"
            )
        indexes.update(range(start - 1, end))
    return sorted(indexes)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


CID_ARTIFACT_RE = re.compile(r"\(cid:\d+\)")


def cmd_extract_text(args: argparse.Namespace) -> None:
    """Extract text via pypdf and flag output that looks image-based.

    The flag is a heuristic, not a certainty (see SKILL.md's "Deciding when
    OCR is needed" section for why these thresholds and why they're
    conservative): fewer than 10
    non-whitespace characters per page on average, or more than 5% of the
    extracted characters coming from unresolved `(cid:N)` glyph-ID
    artifacts, both mean the page has no real text layer.
    """
    path = _require_file(args.input)
    reader = _load_reader(path, args.password)

    if args.pages:
        page_indexes = _parse_page_spec(args.pages, len(reader.pages))
    else:
        page_indexes = list(range(len(reader.pages)))

    per_page_text = [reader.pages[i].extract_text() or "" for i in page_indexes]
    full_text = "\n\f\n".join(per_page_text)

    if args.output:
        Path(args.output).write_text(full_text, encoding="utf-8")
        print(f"wrote {len(full_text)} characters to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(full_text)
        if not full_text.endswith("\n"):
            sys.stdout.write("\n")

    non_whitespace = len(re.sub(r"\s", "", full_text))
    cid_chars = sum(len(m.group(0)) for m in CID_ARTIFACT_RE.finditer(full_text))
    avg_chars_per_page = non_whitespace / max(len(page_indexes), 1)
    cid_fraction = (cid_chars / non_whitespace) if non_whitespace else 0.0

    if avg_chars_per_page < 10 or cid_fraction > 0.05:
        print(
            "WARNING: extracted text looks image-based or unresolved "
            f"(avg {avg_chars_per_page:.1f} chars/page, "
            f"{cid_fraction:.0%} cid-artifact characters). "
            "This PDF is likely a scan with no real text layer -- "
            "run `pdf_tool.py ocr` instead of trusting this output.",
            file=sys.stderr,
        )


def cmd_merge(args: argparse.Namespace) -> None:
    from pypdf import PdfWriter

    if len(args.inputs) < 2:
        raise PdfToolError("merge needs at least two input files")

    writer = PdfWriter()
    for input_str in args.inputs:
        path = _require_file(input_str)
        reader = _load_reader(path, args.password)
        for page in reader.pages:
            writer.add_page(page)

    output_path = Path(args.output)
    with output_path.open("wb") as fh:
        writer.write(fh)
    print(f"merged {len(args.inputs)} files into {output_path} "
          f"({len(writer.pages)} pages)", file=sys.stderr)


def cmd_split(args: argparse.Namespace) -> None:
    from pypdf import PdfWriter

    path = _require_file(args.input)
    reader = _load_reader(path, args.password)
    page_count = len(reader.pages)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = path.stem

    if args.ranges:
        groups: list[list[int]] = []
        for chunk in args.ranges.split(","):
            groups.append(_parse_page_spec(chunk, page_count))
    else:
        groups = [[i] for i in range(page_count)]

    written = []
    for i, group in enumerate(groups, start=1):
        writer = PdfWriter()
        for page_index in group:
            writer.add_page(reader.pages[page_index])
        out_path = outdir / f"{stem}_part{i}.pdf"
        with out_path.open("wb") as fh:
            writer.write(fh)
        written.append(out_path)

    print(f"wrote {len(written)} file(s) to {outdir}/", file=sys.stderr)


def cmd_rotate(args: argparse.Namespace) -> None:
    from pypdf import PdfWriter

    if args.angle % 90 != 0:
        raise PdfToolError(
            f"--angle must be a multiple of 90 (got {args.angle}); "
            "PDF page rotation is a display transform, not a free crop"
        )

    path = _require_file(args.input)
    reader = _load_reader(path, args.password)
    page_count = len(reader.pages)
    page_indexes = (
        _parse_page_spec(args.pages, page_count)
        if args.pages
        else list(range(page_count))
    )

    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i in page_indexes:
            page.rotate(args.angle)
        writer.add_page(page)

    output_path = Path(args.output)
    with output_path.open("wb") as fh:
        writer.write(fh)
    print(f"rotated {len(page_indexes)} page(s) by {args.angle} degrees "
          f"-> {output_path}", file=sys.stderr)


def cmd_watermark(args: argparse.Namespace) -> None:
    """Stamp a text watermark on every page.

    Builds one reportlab overlay per distinct page size (most PDFs have a
    single page size, so in practice this is one overlay reused for every
    page) rather than assuming letter/A4, so mixed-size documents still get
    a correctly placed watermark instead of a clipped or offset one.
    """
    import io

    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.colors import Color
    from reportlab.pdfgen import canvas

    path = _require_file(args.input)
    reader = _load_reader(path, args.password)

    overlay_cache: dict[tuple[float, float], "PdfReader"] = {}

    def overlay_for_size(width: float, height: float):
        key = (round(width, 2), round(height, 2))
        if key not in overlay_cache:
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(width, height))
            c.saveState()
            c.setFont("Helvetica-Bold", args.font_size)
            c.setFillColor(Color(0.5, 0.5, 0.5, alpha=0.4))
            c.translate(width / 2, height / 2)
            c.rotate(45)
            c.drawCentredString(0, 0, args.text)
            c.restoreState()
            c.save()
            buf.seek(0)
            overlay_cache[key] = PdfReader(buf).pages[0]
        return overlay_cache[key]

    writer = PdfWriter()
    for page in reader.pages:
        box = page.mediabox
        overlay = overlay_for_size(float(box.width), float(box.height))
        page.merge_page(overlay)
        writer.add_page(page)

    output_path = Path(args.output)
    with output_path.open("wb") as fh:
        writer.write(fh)
    print(f"watermarked {len(writer.pages)} page(s) -> {output_path}", file=sys.stderr)


def cmd_encrypt(args: argparse.Namespace) -> None:
    from pypdf import PdfWriter

    path = _require_file(args.input)
    # Probe encryption status directly rather than through `_load_reader`:
    # that helper requires a password for *any* encrypted input, but
    # `encrypt` has no `--password` flag (only --user-password/--owner-password,
    # which are for the *new* encryption, not for opening an already-encrypted
    # input) -- going through it here would always raise its generic
    # "password-protected, pass --password" message before this subcommand's
    # own, more specific "already encrypted, decrypt first" message could run.
    reader = _open_pdf_reader(path)
    if reader.is_encrypted:
        raise PdfToolError(
            f"{path} is already encrypted; decrypt it first if you want to "
            "re-encrypt with a different password"
        )

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(
        user_password=args.user_password,
        owner_password=args.owner_password,
    )

    output_path = Path(args.output)
    with output_path.open("wb") as fh:
        writer.write(fh)
    print(f"encrypted -> {output_path}", file=sys.stderr)


def cmd_decrypt(args: argparse.Namespace) -> None:
    from pypdf import PdfWriter

    path = _require_file(args.input)
    probe = _open_pdf_reader(path)
    if not probe.is_encrypted:
        print(
            f"note: {path} was not encrypted; copying through unchanged",
            file=sys.stderr,
        )
    reader = _load_reader(path, args.password)

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    output_path = Path(args.output)
    with output_path.open("wb") as fh:
        writer.write(fh)
    print(f"decrypted -> {output_path}", file=sys.stderr)


def cmd_extract_images(args: argparse.Namespace) -> None:
    path = _require_file(args.input)
    reader = _load_reader(path, args.password)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    count = 0
    for page_number, page in enumerate(reader.pages, start=1):
        for image in page.images:
            safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", image.name)
            out_path = outdir / f"page{page_number:03d}_{safe_name}"
            out_path.write_bytes(image.data)
            count += 1

    if count == 0:
        print(
            "no embedded raster images found. If this PDF is a scan, the "
            "whole page IS the image -- use `pdf_tool.py ocr` instead of "
            "extract-images.",
            file=sys.stderr,
        )
    else:
        print(f"extracted {count} image(s) to {outdir}/", file=sys.stderr)


def cmd_ocr(args: argparse.Namespace) -> None:
    """OCR a PDF page-by-page with pytesseract, for the case where
    extract-text already told you there's no real text layer.

    This subcommand has real, non-optional dependencies beyond pypdf:
    pytesseract + the `tesseract` binary, and pdf2image + poppler's
    `pdftoppm`. Rather than degrade silently when they're missing, it
    raises immediately with the exact install command -- an OCR command
    that quietly returns empty text is worse than one that refuses to run.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise PdfToolError(
            "OCR requires pytesseract and pdf2image "
            "(pip3 install --user pytesseract pdf2image), plus the "
            "tesseract and poppler binaries on PATH "
            "(macOS: brew install tesseract poppler; "
            "Debian/Ubuntu: apt-get install tesseract-ocr poppler-utils)."
        ) from exc

    path = _require_file(args.input)
    # Fail fast on a bad/encrypted file using the same path as every other
    # subcommand, even though convert_from_path does its own PDF parsing --
    # a consistent error message beats a poppler stack trace.
    _load_reader(path, args.password)

    try:
        images = convert_from_path(str(path), dpi=args.dpi)
    except Exception as exc:  # pdf2image raises its own PDFPageCountError etc.
        raise PdfToolError(f"could not rasterize {path} for OCR: {exc}") from exc

    pages_text = []
    for i, image in enumerate(images, start=1):
        text = pytesseract.image_to_string(image, lang=args.lang)
        pages_text.append(f"--- page {i} ---\n{text}")

    full_text = "\n\n".join(pages_text)
    if args.output:
        Path(args.output).write_text(full_text, encoding="utf-8")
        print(f"wrote OCR text for {len(images)} page(s) to {args.output}",
              file=sys.stderr)
    else:
        sys.stdout.write(full_text)
        if not full_text.endswith("\n"):
            sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf_tool.py",
        description="Dispatcher for common PDF operations. Run a subcommand "
        "with -h for its full option list.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("extract-text", help="extract text, warn if scanned")
    p.add_argument("input")
    p.add_argument("-o", "--output", help="write to this file instead of stdout")
    p.add_argument("--pages", help="1-based page spec, e.g. '1,3-5'")
    p.add_argument("--password")
    p.set_defaults(func=cmd_extract_text)

    p = sub.add_parser("merge", help="concatenate PDFs in argument order")
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--password", help="applied to every encrypted input")
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("split", help="split into one file per page or range")
    p.add_argument("input")
    p.add_argument("--outdir", required=True)
    p.add_argument("--ranges", help="e.g. '1-3,4-6' (default: one page each)")
    p.add_argument("--password")
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("rotate", help="rotate pages by a multiple of 90 degrees")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--angle", type=int, required=True)
    p.add_argument("--pages", help="1-based page spec (default: all pages)")
    p.add_argument("--password")
    p.set_defaults(func=cmd_rotate)

    p = sub.add_parser("watermark", help="stamp a diagonal text watermark")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--font-size", type=int, default=40)
    p.add_argument("--password")
    p.set_defaults(func=cmd_watermark)

    p = sub.add_parser("encrypt", help="add password protection")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--user-password", required=True)
    p.add_argument("--owner-password")
    p.set_defaults(func=cmd_encrypt)

    p = sub.add_parser("decrypt", help="remove password protection")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--password", required=True)
    p.set_defaults(func=cmd_decrypt)

    p = sub.add_parser("extract-images", help="dump embedded raster images")
    p.add_argument("input")
    p.add_argument("--outdir", required=True)
    p.add_argument("--password")
    p.set_defaults(func=cmd_extract_images)

    p = sub.add_parser("ocr", help="rasterize + tesseract (for scanned PDFs)")
    p.add_argument("input")
    p.add_argument("-o", "--output", help="write to this file instead of stdout")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--lang", default="eng")
    p.add_argument("--password")
    p.set_defaults(func=cmd_ocr)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except PdfToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
