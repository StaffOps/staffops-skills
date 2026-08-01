---
name: pdf-operations
description: "Extract, merge, split, watermark, OCR, and fill PDF forms."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [pdf, file-operations, ocr, forms, reportlab, pypdf]
    category: documentation
    related_skills: [markdown-docs]
---

# PDF Operations

Programmatic PDF manipulation: extracting text and images, merging and
splitting files, rotating and watermarking pages, encrypting/decrypting,
falling back to OCR when there is no text layer, and filling both fillable
and non-fillable forms. This is general file-format tooling for working
with PDFs that already exist (or need light creation via reportlab) — it
deliberately does not cover authoring long-form documents from scratch; for
that, write in Markdown and render (see `markdown-docs`) or hand-author with
a word processor and export.

## When to Use

Use when a task involves a `.pdf` file on either end: extracting its text
or tables, combining or splitting PDFs, rotating or stamping pages,
password-protecting or removing protection, pulling out embedded images,
recovering text from a scanned document, or filling out a PDF form
(fillable or flat/scanned).

## One script, not a library-selection table

Every PDF task in this skill routes through a single dispatcher,
`scripts/pdf_tool.py`, with one subcommand per task:

```
python3 scripts/pdf_tool.py extract-text input.pdf [--pages 1-3,5] [-o out.txt]
python3 scripts/pdf_tool.py merge a.pdf b.pdf c.pdf -o merged.pdf
python3 scripts/pdf_tool.py split input.pdf --outdir out/ [--ranges 1-3,4-6]
python3 scripts/pdf_tool.py rotate input.pdf -o out.pdf --angle 90 [--pages 1,3]
python3 scripts/pdf_tool.py watermark input.pdf -o out.pdf --text "DRAFT"
python3 scripts/pdf_tool.py encrypt input.pdf -o out.pdf --user-password secret
python3 scripts/pdf_tool.py decrypt input.pdf -o out.pdf --password secret
python3 scripts/pdf_tool.py extract-images input.pdf --outdir images/
python3 scripts/pdf_tool.py ocr input.pdf -o out.txt [--dpi 300]
```

The point of one entry point is that the caller picks a *task*, not a
*library*. Internally the script reaches for pypdf for structural work
(merge/split/rotate/encrypt/extract-images), reportlab for the watermark
overlay, and pytesseract + pdf2image for `ocr` — but that choice is the
script's problem, not yours. `extract-text`, `merge`, `split`, and `rotate`
are the four operations covered here in full, hardened form; treat
`watermark`, `encrypt`/`decrypt`, and `extract-images` as solid but simpler
implementations, and `ocr` as dependent on external binaries (see below).

Every subcommand shares the same failure behavior: missing file, wrong or
missing password on an encrypted PDF, a corrupt/truncated file, an
out-of-range page number, or a non-90-degree rotation angle all stop the
run with a specific message on stderr and a non-zero exit code. None of
them catch a broad exception and limp forward — a script that produces a
half-merged PDF because page 4 of the third input failed silently is worse
than one that refuses to run.

## The validation-gate pattern (house style)

This skill's central technique, used everywhere from `rotate`'s angle check
to the form-filling workflow below, is: **validate every input against
ground truth before writing anything, and fail loud with a message that
names the specific field/page/value that's wrong.** Never let a mismatch
between what you assumed and what the PDF actually contains flow through
into a written file — a form field silently left blank, or a checkbox
silently set to the wrong state, costs far more to discover later than a
script that stops and says exactly what didn't match.

Concretely, apply the gate in two places for anything beyond the simple
dispatcher operations:

1. **Before you build the change** — confirm the target (field name, page
   index, coordinate) exists and is the type you think it is, by reading it
   back from the source of truth (the AcroForm field list, the extracted
   page structure, or the rendered image), not from memory or assumption.
2. **Before you write the change** — re-validate the full set of edits
   against that same ground truth (do the field IDs still exist, does the
   value fit the field's declared type and options, do bounding boxes
   overlap) and abort the write if anything fails.

The form-filling workflow below is this pattern applied end to end, plus a
third gate after writing: re-render the output and look at it, because a
technically valid PDF write can still be visually wrong (text overlapping a
line, a checkbox mark landing next to the box instead of inside it).

## Deciding when OCR is needed

Do not guess from the file's origin ("it came from a scanner" / "it came
from a fax") — check the actual extracted text. Run `extract-text` first;
it applies this rule automatically and prints a warning when triggered:

> **A PDF needs OCR when text extraction returns near-empty output (fewer
> than ~10 non-whitespace characters per page on average), or when the
> output is dominated by unresolved glyph-ID artifacts of the form
> `(cid:123)` instead of readable characters.**

Both symptoms mean the same thing: the page has no honest text layer.
`(cid:N)` output specifically means the PDF's font has a broken or
non-standard ToUnicode mapping — pypdf/pdftotext can see glyph indexes but
cannot translate them back to characters, which happens with some scanned
documents' fake text layers and some poorly-generated PDFs. In either case,
switch to `python3 scripts/pdf_tool.py ocr input.pdf`, which rasterizes each
page and runs tesseract over the image instead of trusting the embedded
text.

`ocr` needs binaries beyond the Python dependencies this skill otherwise
assumes: `tesseract` and poppler's `pdftoppm`. Install them with
`brew install tesseract poppler` (macOS) or
`apt-get install tesseract-ocr poppler-utils` (Debian/Ubuntu) before the
Python packages (`pip3 install --user pytesseract pdf2image`) will do
anything useful. The subcommand raises immediately with this exact guidance
if the imports fail — it does not fall back to returning empty text.

## Creating PDFs and the reportlab sub/superscript trap

For generating a new PDF (a report, a cover page, a watermark overlay),
reportlab is the standard choice: `canvas` for direct drawing, or
`platypus`'s `SimpleDocTemplate` + `Paragraph`/`Spacer`/`PageBreak` for
flowed, multi-page documents built from a list of story elements.

One gotcha is not obvious until it bites: **never put a Unicode
subscript/superscript character (U+2080-U+2089, U+2070-U+2079, etc.)
directly into text drawn with a reportlab built-in font.** The standard
fonts (Helvetica, Times, Courier) do not include those glyphs, and instead
of falling back to a normal digit or erroring, reportlab renders them as
solid black boxes with no warning at generation time — you only find out
when you open the PDF.

The fix is to never encode the subscript/superscript in the text itself.
Inside a `Paragraph`, use the `<sub>`/`<super>` markup tags, which reportlab
resolves by shrinking and shifting a normal-weight character rather than by
looking up a special glyph:

```python
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet

styles = getSampleStyleSheet()
water_formula = Paragraph("H<sub>2</sub>O", styles["Normal"])
pythagorean = Paragraph("a<super>2</super> + b<super>2</super> = c<super>2</super>", styles["Normal"])
```

For text drawn directly on a `canvas` (not inside a `Paragraph`), there is
no markup layer to fall back on — draw the base character at the normal
size, then draw the sub/superscript character separately at a smaller
`setFont` size, offset a few points up or down from the baseline.

## Filling PDF forms

Form-filling is not one more dispatcher subcommand: it needs an iterative,
look-at-the-result loop that a single non-interactive command can't
provide, so it is documented as a workflow in
[`references/forms.md`](references/forms.md) instead. The short version —
first check whether the PDF has real AcroForm fields, and let that answer
pick the path:

1. **Fillable fields exist** — read every field's id, page, rect, and type
   with pypdf (resolving radio-group parent/kid relationships, since a
   radio group's individual buttons are children carrying the actual
   `/Rect`, not the parent field itself). Render the pages to images purely
   to let a human or agent infer what each cryptically-named field
   (`Text12`, `Text13`, ...) *means*. Validate every proposed value against
   the extracted field list before writing anything — right type, and for
   checkboxes/radios/choice fields, one of the field's own declared option
   values, not a guess.
2. **No fillable fields, but a real text layer** — extract label positions,
   ruled lines, and checkbox-shaped rectangles from the page structure, and
   infer each entry area's bounding box from where its label ends and the
   next boundary begins.
3. **No fillable fields and no usable text layer (a flat scan)** — render
   to an image, roughly place each field by eye, then re-render a zoomed
   crop around each rough estimate to pin down exact pixel coordinates
   before converting them to PDF point space.
4. **Hybrid** — tier 2 for whatever it found, tier 3's zoom-and-refine only
   for what it missed (a circular checkbox, an unusual control), all
   coordinates normalized into the same space before writing.

Every tier converges on the same JSON field manifest, the same
validate-before-write gate (no overlapping boxes, no entry box shorter than
its font size), and the same final step: re-render the filled PDF to images
and visually confirm placement. `references/forms.md` has the full
decision tree, the manifest schema, and the coordinate-conversion math for
each tier, plus the known fragility of the checkbox-detection heuristic
(see next section for the short version).

## Anti-patterns

- **Assuming OCR is or isn't needed from the file's origin.** Check the
  actual extracted text (near-empty output, or `(cid:N)` artifacts) — a
  "scanned" PDF sometimes has a real text layer already, and a
  "digital" PDF sometimes doesn't.
- **Trusting the checkbox-detection heuristic on its own.** Small
  near-square rectangles (roughly 5-15pt on a side) are a *candidate*
  signal for a checkbox, not proof — circular checkboxes, symbol-font
  glyphs, and coincidentally checkbox-sized unrelated controls all defeat
  it. Always cross-check a detected checkbox against the rendered page
  image before writing to it.
- **Writing form values without validating against the extracted field
  list first.** A field name typo, a checkbox value that isn't one of its
  two real on/off states, or a choice value that isn't in the field's
  option list all produce a PDF that looks fine in the write call's return
  value and wrong when opened.
- **Skipping the re-render-and-look step after filling a form.** A
  successful write is not the same thing as correct placement — text can
  overlap a printed line, or land outside the box entirely, and the only
  way to catch that is to look at the rendered result.
- **Unicode subscript/superscript characters in reportlab text.** They
  render as black boxes with built-in fonts; use `<sub>`/`<super>` markup
  in a `Paragraph`, or a manually offset smaller font on a raw `canvas`.
- **Catching a broad exception and continuing** in any PDF script — a
  missing password, a corrupt page, or an out-of-range page number should
  stop the run with a specific message, not produce a partially-correct
  output file.
- **Reaching for OCR by default.** It is slower, lossier, and needs
  external binaries; only use it once `extract-text`'s heuristic (or a
  direct look at the extracted output) confirms there's no real text layer.

## Reference

- `scripts/pdf_tool.py` — the dispatcher covering extract-text, merge,
  split, rotate, watermark, encrypt, decrypt, extract-images, and ocr
- `references/forms.md` — the full form-filling decision tree, manifest
  schema, and checkbox-heuristic caveats
- pypdf docs: https://pypdf.readthedocs.io/
- pdfplumber docs: https://github.com/jsvine/pdfplumber
- reportlab user guide: https://www.reportlab.com/docs/reportlab-userguide.pdf
- pytesseract: https://github.com/madmaze/pytesseract
- Related: `markdown-docs` (authoring a new document instead of
  manipulating an existing PDF)
