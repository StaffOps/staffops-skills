---
name: invoice-organizer
description: "Extract, rename, organize, and CSV-export invoices/receipts."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [invoices, receipts, file-operations, ocr, csv, bookkeeping]
    category: documentation
    related_skills: [pdf-operations, session-handoff]
---

# Invoice Organizer

Turn a messy folder of invoice and receipt files (PDFs, scans, photos) into
consistently named files sorted into a folder structure, plus a CSV export
suitable for handing to a bookkeeper. This is general file-organization
tooling built on top of `pdf-operations` for the PDF-reading half of the
job; it deliberately does not do bookkeeping, expense-report submission, or
tax preparation itself, and none of its "category" output is tax advice
(see "Not tax or accounting advice" below).

## When to Use

Use when a directory contains invoice/receipt files (`.pdf`, `.jpg`,
`.jpeg`, `.png`, `.tif`, `.tiff`, `.bmp`) that need vendor/date/amount/
invoice-number pulled out, a consistent filename applied, a folder
structure imposed, and/or a CSV summary generated. Not for a single
one-off PDF read (use `pdf-operations` directly) and not for anything past
"organize the files and list what's in them" -- categorization output here
is a filing convenience, not a financial or tax determination.

## One script, four subcommands

Every task routes through `scripts/invoice_tool.py`:

```
python3 scripts/invoice_tool.py scan DIR [--recursive] [--json]
python3 scripts/invoice_tool.py extract FILE [--verbose]
python3 scripts/invoice_tool.py organize SRC_DIR --dest DEST_DIR
    [--strategy vendor|category|date|flat] [--recursive]
    [--execute] [--move] [--category-map map.json]
python3 scripts/invoice_tool.py export-csv SRC_DIR --dest out.csv
    [--recursive] [--force] [--category-map map.json]
```

`scan` and `extract` never write anything -- `scan` lists candidate files
(by extension) and flags exact-hash duplicates; `extract` returns one
file's fields as JSON. `organize` and `export-csv` are the two
batch/write-capable subcommands and are covered in detail below.

## Extraction and confidence, not silent guessing

`extract` pulls four fields -- vendor, invoice number, date, amount -- each
as `{"value", "confidence", "note"}` (amount also carries `"currency"`).
`confidence` is one of:

- **`high`** -- found via a labeled pattern match (`"Vendor: Acme Corp"`,
  `"Total Due: $52.99"`, `"Invoice Date: 2024-03-15"`).
- **`low`** -- inferred by a fallback heuristic: the first non-empty line
  of the document for vendor, an unlabeled date found anywhere in the body,
  the largest currency-shaped number in the document for amount, or the
  file's modification time when no date appears in the content at all.
- **`missing`** -- nothing found by either path.

A record's `needs_review` boolean is `true` whenever **vendor, date, or
amount** is not `high` confidence -- these three are what `organize` and
`export-csv` actually build filenames and folders from, so anything less
than a labeled match gets surfaced, not silently trusted. `invoice_number`
is tracked in `review_reasons` too, but does not by itself flip
`needs_review`: a plain receipt legitimately has no invoice number, and
treating that as a defect would flag most receipts for no reason.

```
$ python3 scripts/invoice_tool.py extract staples_receipt.pdf
{
  "vendor": {"value": "Staples, Inc. \"Office Superstore\"",
             "confidence": "high", "note": "found via labeled pattern match"},
  "date": {"value": "2024-03-10", "confidence": "high", "note": "..."},
  "amount": {"value": "127.45", "currency": "USD", "confidence": "high", "note": "..."},
  "invoice_number": {"value": "", "confidence": "missing", "note": "..."},
  "needs_review": false,
  "review_reasons": ["invoice_number:missing"]
}
```

For PDFs, text extraction and the OCR-needed decision reuse
`pdf-operations`' reader and heuristic (same thresholds: fewer than 10
non-whitespace characters per page on average, or more than 5% `(cid:N)`
glyph-ID artifacts -- see that skill's "Deciding when OCR is needed"
section for the full rationale) rather than reimplementing text-vs-scanned
detection. `invoice_tool.py` imports `pdf-operations/scripts/pdf_tool.py`
directly from its usual relative path in this catalog when present, and
falls back to an inline copy of the identical pypdf-based logic if that
sibling skill isn't there (e.g. this skill directory was copied out on its
own) -- either way the same rule decides OCR, it is never reinvented
per-skill. Image files go straight to `pytesseract`; no text-layer
decision is needed for them since a bitmap has no text layer to begin
with.

## Known limitations of the field heuristics

Be upfront about these rather than let a user discover them the hard way:

- **Ambiguous numeric dates.** A slash- or dash-separated date like
  `03/09/2024` is genuinely ambiguous between MM/DD and DD/MM. This tool
  always downgrades such a match to `low` confidence and says so in the
  note, even when it came from a labeled `"Date:"` line -- it does not
  silently assume US ordering.
- **Largest-amount fallback for total.** When no line is labeled
  `"Total"`/`"Amount Due"`/etc., the fallback picks the single largest
  currency-shaped number in the document. That is usually the grand total,
  but can be wrong on documents with large unrelated numbers (a large
  quantity times unit price shown as a line item, a large negative
  discount rendered without a minus sign). Always `low` confidence,
  flagged for review.
- **Vendor first-line fallback.** Works well for invoices that put the
  company name at the very top with no other label; fails on templates
  that lead with a logo-only header (no text) or a "Bill To" block above
  the vendor name.
- **Currency detection.** Only recognizes `$`, `€`, `£` symbols, mapped to
  USD/EUR/GBP. A bare number with no symbol (common on some receipts)
  yields an empty `currency` field, not a guess.
- **No `python-dateutil` dependency.** Date parsing uses a fixed list of
  `strptime` formats (ISO, `Month DD, YYYY`, and the common numeric
  variants) rather than a general natural-language date parser, to avoid
  adding a dependency for something the ambiguity note above already
  requires manual review of.

## organize: plan, then confirm, then execute

`organize` follows the same validation-gate house style as
`pdf-operations`' form-filling workflow: it always builds and prints the
**full plan** first, and only ever touches the filesystem when you pass
`--execute`. Without `--execute` nothing is created, moved, copied, or
hashed-into-a-state-file -- not even the destination directory.

```
$ python3 scripts/invoice_tool.py organize ./inbox --dest ./Invoices --strategy vendor
Organization plan (strategy=vendor, dest=./Invoices)
  5 file(s) to organize
  1 file(s) skipped (already organized or exact duplicate)
  2 file(s) flagged needs_review -> routed to _NeedsReview/, original filename kept
  0 file(s) failed extraction

  ./inbox/adobe_march.pdf
    -> ./Invoices/Adobe Inc/2024-03-15 Adobe Inc - Invoice - INV-12345.pdf
  ./inbox/IMG_2847.pdf
    -> ./Invoices/_NeedsReview/IMG_2847.pdf [NEEDS REVIEW]
       reasons: vendor:low, date:low, invoice_number:missing
  ...

Dry run only -- no files were copied or moved. Re-run with --execute to apply this plan.
```

Review the plan (especially the `_NeedsReview/` entries), then re-run the
identical command with `--execute` to apply it.

**Filenames**: `YYYY-MM-DD Vendor - Invoice - <number>.ext`, or
`YYYY-MM-DD Vendor - Receipt.ext` when there's no invoice number.
**needs_review files bypass the naming scheme entirely** -- they are
copied into `<dest>/_NeedsReview/` under their *original* filename, never
renamed, because a filename built from a low-confidence field is worse
than no rename at all.

**Strategies** (`--strategy`, default `date`):

| Strategy | Folder layout |
|----------|----------------|
| `vendor` | `<dest>/<Vendor>/` |
| `date` | `<dest>/<year>/<month>/` |
| `category` | `<dest>/<year>/<Category>/` (see category map below) |
| `flat` | `<dest>/` (no subfolders) |

**Originals are preserved by default** (`shutil.copy2`); pass `--move` to
move instead.

## Idempotency

Running `organize --execute` twice on the same source/dest pair applies
nothing the second time. This is enforced two ways, not one:

1. **State file** -- `<dest>/.invoice-organizer-state.json` maps each
   source file's sha256 to where it landed and when.
2. **Ground-truth re-check** -- before trusting the state file's answer,
   the tool re-hashes the file it claims is already at that destination.
   If it's gone or has different content, the source is treated as not
   yet organized (state alone is never assumed correct -- same
   validate-against-reality principle as `pdf-operations`).

If a naming collision happens (a *different* file already sits at the
computed target path), the tool appends a disambiguating suffix
(`Name (2).pdf`) rather than overwriting anything.

`export-csv` is idempotent the same way, but by content: it reads any
existing output CSV's `sha256` column and only extracts + appends rows for
files not already present, so re-running it after adding a few new files
to the source directory appends just those new rows. Pass `--force` to
discard the existing file and rewrite the CSV from scratch.

## Duplicate detection: sha256, and its real limitation

Both `scan` and `organize` group candidate files by sha256 and treat any
group with more than one member as exact duplicates -- `organize` skips
all but the first (sorted by path) and says which file it's a duplicate
of.

**Be honest about what this does and doesn't catch**: sha256 comparison
only ever finds byte-identical files. It will catch the same PDF saved
twice, or emailed to two different folders. It will **not** catch a
receipt scanned twice at different DPI settings, the same invoice
re-exported to PDF with different metadata, or a photo and a scan of the
same paper receipt -- those produce different bytes even though a human
would call them "the same document." Detecting that class of near-duplicate
needs perceptual image hashing or OCR-text similarity, neither of which
this tool implements. If that matters for your use case, review the
`_NeedsReview` output and the vendor/date/amount fields by eye; the tool
will not flag a near-duplicate for you.

## export-csv: fixed schema, real escaping

The CSV schema is fixed and documented, not ad hoc:

```
source_path, sha256, vendor, vendor_confidence, invoice_number,
invoice_number_confidence, date, date_confidence, amount,
amount_confidence, currency, category, needs_review, review_reasons,
extraction_method
```

Rows are written with Python's `csv.DictWriter` (`QUOTE_MINIMAL`), so a
vendor name containing a comma or an embedded quote is escaped correctly
by the standard library rather than by hand-rolled string concatenation --
`Staples, Inc. "Office Superstore"` round-trips through the file exactly,
quoted as `"Staples, Inc. ""Office Superstore"""`. Never build this file
with `f"{a},{b},{c}"`.

## Not tax or accounting advice

`organize --strategy category` and `export-csv`'s `category` column
assign a category by matching keywords in the vendor name against a map
(`Software`, `Office Supplies`, `Travel`, `Professional Services`, else
`Uncategorized`). This is a **filing convenience only** -- it is not a
determination of what is tax-deductible, and the category names are not
IRS or any other tax authority's categories. The built-in map is
illustrative; pass `--category-map path/to/map.json` (a JSON object of
`{"Category Name": ["keyword", "keyword", ...]}`) to use your own.
Whether an expense is actually deductible, and under which category,
depends on jurisdiction, the nature of the business, and facts this tool
has no way to see from a filename or a total -- that determination belongs
to an accountant, not to a keyword match.

## PII and financial-data handling

Invoices and receipts routinely carry account numbers, partial card
numbers, billing addresses, and names -- treat this the same way
`session-handoff`'s redaction table treats credentials and PII: extracted
**field values** (vendor, date, amount, invoice number) are fine to print
and log, since that's the tool's whole job, but the **full raw document
text** is not printed by default. `extract --verbose` opts into printing
it and prints an explicit warning first; do not paste that output into
chat, a ticket, or a log if the source document carries anything more
sensitive than what already ended up in the four extracted fields. Treat
an `export-csv` output file itself as sensitive once it has real vendor
and amount data in it (keep it out of a public repo, redact before sharing
with a third party) for the same reason `session-handoff` treats a handoff
document as something that stays out of git history.

## Anti-patterns

- **Trusting a `low`-confidence or `missing` field as if it were certain.**
  That's exactly what `needs_review` and `_NeedsReview/` exist to prevent
  -- check them before relying on a renamed file or a CSV row.
- **Assuming sha256 duplicate detection catches near-duplicates.** It only
  catches byte-identical files; a rescanned or re-exported copy will not
  be flagged (see "Duplicate detection" above).
- **Building the CSV by hand-concatenating strings instead of using the
  `csv` module.** A vendor name with a comma or a quote will corrupt a
  hand-built CSV; `csv.DictWriter` handles it correctly.
- **Running `organize --execute` without reviewing the dry-run plan
  first.** The dry run is the default for a reason -- read it, especially
  the `_NeedsReview` section, before applying it.
- **Treating the `category` output as tax guidance.** It's a keyword match
  against an illustrative, user-overridable map, not a tax determination.
  See "Not tax or accounting advice" above.
- **Assuming a numeric slash-formatted date's ordering.** MM/DD and DD/MM
  are both plausible; this tool always flags such a match as low
  confidence instead of picking one silently.
- **Piping `extract --verbose` output into a shared log or chat without
  checking what's in it.** The full extracted text can carry more than
  the four structured fields; see "PII and financial-data handling."
- **Reinventing PDF text-vs-scanned detection instead of reusing
  `pdf-operations`' heuristic.** If you're extending this tool, keep the
  OCR decision consistent with that skill rather than adding a second,
  possibly-divergent threshold.

## Reference

- `scripts/invoice_tool.py` -- the dispatcher: `scan`, `extract`,
  `organize`, `export-csv`
- Related: `pdf-operations` (PDF reading, the OCR-needed heuristic this
  skill reuses)
- Related: `session-handoff` (the redaction convention this skill's
  PII/financial-data handling note follows)
- pytesseract: https://github.com/madmaze/pytesseract
- pypdf docs: https://pypdf.readthedocs.io/
- Python `csv` module: https://docs.python.org/3/library/csv.html

## When NOT to use

- **Accounting/bookkeeping logic** — this organizes files, not financial calculations.
- **Expense approval workflows** — use your finance platform, not file manipulation.
- **Non-invoice documents** — see [file-organizer](../documentation/file-organizer/SKILL.md) for general file management.


## Decision tree

```
What do you need?
├── Scan a folder of invoices?
│   ├── Preview what's found → invoice-organizer scan PATH (read-only report)
│   ├── Specific format → invoice-organizer scan --type pdf|xml|image PATH
│   └── Check extraction confidence → review low-confidence entries before acting
├── Rename files consistently?
│   ├── Standard pattern → invoice-organizer rename --pattern "{date}_{vendor}_{amount}" PATH
│   ├── Dry-run first → invoice-organizer rename --dry-run PATH (always)
│   └── Apply → invoice-organizer rename PATH (after confirming dry-run output)
├── Export structured data?
│   ├── CSV → invoice-organizer export --format csv PATH > invoices.csv
│   ├── JSON → invoice-organizer export --format json PATH
│   └── Filter by date → invoice-organizer export --since 2026-01-01 PATH
└── Something went wrong?
    ├── Wrong rename → undo log: invoice-organizer undo UNDO_LOG.json
    └── Bad extraction → check/fix manually, re-scan with --force
```

## Related skills

- [file-organizer](../documentation/file-organizer/SKILL.md) — general file organization patterns.
- [pdf-operations](../documentation/pdf-operations/SKILL.md) — extracting data from PDF invoices.
- [bash-scripting](../shell/bash-scripting/SKILL.md) — automating batch invoice processing.
