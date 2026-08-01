# Filling PDF Forms — the Decision Tree

This is the detailed workflow referenced from the main skill. Read it
before writing any form-filling code — the tier you land in changes both
the tool you use and the coordinate system you work in, and picking the
wrong one produces a form that looks filled but is wrong.

Every tier below ends at the same two gates: validate the proposed values
or coordinates against ground truth before writing, and re-render the
output afterward to confirm it visually. See the main `SKILL.md`'s
"validation-gate pattern" section for why that ordering matters.

## Step 0: Does the PDF have real fillable fields?

```python
from pypdf import PdfReader

reader = PdfReader("input.pdf")
fields = reader.get_fields()
print(f"{len(fields or {})} fillable field(s)")
```

- `fields` non-empty -> go to **Tier 1: Fillable fields**.
- `fields` empty or `None` -> go to **Tier 2: Structure extraction** first;
  fall back to **Tier 3: Visual estimation** only if that finds nothing
  usable.

## Tier 1: Fillable fields (AcroForm)

This is the reliable path — the PDF already declares where each field is
and what kind it is. The work is reading that declaration correctly, not
guessing geometry.

### 1.1 Extract field metadata

For each field, you need: a stable identifier, which page it's on, its
bounding box, and its type (`text`, `checkbox`, `radio_group`, or
`choice`). `reader.get_fields()` gives you the field dictionary, but two
details need extra handling:

- **Radio groups.** A radio group is represented as one parent field (the
  `/T` name you'll use to set a value) whose actual clickable widgets are
  child annotations (`/Kids`) spread across the page's `/Annots` array.
  The parent has no `/Rect` of its own — you have to walk each page's
  annotations, follow each annotation's `/Parent` chain back up to find
  which group it belongs to, and collect the *kid's* rect plus its "on"
  appearance-state name (from its `/AP /N` appearance dictionary) as the
  value that selects that particular radio button.
- **Checkboxes.** A checkbox field's two states are not reliably named
  `/Yes` and `/Off` — read the actual state names off the field's
  appearance dictionary. Treat whichever state isn't `/Off` as the
  "checked" value; if the checkbox exposes more than two states or neither
  is `/Off`, that is unusual enough to flag and check visually rather than
  guess.

Write the result to a field-info file (JSON is fine) with, per field: id,
page, rect, type, and — for checkboxes, radio groups, and choice fields —
the exact set of legal values. This file is the ground truth every value
gets validated against in step 1.3.

### 1.2 Render pages to images, for meaning, not geometry

Convert each page to a PNG (see `scripts/pdf_tool.py`'s use of `pypdf`
plus any rasterizer, or a dedicated renderer like `pdf2image` /
`pypdfium2`). The purpose here is entirely different from Tier 3: you are
not deriving coordinates from the image — pypdf already gave you exact
`/Rect` values in PDF point space. You are looking at the rendered page to
figure out what a cryptically-named field (`Text12`, `Text13`, `c1_1[0]`)
actually represents, by reading the label printed next to it.

Build a mapping from field id to intended value based on that visual read,
with a short human-readable description of what each field is for
alongside the value — that description is what makes a later validation
failure ("field `Text12`, described as 'spouse's employer', got value X")
actionable instead of cryptic.

### 1.3 Validate before writing

For every field you're about to set, check against the field-info file
from 1.1:

- The field id exists.
- For `checkbox`: the value is exactly the field's checked or unchecked
  state, nothing else.
- For `radio_group`: the value matches one of that group's kids' "on"
  values.
- For `choice`: the value matches one of the field's declared options.
- For `text`: no type constraint, but check it against any obvious length
  limit implied by the field's bounding box if the form is dense.

If any field fails, stop. Report every failing field and why, not just the
first one — a form usually has more than one wrong field if one is wrong,
and fixing them one at a time wastes a full pass per field.

### 1.4 Write and re-render

Once every value passes validation, set them on a `PdfWriter` (pypdf
exposes this via the writer's form-field update method, matched by the
field's full dotted name for nested fields) and write the output. Then
render the output back to images and look at it — a value that passed
type validation can still be visually wrong, most often because the wrong
field id had the right type by coincidence.

## Tier 2: Structure extraction (no fillable fields, real text layer)

This applies to forms that were designed to be filled by hand or with a
typewriter and were never converted to AcroForm — common for PDFs
generated from templates that flatten the form into plain text and vector
lines. There's a real text layer, so extraction is trustworthy; there's
just no declared "field" to read a rect from.

### 2.1 Extract labels, lines, and checkbox candidates

Use `pdfplumber` to pull, per page:

- Every text run with its exact bounding box (`x0`, `top`, `x1`, `bottom`
  in PDF points, top-down).
- Horizontal lines (`page.lines` / `page.rects` filtered to near-zero
  height) — these define row boundaries.
- Small rectangles with roughly equal width and height (see the fragility
  note below) as checkbox candidates.

If the extracted text is dominated by `(cid:N)` artifacts or is
near-empty, stop — this is not a Tier 2 PDF, it's a scan. Go to Tier 3 (or
straight to `pdf_tool.py ocr` if the goal is reading the form rather than
filling it).

### 2.2 Group labels into fields and infer entry geometry

- Adjacent text runs at the same `top` with a small horizontal gap are
  usually one label split across runs ("Last" + "Name").
- Runs sharing a `top` value (within a small tolerance) are in the same
  row.
- An entry area's bounding box is inferred, not extracted: it starts a
  few points after its label's right edge, and extends to the next
  label's left edge or the nearest row-boundary line, whichever comes
  first.
- Checkbox candidates get their bounding box directly from the rectangle
  — no inference needed, only the fragility caveat below.

### 2.3 Handle what structure extraction misses

Circular checkboxes, decorative or non-rectangular controls, and very
faint lines are common gaps. If a field is visible in the rendered page
but absent from the extracted structure, don't force it into Tier 2 —
switch to Tier 3's zoom-refinement for that one field and combine the
results (see **Hybrid**, below).

## Tier 3: Visual estimation (flat scan, no usable text layer)

This is the fallback when there's nothing to extract from — the page is
effectively a photograph of a form.

### 3.1 Render and rough-place

Render each page to an image at a reasonable DPI (200-300 is usually
enough to read labels; go higher only if the source scan is high-DPI). By
eye, note the approximate pixel location of each label and its
corresponding entry area or checkbox. These estimates do not need to be
precise yet — they only need to be close enough to know where to crop
next.

### 3.2 Zoom-refine every field before trusting its coordinates

A rough estimate at full-page resolution is not accurate enough to avoid
overlapping a neighboring label or missing a checkbox by a few pixels.
For each field, crop a padded region around the rough estimate (the field
area plus roughly 50px of margin on each side) and look at the crop in
isolation to find the precise pixel boundaries of the entry area.

Convert the coordinates found in the crop back to full-page pixel space by
adding the crop's own offset:

```
full_x = crop_x + crop_offset_x
full_y = crop_y + crop_offset_y
```

### 3.3 Convert pixel coordinates to PDF points before writing

Annotations and drawn text are placed in PDF point space, not image pixel
space. Convert using the ratio between the page's PDF dimensions and the
rendered image's pixel dimensions:

```
pdf_x = pixel_x * (pdf_width / image_width)
pdf_y = pixel_y * (pdf_height / image_height)
```

Keep track of which coordinate system each field's numbers are in until
this conversion happens — mixing pixel and point coordinates in the same
manifest is the most common source of a form that fills in the wrong
place.

## Hybrid: structure extraction plus targeted visual refinement

When Tier 2 handles most fields but misses a few (typically checkboxes
that aren't square, or a handful of non-standard controls):

1. Use Tier 2's output for every field it found.
2. Render to images only to zoom-refine the fields it missed, using Tier
   3's crop-and-refine technique for just those.
3. Convert the visually-estimated fields' pixel coordinates to PDF points
   (3.3), so the final manifest is entirely in one coordinate system.
4. Validate the combined manifest as one set (next section) — don't
   validate Tier 2's fields and Tier 3's fields separately, since overlap
   between a structure-extracted field and a visually-estimated one is
   exactly the kind of bug the validation gate exists to catch.

## Validate before filling (Tiers 2 and 3, and the hybrid)

Before writing anything, check the full field manifest for:

- **Overlapping bounding boxes** — any two boxes (label-vs-label,
  label-vs-entry, entry-vs-entry) that intersect will produce visually
  garbled output when both are rendered. Compare every pair on the same
  page.
- **Entry boxes too small for their text** — if an entry's height is less
  than the font size chosen for the value going into it, the text will be
  clipped or overflow the box. Either grow the box or shrink the font.

Fix every reported problem in the manifest before filling — don't fill and
fix in a second pass, since a second pass means the first PDF was wrong
and the manifest still needs the same correction.

## Fill, then re-render and look

Fill the form (annotation-based text/mark placement for Tiers 2/3 and the
hybrid; form-field update for Tier 1), then render the *output* PDF back
to images and look at it. If placement is off:

- **Tier 1**: the value most likely went to the wrong field id — recheck
  1.1's field-info extraction, not the coordinates (Tier 1 doesn't compute
  its own coordinates).
- **Tier 2**: recheck the row/column inference in 2.2 — a mis-identified
  row boundary shifts every entry in that row.
- **Tier 3 / hybrid**: recheck the pixel-to-point conversion in 3.3 first
  — a swapped width/height or a stale image-dimension value is the most
  common cause of a systematic offset across the whole page.

## Known limitation: the checkbox-detection heuristic is fragile

Tier 2's checkbox candidates come from a simple geometric heuristic: a
rectangle whose width and height both fall roughly in the 5-15pt range and
whose aspect ratio is close to 1:1. This heuristic is convenient and wrong
often enough to matter:

- Circular checkboxes (common in government and legal forms) are not
  rectangles at all and won't be found this way.
- Checkboxes rendered as glyphs from a symbol font (a "☐" character
  positioned like text) look like a text run, not a rect, and also won't
  be found.
- Any other small square-ish decoration or unrelated control (a bullet
  box, a small logo placeholder) can be misclassified as a checkbox.

**Treat every heuristic-detected checkbox as a candidate, never as
confirmed, and always cross-check it against the rendered page image
before writing a mark into it.** When a checkbox from the rendered image
doesn't show up in the geometric candidates, that's expected behavior, not
a bug — route it through Tier 3's zoom-refinement instead of trying to
loosen the heuristic's thresholds, since loosening them trades missed
checkboxes for false positives on ordinary small text runs and table
borders.

## Field manifest schema (reference)

A minimal manifest entry, regardless of tier, needs:

```json
{
  "page_number": 1,
  "field_id": "last_name",
  "description": "Last name entry field",
  "type": "text",
  "coordinate_space": "pdf_points",
  "entry_bounding_box": [92.0, 713.0, 260.0, 729.0],
  "value": "Smith",
  "font_size": 10
}
```

`coordinate_space` is worth carrying explicitly (`pdf_points` vs
`image_pixels`) even after every field has been normalized to
`pdf_points` for writing — it documents which tier each field came from,
which is exactly the information you need when a specific field's
placement needs debugging later.
