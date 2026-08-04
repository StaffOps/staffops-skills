#!/usr/bin/env python3
"""invoice_tool.py -- single-entry-point dispatcher for organizing invoices
and receipts.

Design goal: the caller picks a *task* (scan, extract, organize,
export-csv), not a *library*. PDF text extraction and the "does this need
OCR" decision reuse the sibling `pdf-operations` skill's reader and
heuristic when that skill is present at its usual relative path in this
catalog, falling back to an inline copy of the identical logic when it
isn't (e.g. this skill directory was copied out and distributed on its
own). Image OCR goes through pytesseract directly. See SKILL.md's
"Extraction and confidence" section for the full rationale.

House style (shared with pdf-operations -- see its SKILL.md "validation-gate
pattern" section): `organize` never writes to disk without first building
and printing the full plan; it requires `--execute` to apply it. Every
extracted field carries a confidence label and a note explaining how it was
derived, so nothing inferred is presented as if it were certain.

Usage:
    python3 invoice_tool.py scan DIR [--recursive] [--json]
    python3 invoice_tool.py extract FILE [--verbose]
    python3 invoice_tool.py organize SRC_DIR --dest DEST_DIR
        [--strategy vendor|category|date|flat] [--recursive]
        [--execute] [--move] [--category-map map.json]
    python3 invoice_tool.py export-csv SRC_DIR --dest out.csv
        [--recursive] [--force] [--category-map map.json]

`scan` and `extract` never write anything. `organize` defaults to a dry
run and copies (not moves) originals unless `--execute`/`--move` are
given. `export-csv` defaults to appending only rows not already present
(matched by sha256) instead of duplicating them on a second run.

Not tax or accounting advice: the built-in category map (and any
`--category-map` you supply) is an illustrative filing convenience, not an
authoritative determination of what is tax-deductible. See SKILL.md.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

CANDIDATE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
IMAGE_EXTENSIONS = CANDIDATE_EXTENSIONS - {".pdf"}

# Must match pdf-operations' cmd_extract_text thresholds (see
# skills/documentation/pdf-operations/scripts/pdf_tool.py, "Deciding when
# OCR is needed" in its SKILL.md). Duplicated here only as numeric
# constants for the standalone fallback path -- the reader/parsing logic
# itself is reused via _load_pdf_operations_module(), not reimplemented.
OCR_MIN_AVG_CHARS_PER_PAGE = 10
OCR_MAX_CID_FRACTION = 0.05

STATE_FILENAME = ".invoice-organizer-state.json"

CSV_FIELDNAMES = [
    "source_path", "sha256", "vendor", "vendor_confidence",
    "invoice_number", "invoice_number_confidence",
    "date", "date_confidence", "amount", "amount_confidence",
    "currency", "category", "needs_review", "review_reasons",
    "extraction_method",
]

# Illustrative only -- see SKILL.md's "Not tax advice" section. Override
# with --category-map for anything that matters.
DEFAULT_CATEGORY_MAP = {
    "Software": ["adobe", "microsoft", "github", "aws", "google", "slack",
                 "atlassian", "notion", "figma", "openai", "anthropic", "dropbox"],
    "Office Supplies": ["staples", "office depot", "amazon"],
    "Travel": ["delta", "united", "airlines", "airbnb", "uber", "lyft",
               "marriott", "hilton", "expedia"],
    "Professional Services": ["legal", "consulting", "accountant", "law"],
}


class InvoiceToolError(Exception):
    """Raised for any expected failure. Caught once, at the top level, and
    printed without a traceback. Batch subcommands (scan/organize/
    export-csv) catch this PER FILE and keep going -- one unreadable file
    must not abort a run over hundreds of others -- but every failure is
    recorded and reported by name, never silently dropped."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _require_file(path_str: str) -> Path:
    path = Path(path_str)
    if not path.exists():
        raise InvoiceToolError(f"input file not found: {path}")
    if not path.is_file():
        raise InvoiceToolError(f"not a file: {path}")
    return path


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_candidates(root_str: str, recursive: bool) -> list[Path]:
    root = Path(root_str)
    if not root.is_dir():
        raise InvoiceToolError(f"not a directory: {root}")
    it = root.rglob("*") if recursive else root.glob("*")
    return sorted(p for p in it if p.is_file() and p.suffix.lower() in CANDIDATE_EXTENSIONS)


# ---------------------------------------------------------------------------
# Text extraction (PDF via pdf-operations reuse, images via pytesseract)
# ---------------------------------------------------------------------------


def _load_pdf_operations_module():
    """Best-effort import of the sibling pdf-operations skill's dispatcher
    module, so PDF reading and the OCR-needed heuristic are reused instead
    of reimplemented (see pdf-operations SKILL.md, "Deciding when OCR is
    needed"). Returns None if that skill isn't present at its usual
    relative path in this catalog -- callers fall back to an inline copy
    of the identical pypdf-based logic in that case, so this skill still
    works if copied out on its own.
    """
    candidate = Path(__file__).resolve().parent.parent.parent / "pdf-operations" / "scripts" / "pdf_tool.py"
    if not candidate.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_pdf_operations_pdf_tool", candidate)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


def _extract_pdf_text(path: Path) -> tuple[str, bool]:
    """Return (text, needs_ocr) for a PDF. Opens the file and applies the
    OCR-needed heuristic exactly as pdf-operations' `extract-text`
    subcommand does: average non-whitespace characters per page below
    OCR_MIN_AVG_CHARS_PER_PAGE, or more than OCR_MAX_CID_FRACTION of
    extracted characters being unresolved `(cid:N)` glyph-ID artifacts,
    both mean the page has no real text layer.
    """
    pdf_tool = _load_pdf_operations_module()
    try:
        if pdf_tool is not None:
            reader = pdf_tool._open_pdf_reader(path)  # noqa: SLF001 -- deliberate reuse, see module docstring
            cid_re = pdf_tool.CID_ARTIFACT_RE
        else:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            cid_re = re.compile(r"\(cid:\d+\)")
    except ImportError as exc:
        raise InvoiceToolError("pypdf is required (pip3 install --user pypdf)") from exc
    except Exception as exc:
        # Covers both pdf_tool.PdfToolError (reuse path) and pypdf's own
        # EmptyFileError/PdfReadError (standalone fallback path) -- both
        # mean "this isn't a readable PDF", translated to one error type.
        # The inner message from the reuse path already names the path,
        # so avoid stuttering "path ... path could not be parsed".
        message = str(exc)
        if message.startswith(str(path)):
            raise InvoiceToolError(message) from exc
        raise InvoiceToolError(f"{path} could not be read as a PDF: {message}") from exc

    if reader.is_encrypted:
        raise InvoiceToolError(
            f"{path} is password-protected; this tool does not accept PDF passwords"
        )

    pages_text = [page.extract_text() or "" for page in reader.pages]
    full_text = "\n\f\n".join(pages_text)

    non_whitespace = len(re.sub(r"\s", "", full_text))
    cid_chars = sum(len(m.group(0)) for m in cid_re.finditer(full_text))
    avg_chars_per_page = non_whitespace / max(len(pages_text), 1)
    cid_fraction = (cid_chars / non_whitespace) if non_whitespace else 0.0
    needs_ocr = avg_chars_per_page < OCR_MIN_AVG_CHARS_PER_PAGE or cid_fraction > OCR_MAX_CID_FRACTION
    return full_text, needs_ocr


def _ocr_pdf(path: Path, dpi: int = 300) -> str:
    """Rasterize + tesseract, mirroring pdf-operations' `ocr` subcommand:
    same dependencies (pytesseract + pdf2image), same non-optional
    binaries (tesseract + poppler's pdftoppm). Raises immediately if the
    OCR stack isn't installed instead of returning empty text.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise InvoiceToolError(
            "OCR requires pytesseract and pdf2image "
            "(pip3 install --user pytesseract pdf2image), plus the "
            "tesseract and poppler binaries on PATH "
            "(macOS: brew install tesseract poppler; "
            "Debian/Ubuntu: apt-get install tesseract-ocr poppler-utils)."
        ) from exc

    try:
        images = convert_from_path(str(path), dpi=dpi)
    except Exception as exc:  # pdf2image raises its own PDFPageCountError etc.
        raise InvoiceToolError(f"could not rasterize {path} for OCR: {exc}") from exc

    return "\n\n".join(pytesseract.image_to_string(img) for img in images)


def _ocr_image(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise InvoiceToolError(
            "Image OCR requires pytesseract and Pillow "
            "(pip3 install --user pytesseract pillow), plus the tesseract "
            "binary on PATH (macOS: brew install tesseract; "
            "Debian/Ubuntu: apt-get install tesseract-ocr)."
        ) from exc
    try:
        image = Image.open(path)
    except Exception as exc:
        raise InvoiceToolError(f"could not open {path} as an image: {exc}") from exc
    return pytesseract.image_to_string(image)


def _get_document_text(path: Path) -> tuple[str, str]:
    """Return (text, extraction_method). extraction_method is one of
    pdf-text, pdf-ocr, image-ocr -- recorded in every output so a human
    reviewing low-confidence fields knows whether OCR was involved."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text, needs_ocr = _extract_pdf_text(path)
        if needs_ocr:
            return _ocr_pdf(path), "pdf-ocr"
        return text, "pdf-text"
    if suffix in IMAGE_EXTENSIONS:
        return _ocr_image(path), "image-ocr"
    raise InvoiceToolError(f"unsupported file type: {path.suffix}")


# ---------------------------------------------------------------------------
# Field extraction with confidence signaling
# ---------------------------------------------------------------------------

VENDOR_LABEL_RE = re.compile(
    r"(?im)^[ \t]*(?:vendor|from|sold\s*by|company|merchant|bill\s*from)\s*[:\-]\s*(.+)$"
)
INVOICE_NUMBER_RE = re.compile(
    r"(?im)\b(?:invoice|inv)\.?\s*(?:number|no\.?|#)?\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9/_-]{2,24})\b"
)
DATE_LABEL_RE = re.compile(
    r"(?im)^[ \t]*(?:invoice\s*date|date\s*issued|date\s*of\s*issue|date|issued)\s*[:\-]\s*(.+)$"
)
GENERAL_DATE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"[A-Z][a-z]{2,8}\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Z][a-z]{2,8}\.?\s+\d{4})\b"
)
AMOUNT_VALUE_RE = re.compile(r"([\$€£]?\s?\d{1,3}(?:,\d{3})*\.\d{2})")
AMOUNT_PRIORITY = ["amount due", "total due", "grand total", "balance due", "total", "amount"]
CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}

# Unambiguous formats (ISO or a named month) are trusted at high
# confidence when labeled. Slash/dash numeric formats are inherently
# ambiguous (MM/DD vs DD/MM) -- see SKILL.md's "Known limitations" section
# -- so a match against these is always downgraded to low confidence, even
# when labeled, rather than silently guessing US ordering.
DATE_FORMATS_UNAMBIGUOUS = ["%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y",
                             "%d %B %Y", "%d %b %Y"]
DATE_FORMATS_AMBIGUOUS = ["%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%y"]

UNSAFE_FILENAME_RE = re.compile(r'[\/\\:*?"<>|\x00-\x1f]')


def _sanitize_filename_part(value: str, max_len: int = 60) -> str:
    value = UNSAFE_FILENAME_RE.sub("", value).strip()
    value = re.sub(r"\s+", " ", value)
    return value[:max_len].strip(" .") or "Unknown"


def _split_currency(raw: str) -> tuple[str, str]:
    raw = raw.strip()
    symbol = ""
    if raw and raw[0] in CURRENCY_SYMBOLS:
        symbol = raw[0]
        raw = raw[1:].strip()
    return CURRENCY_SYMBOLS.get(symbol, ""), raw.replace(",", "")


def _extract_vendor(text: str, filename: str) -> dict:
    match = VENDOR_LABEL_RE.search(text)
    if match:
        value = match.group(1).strip().strip(".,")
        if value:
            return {"value": value, "confidence": "high", "note": "found via labeled pattern match"}

    skip_prefixes = ("invoice", "receipt", "date", "bill to", "ship to", "page ")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and len(stripped) <= 80 and not stripped.lower().startswith(skip_prefixes):
            return {
                "value": stripped, "confidence": "low",
                "note": "inferred from the first non-empty line of document text, needs review",
            }

    stem = Path(filename).stem
    guess = re.sub(r"[_\-]+", " ", stem).strip().title()
    if guess:
        return {
            "value": guess, "confidence": "low",
            "note": "inferred from filename; document text extraction produced nothing usable, needs review",
        }
    return {"value": "", "confidence": "missing", "note": "no vendor found in text or filename"}


def _extract_invoice_number(text: str) -> dict:
    match = INVOICE_NUMBER_RE.search(text)
    if match:
        return {"value": match.group(1).strip(), "confidence": "high", "note": "found via labeled pattern match"}
    return {
        "value": "", "confidence": "missing",
        "note": "no invoice number found (normal for a simple receipt, not necessarily an error)",
    }


def _try_parse_date(raw: str) -> tuple[str, bool] | None:
    """Return (iso_date, is_ambiguous) for the first format that parses."""
    raw = raw.strip().rstrip(".")
    for fmt in DATE_FORMATS_UNAMBIGUOUS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d"), False
        except ValueError:
            continue
    for fmt in DATE_FORMATS_AMBIGUOUS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d"), True
        except ValueError:
            continue
    return None


def _extract_date(text: str, mtime: float) -> dict:
    match = DATE_LABEL_RE.search(text)
    if match:
        parsed = _try_parse_date(match.group(1))
        if parsed:
            iso, ambiguous = parsed
            if ambiguous:
                return {
                    "value": iso, "confidence": "low",
                    "note": (
                        f"labeled, but '{match.group(1).strip()}' is a numeric format "
                        "ambiguous between MM/DD and DD/MM -- verify manually"
                    ),
                }
            return {"value": iso, "confidence": "high", "note": "found via labeled pattern match"}

    for candidate in GENERAL_DATE_RE.findall(text):
        parsed = _try_parse_date(candidate)
        if parsed:
            iso, _ambiguous = parsed
            return {
                "value": iso, "confidence": "low",
                "note": (
                    f"inferred from an unlabeled date in the document body ('{candidate}'); "
                    "could be an issue date, due date, or something else -- needs review"
                ),
            }

    fallback = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    return {
        "value": fallback, "confidence": "low",
        "note": "no date found in document content; inferred from file modification time, needs review",
    }


def _find_labeled_amount(text: str) -> tuple[str, str] | None:
    """Return (raw_value, matched_label) for the highest-priority labeled
    amount line found, or None. Explicitly skips subtotal lines so a
    subtotal is never mistaken for the final total."""
    best: tuple[int, str, str] | None = None
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith(("subtotal", "sub total", "sub-total")):
            continue
        for idx, label in enumerate(AMOUNT_PRIORITY):
            if low.startswith(label):
                match = AMOUNT_VALUE_RE.search(low[len(label):])
                if match and (best is None or idx < best[0]):
                    best = (idx, match.group(1), label)
                break
    if best is None:
        return None
    return best[1], best[2]


def _extract_amount(text: str) -> dict:
    found = _find_labeled_amount(text)
    if found:
        raw_value, label = found
        currency, numeric = _split_currency(raw_value)
        return {
            "value": numeric, "currency": currency, "confidence": "high",
            "note": f"found via labeled pattern match ('{label}')",
        }

    parsed = []
    for raw in AMOUNT_VALUE_RE.findall(text):
        currency, numeric = _split_currency(raw)
        try:
            parsed.append((float(numeric.replace(",", "")), numeric, currency))
        except ValueError:
            continue
    if parsed:
        parsed.sort(key=lambda item: item[0], reverse=True)
        _value, numeric, currency = parsed[0]
        return {
            "value": numeric, "currency": currency, "confidence": "low",
            "note": (
                "inferred as the largest currency-shaped amount found in the document "
                "body; verify against the subtotal/tax breakdown, needs review"
            ),
        }

    return {"value": "", "currency": "", "confidence": "missing", "note": "no amount pattern found"}


def extract_one(path: Path, include_text: bool = False) -> dict:
    """Extract vendor/date/amount/invoice-number from one file. Raises
    InvoiceToolError for anything unreadable -- callers doing batch work
    (organize, export-csv) must catch this per file and continue; the
    single-file `extract` subcommand lets it propagate and fail loud."""
    if not path.is_file():
        raise InvoiceToolError(f"not a file: {path}")

    text, method = _get_document_text(path)
    sha256 = _sha256_of(path)
    vendor = _extract_vendor(text, path.name)
    invoice_number = _extract_invoice_number(text)
    date = _extract_date(text, path.stat().st_mtime)
    amount = _extract_amount(text)

    # Vendor, date, and amount are the fields organize/export-csv actually
    # depend on; invoice_number is commonly and legitimately absent on a
    # plain receipt, so its absence alone does not trigger needs_review.
    critical = {"vendor": vendor, "date": date, "amount": amount}
    review_reasons = [f"{name}:{field['confidence']}" for name, field in critical.items()
                       if field["confidence"] != "high"]
    if invoice_number["confidence"] != "high":
        review_reasons.append(f"invoice_number:{invoice_number['confidence']}")

    record = {
        "source_path": str(path),
        "sha256": sha256,
        "extraction_method": method,
        "vendor": vendor,
        "invoice_number": invoice_number,
        "date": date,
        "amount": amount,
        "needs_review": any(field["confidence"] != "high" for field in critical.values()),
        "review_reasons": review_reasons,
    }
    if include_text:
        record["_raw_text"] = text
    return record


# ---------------------------------------------------------------------------
# Categorization -- illustrative only, NOT tax advice (see SKILL.md)
# ---------------------------------------------------------------------------


def _load_category_map(path_str: str | None) -> dict[str, list[str]]:
    if not path_str:
        return DEFAULT_CATEGORY_MAP
    path = Path(path_str)
    if not path.is_file():
        raise InvoiceToolError(f"category map not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvoiceToolError(f"category map {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InvoiceToolError(f"category map {path} must be a JSON object of category -> [keyword, ...]")
    return data


def _categorize(vendor: str, category_map: dict[str, list[str]]) -> str:
    low = vendor.lower()
    for category, keywords in category_map.items():
        if any(keyword.lower() in low for keyword in keywords):
            return category
    return "Uncategorized"


# ---------------------------------------------------------------------------
# organize -- plan, then (only with --execute) copy/move + rename
# ---------------------------------------------------------------------------


def _build_target_name(record: dict, original_suffix: str) -> str:
    date_val = record["date"]["value"] or "0000-00-00"
    vendor_val = _sanitize_filename_part(record["vendor"]["value"] or "Unknown Vendor")
    invoice_number = record["invoice_number"]["value"]
    label = f"Invoice - {invoice_number}" if invoice_number else "Receipt"
    return f"{date_val} {vendor_val} - {label}{original_suffix}"


def _target_dir(dest_root: Path, record: dict, strategy: str, category_map: dict) -> Path:
    if record["needs_review"]:
        return dest_root / "_NeedsReview"

    date_val = record["date"]["value"] or "0000-00-00"
    date_parts = date_val.split("-")
    year = date_parts[0]
    vendor_val = _sanitize_filename_part(record["vendor"]["value"] or "Unknown Vendor")

    if strategy == "vendor":
        return dest_root / vendor_val
    if strategy == "date":
        month = date_parts[1] if len(date_parts) > 1 else "00"
        return dest_root / year / month
    if strategy == "category":
        return dest_root / year / _categorize(record["vendor"]["value"], category_map)
    if strategy == "flat":
        return dest_root
    raise InvoiceToolError(f"unknown strategy: {strategy}")


def _resolve_collision(target_path: Path, source_sha256: str) -> Path:
    """Ground-truth check before ever proposing a write: if something is
    already at the target path, compare content, not just the name. An
    identical file there is not a collision (organize is idempotent for
    it); a different file there gets a disambiguating suffix instead of
    being silently overwritten."""
    if not target_path.exists():
        return target_path
    if _sha256_of(target_path) == source_sha256:
        return target_path
    stem, suffix = target_path.stem, target_path.suffix
    counter = 2
    while True:
        candidate = target_path.with_name(f"{stem} ({counter}){suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _load_state(dest_root: Path) -> dict:
    state_path = dest_root / STATE_FILENAME
    if not state_path.is_file():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_state(dest_root: Path, state: dict) -> None:
    state_path = dest_root / STATE_FILENAME
    tmp_path = state_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp_path, state_path)


def _print_plan(plan: list[dict], errors: list[dict], strategy: str, dest_root: Path) -> None:
    organize_items = [item for item in plan if item["action"] == "organize"]
    skip_items = [item for item in plan if item["action"] == "skip"]
    review_items = [item for item in organize_items if item.get("needs_review")]

    print(f"Organization plan (strategy={strategy}, dest={dest_root})")
    print(f"  {len(organize_items)} file(s) to organize")
    print(f"  {len(skip_items)} file(s) skipped (already organized or exact duplicate)")
    print(f"  {len(review_items)} file(s) flagged needs_review -> routed to _NeedsReview/, original filename kept")
    print(f"  {len(errors)} file(s) failed extraction")
    print()

    for item in organize_items:
        flag = " [NEEDS REVIEW]" if item.get("needs_review") else ""
        print(f"  {item['source']}\n    -> {item['dest']}{flag}")
        if item.get("review_reasons"):
            print(f"       reasons: {', '.join(item['review_reasons'])}")
    for item in skip_items:
        print(f"  {item['source']}\n    (skip: {item['reason']})")
    for err in errors:
        print(f"  {err['source']}\n    (error: {err['error']})")


def cmd_organize(args: argparse.Namespace) -> None:
    files = _find_candidates(args.source, args.recursive)
    if not files:
        print(f"no candidate invoice/receipt files found under {args.source}", file=sys.stderr)
        return

    category_map = _load_category_map(args.category_map)
    dest_root = Path(args.dest)
    # No mkdir here -- a dry run (the default) must not touch the
    # filesystem at all, not even to create an empty dest directory.
    # _load_state tolerates a dest_root that doesn't exist yet.
    state = _load_state(dest_root)

    # Exact-duplicate detection across the whole batch, up front. sha256
    # only catches byte-identical files -- it will NOT catch a
    # near-duplicate like the same receipt rescanned at a different DPI,
    # re-exported with different metadata, or photographed vs scanned.
    # See SKILL.md's "Duplicate detection" section.
    hashes: dict[str, list[Path]] = {}
    for f in files:
        hashes.setdefault(_sha256_of(f), []).append(f)
    duplicate_of = {
        str(p): sorted(paths)[0]
        for paths in hashes.values() if len(paths) > 1
        for p in sorted(paths)[1:]
    }

    plan: list[dict] = []
    errors: list[dict] = []
    for f in sorted(files):
        sha256 = _sha256_of(f)

        existing = state.get(sha256)
        if existing:
            existing_dest = dest_root / existing["dest"]
            if existing_dest.is_file() and _sha256_of(existing_dest) == sha256:
                plan.append({
                    "source": str(f), "action": "skip",
                    "reason": "already organized", "dest": str(existing_dest),
                })
                continue

        if str(f) in duplicate_of:
            plan.append({
                "source": str(f), "action": "skip",
                "reason": f"exact duplicate of {duplicate_of[str(f)]} (sha256 match; "
                          "will not catch a different-DPI rescan or similar near-duplicate)",
            })
            continue

        try:
            record = extract_one(f)
        except InvoiceToolError as exc:
            errors.append({"source": str(f), "error": str(exc)})
            continue

        target_dir = _target_dir(dest_root, record, args.strategy, category_map)
        target_name = f.name if record["needs_review"] else _build_target_name(record, f.suffix.lower())
        target_path = _resolve_collision(target_dir / target_name, sha256)

        plan.append({
            "source": str(f), "sha256": sha256, "action": "organize",
            "dest": str(target_path), "needs_review": record["needs_review"],
            "review_reasons": record["review_reasons"], "extraction_method": record["extraction_method"],
        })

    _print_plan(plan, errors, args.strategy, dest_root)

    if not args.execute:
        print(
            "\nDry run only -- no files were copied or moved. "
            "Re-run with --execute to apply this plan.",
            file=sys.stderr,
        )
        return

    dest_root.mkdir(parents=True, exist_ok=True)
    applied = 0
    for item in plan:
        if item["action"] != "organize":
            continue
        src, dest = Path(item["source"]), Path(item["dest"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        if args.move:
            shutil.move(str(src), str(dest))
        else:
            shutil.copy2(str(src), str(dest))
        state[item["sha256"]] = {
            "dest": str(dest.relative_to(dest_root)),
            "organized_at": datetime.now().isoformat(timespec="seconds"),
        }
        applied += 1

    _save_state(dest_root, state)
    print(f"\napplied: {applied} file(s) {'moved' if args.move else 'copied'}", file=sys.stderr)


# ---------------------------------------------------------------------------
# export-csv
# ---------------------------------------------------------------------------


def _record_to_csv_row(record: dict, category: str) -> dict:
    return {
        "source_path": record["source_path"],
        "sha256": record["sha256"],
        "vendor": record["vendor"]["value"],
        "vendor_confidence": record["vendor"]["confidence"],
        "invoice_number": record["invoice_number"]["value"],
        "invoice_number_confidence": record["invoice_number"]["confidence"],
        "date": record["date"]["value"],
        "date_confidence": record["date"]["confidence"],
        "amount": record["amount"]["value"],
        "amount_confidence": record["amount"]["confidence"],
        "currency": record["amount"]["currency"],
        "category": category,
        "needs_review": "yes" if record["needs_review"] else "no",
        "review_reasons": ";".join(record["review_reasons"]),
        "extraction_method": record["extraction_method"],
    }


def cmd_export_csv(args: argparse.Namespace) -> None:
    files = _find_candidates(args.source, args.recursive)
    if not files:
        print(f"no candidate invoice/receipt files found under {args.source}", file=sys.stderr)
        return

    category_map = _load_category_map(args.category_map)
    dest_csv = Path(args.dest)

    existing_hashes: set[str] = set()
    existing_rows: list[dict] = []
    if dest_csv.is_file() and not args.force:
        with dest_csv.open("r", newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                existing_rows.append(row)
                if row.get("sha256"):
                    existing_hashes.add(row["sha256"])

    new_rows: list[dict] = []
    errors: list[dict] = []
    skipped = 0
    for f in sorted(files):
        sha256 = _sha256_of(f)
        if sha256 in existing_hashes:
            skipped += 1
            continue
        try:
            record = extract_one(f)
        except InvoiceToolError as exc:
            errors.append({"source": str(f), "error": str(exc)})
            continue
        category = _categorize(record["vendor"]["value"], category_map)
        new_rows.append(_record_to_csv_row(record, category))

    all_rows = (existing_rows + new_rows) if (dest_csv.is_file() and not args.force) else new_rows
    dest_csv.parent.mkdir(parents=True, exist_ok=True)
    with dest_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDNAMES, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({key: row.get(key, "") for key in CSV_FIELDNAMES})

    print(
        f"wrote {len(all_rows)} row(s) to {dest_csv} "
        f"({len(new_rows)} new, {skipped} already present, {len(errors)} error(s))",
        file=sys.stderr,
    )
    for err in errors:
        print(f"  error: {err['source']}: {err['error']}", file=sys.stderr)
    review_count = sum(1 for row in new_rows if row["needs_review"] == "yes")
    if review_count:
        print(
            f"{review_count} new row(s) flagged needs_review=yes -- verify before relying on them",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# scan / extract
# ---------------------------------------------------------------------------


def cmd_scan(args: argparse.Namespace) -> None:
    files = _find_candidates(args.directory, args.recursive)
    if not files:
        print(f"no candidate invoice/receipt files found under {args.directory}", file=sys.stderr)
        return

    records = []
    hashes: dict[str, list[Path]] = {}
    for f in files:
        sha256 = _sha256_of(f)
        hashes.setdefault(sha256, []).append(f)
        records.append({"path": str(f), "size": f.stat().st_size, "sha256": sha256})

    duplicate_groups = [[str(p) for p in paths] for paths in hashes.values() if len(paths) > 1]

    if args.json:
        print(json.dumps(
            {"root": args.directory, "files": records, "duplicate_groups": duplicate_groups}, indent=2
        ))
        return

    by_ext: dict[str, int] = {}
    for f in files:
        by_ext[f.suffix.lower()] = by_ext.get(f.suffix.lower(), 0) + 1
    print(f"{len(files)} candidate file(s) under {args.directory}")
    for ext, count in sorted(by_ext.items()):
        print(f"  {ext}: {count}")
    if duplicate_groups:
        print(
            f"\n{len(duplicate_groups)} exact-duplicate group(s) (sha256 match -- will not "
            "catch near-duplicates like the same receipt rescanned at a different DPI):"
        )
        for group in duplicate_groups:
            print(f"  {group}")


def cmd_extract(args: argparse.Namespace) -> None:
    path = _require_file(args.input)
    record = extract_one(path, include_text=args.verbose)
    if args.verbose:
        print(
            "WARNING: --verbose prints the full extracted document text below. Do not "
            "paste this into chat, tickets, or logs if the source document carries "
            "account numbers or other sensitive data -- see SKILL.md's "
            "'PII and financial-data handling' section.",
            file=sys.stderr,
        )
        print(record.pop("_raw_text"))
        print("--- end of extracted text ---", file=sys.stderr)
    print(json.dumps(record, indent=2))


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="invoice_tool.py",
        description="Dispatcher for scanning, extracting, organizing, and exporting invoices/receipts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scan", help="find candidate invoice/receipt files in a directory")
    p.add_argument("directory")
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("extract", help="extract vendor/date/amount/invoice-number from one file")
    p.add_argument("input")
    p.add_argument("--verbose", action="store_true",
                    help="also print the full extracted text (may contain sensitive data)")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("organize", help="plan, and with --execute apply, a rename + copy/move")
    p.add_argument("source")
    p.add_argument("--dest", required=True)
    p.add_argument("--strategy", choices=["vendor", "category", "date", "flat"], default="date")
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--execute", action="store_true", help="apply the plan (default: dry run only)")
    p.add_argument("--move", action="store_true", help="move instead of copy (default: copy, originals kept)")
    p.add_argument("--category-map", help="JSON {category: [keyword, ...]} (default: small illustrative map)")
    p.set_defaults(func=cmd_organize)

    p = sub.add_parser("export-csv", help="extract every candidate file in a directory and write a CSV")
    p.add_argument("source")
    p.add_argument("--dest", required=True)
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--force", action="store_true",
                    help="rewrite the CSV from scratch instead of appending only new rows")
    p.add_argument("--category-map", help="JSON {category: [keyword, ...]} (default: small illustrative map)")
    p.set_defaults(func=cmd_export_csv)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except InvoiceToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
