---
name: image-enhancer
description: "Upscale, sharpen, denoise, and resize images via Pillow."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [image, upscale, sharpen, denoise, pillow, resize]
    category: documentation
    related_skills: [pdf-operations]
---

# Image Enhancer

Programmatic image enhancement: upscaling via Lanczos resampling (with an
optional Real-ESRGAN path if that binary happens to be installed),
unsharp-mask sharpening, median/Gaussian denoising, and resizing to explicit
dimensions or named presets. Every operation reports an objective before/after
sharpness number instead of a claim like "enhanced clarity". This is
classical image processing, not an AI-generation or inpainting tool — it
never invents pixels that weren't implied by the input; it resamples,
convolves, and filters the pixels that are already there.

## When to Use

Use when a task involves making an existing raster image (screenshot, photo,
graphic) larger, sharper, less noisy, or a specific target size: upscaling a
low-resolution screenshot before it goes into a document, sharpening a
slightly soft photo, cleaning up salt-and-pepper noise from a scan or a
low-quality capture, or resizing a batch of images to a specific pixel target
for a platform or presentation. It does not cover generating new image
content, removing objects (inpainting), style transfer, or color grading —
none of those are implemented here.

## One script, not a library-selection table

Every operation in this skill routes through a single dispatcher,
`scripts/image_tool.py`, with one subcommand per task:

```
python3 scripts/image_tool.py upscale input.png -o out.png --scale 2 [--method lanczos|realesrgan]
python3 scripts/image_tool.py resize input.png -o out.png (--width 1920 --height 1080 | --preset 1080p) [--keep-aspect]
python3 scripts/image_tool.py sharpen input.png -o out.png [--radius 2.0] [--percent 150] [--threshold 3]
python3 scripts/image_tool.py denoise input.png -o out.png [--method median|gaussian] [--size 3]
python3 scripts/image_tool.py metrics input.png
python3 scripts/image_tool.py batch indir/ --op sharpen --outdir out/ [op-specific flags]
```

Internally it reaches for Pillow (`PIL.Image`, `ImageFilter`, `ImageOps`) for
every operation — there is no numpy or OpenCV dependency, because neither is
needed for any of the techniques used here (see below for exactly what each
one does). `upscale`, `resize`, `sharpen`, and `metrics` are covered in full,
tested form; `denoise` and `batch` share the same code paths and safety
gates. None of the subcommands catch a broad exception and continue — a
missing file, a bad page/size argument, or a corrupt image stops the run
with a specific message on stderr and a non-zero exit code, the same house
style as `pdf-operations`.

## Objective quality metric: variance of the Laplacian

Instead of a subjective "looks sharper" claim, `metrics` and every
enhancement subcommand report the **variance of the Laplacian** — a
long-established blur/sharpness metric (Pech-Pacheco et al., 2000, still the
standard reference implementation people reach for with OpenCV). Convert the
image to grayscale, convolve it with the discrete Laplacian kernel

```
 0  1  0
 1 -4  1
 0  1  0
```

(each pixel's four direct neighbors summed, minus four times the pixel
itself — the discrete second derivative), and take the variance of that
response across the whole image. A sharp image has strong, varied edge
content, so the response swings widely (high variance); a blurry image's
edges are smoothed out, so the response stays close to zero everywhere (low
variance). `laplacian_variance()` in the script does this convolution in
plain Python floats rather than through Pillow's 8-bit `ImageFilter.Kernel`
(which clips negative responses to 0 and would bias the number) — there is
no numpy in this environment, so it's a nested loop over pixels, downsampled
first (Lanczos, capped at a 1600px long edge) on large images purely for
speed. That cap is a documented approximation: it discards detail above the
capped resolution, so treat before/after pairs computed through the same cap
(which every subcommand does automatically) as valid, and don't compare an
absolute score for a heavily-downsampled huge image against one computed at
native resolution for a small one.

**Real example, not a fabricated one.** Generated a 640x480 synthetic test
image with real edge content (a checkerboard block, ruled lines, text), then
produced a blurred variant (Gaussian blur radius 3) and ran the tool against
both:

```
$ python3 image_tool.py metrics sharp_original.png
sharpness (variance of Laplacian): 12762.2

$ python3 image_tool.py metrics blurry.png
sharpness (variance of Laplacian): 11.6

$ python3 image_tool.py sharpen blurry.png -o blurry_sharpened.png
sharpened -> blurry_sharpened.png
sharpness (variance of Laplacian): 11.6 -> 30.7
```

Sharpening only partially recovers the score (11.6 -> 30.7, nowhere near the
original's 12762.2) — an honest result, not a bug: an unsharp mask
accentuates whatever edge contrast survived the blur, it does not
reconstruct detail a Gaussian blur has already destroyed. Expect `sharpen`
to make a slightly soft image read as crisper, not to undo a heavy blur.

**A sharper gotcha: salt-and-pepper noise inflates this metric, it doesn't
lower it.** Adding salt noise to just 0.5% of the same blurred image's
pixels (1,536 out of 307,200) pushes the score far *above* even the sharp
original's:

```
$ python3 image_tool.py metrics blurry_noisy.png
sharpness (variance of Laplacian): 2643.4

$ python3 image_tool.py denoise blurry_noisy.png -o blurry_denoised.png --method median --size 3
denoised (median) -> blurry_denoised.png
sharpness (variance of Laplacian): 2643.4 -> 18.1
```

Each salt/pepper pixel is a single-pixel discontinuity against its
neighbors — exactly the shape of high-frequency signal a per-pixel Laplacian
reacts to hardest, so a small fraction of noise pixels can swing this metric
further than genuine focus does. Median filtering, which specifically
targets impulse noise, drops the score back down near the noise-free
blurred baseline (2643.4 -> 18.1) — a large drop that reads as "got worse"
if you only watch the number, when what actually happened is the noise
spikes got removed. This is the sharpest version of the same lesson: judge
denoise by whether the *visible* noise is gone, not by whether this number
went up or down.

**Important caveat: the metric is not scale-invariant.** Upscaling the same
sharp source 2x with Lanczos took its score from 12762.2 down to 1068.8 — a
~12x drop with zero loss of visual quality, because spreading the same edge
transition across more pixels lowers the discrete second derivative's
magnitude at each one. Don't use this metric to judge an `upscale` output
against its smaller input; it's only a like-for-like comparison when
dimensions are unchanged (`sharpen`, `denoise`), or when comparing two
upscales of the *same* target size against each other (e.g. Lanczos vs.
Real-ESRGAN at the same output resolution).

There is no universal "good" threshold — a photo of a foggy landscape can
legitimately score lower than a screenshot of text, and different image
sizes aren't comparable either. Use the number to compare a before/after
pair of the same image at the same dimensions, not as an absolute quality
gate across unrelated images.

## Concrete pixel targets, not marketing terms

"4K" and "retina" mean different things depending on who's asking. This
tool's `resize --preset` uses actual pixel dimensions instead:

| Preset | Pixels | What it actually is |
| --- | --- | --- |
| `4k` | 3840x2160 | 4K UHD (not DCI 4K's 4096x2160) |
| `1440p` | 2560x1440 | QHD |
| `1080p` | 1920x1080 | Full HD |
| `720p` | 1280x720 | HD |
| `instagram-square` | 1080x1080 | Instagram square post |
| `instagram-portrait` | 1080x1350 | Instagram portrait post (4:5) |
| `twitter-post` | 1600x900 | Twitter/X in-stream image |
| `linkedin-post` | 1200x627 | LinkedIn shared-link image |
| `facebook-post` | 1200x630 | Facebook shared-link image |

"Retina" isn't a fixed resolution — it's a density multiplier relative to a
layout size (typically 2x or 3x the CSS pixel dimensions), so it isn't a
preset here; compute the target pixels yourself (`--width`/`--height`) from
the layout size and multiplier you actually need, or use `upscale --scale 2`
against the base-resolution asset. Platform presets above are frequently
revised by the platforms themselves — verify against current guidance before
relying on one for anything pixel-critical (e.g. an ad spec).

## Safety pattern: never overwrite the original

Every subcommand that writes an image (`upscale`, `resize`, `sharpen`,
`denoise`, `batch`) calls `_require_new_output()` before touching the
filesystem, which refuses to run if the resolved output path is the same
file as the input:

```
$ python3 image_tool.py sharpen sharp_original.png -o sharp_original.png
error: refusing to overwrite the input file in place (sharp_original.png).
Write to a new path -- this tool never modifies an original.
```

`batch` has the equivalent directory-level gate: `--outdir` may not resolve
to the same directory as the input directory. This is a hard behavior in the
script, not a suggestion in this doc — there is no `--force` flag to bypass
it, matching `pdf-operations`' validate-before-write house style.

## Format and edge-case handling

Every image is opened through `open_image()`, which applies three explicit,
documented behaviors instead of leaving them undefined:

- **EXIF orientation: respected, actively.** `ImageOps.exif_transpose` runs
  on every input before any processing, so a JPEG tagged `Orientation: 6`
  (rotated 90 CW) comes out physically rotated in the output, with the
  now-redundant orientation tag dropped — not passed through for the next
  viewer to apply again. Verified against a real EXIF-tagged JPEG in
  testing: a 300x200 source tagged `Orientation: 6` produced a 200x300
  output, confirming the transpose actually ran (Pillow's
  `exif_transpose` also drops the `.format` attribute on the object it
  returns as a side effect; `open_image()` restores it explicitly so
  `metrics` and format-from-extension saving both still work).
- **Alpha channels: filtered separately from color, never blurred/sharpened
  themselves.** `sharpen` and `denoise` split an RGBA/LA input into its
  color bands and its alpha band (`split_alpha()`), run the filter on color
  only, and reattach the *original, unmodified* alpha afterward
  (`merge_alpha()`). Running an unsharp mask or median filter across the
  alpha band too would blur or ring transparency edges — verified in testing
  by diffing a filtered RGBA output's alpha channel against the input's and
  confirming it's pixel-identical while the color channels changed.
  `upscale`/`resize` resample the alpha band together with color (desired —
  a resized transparency edge should stay smooth), so this splitting is
  specific to the convolution-based filters.
- **Palette-mode images (indexed PNGs, every GIF frame): converted before
  filtering, not passed through as-is.** Pillow's `ImageFilter` kernels only
  operate on `L`/`RGB`/`CMYK`-class modes and raise `ValueError` on raw `P`
  data, so `split_alpha()` converts a `P` image to `RGBA` when it carries a
  `transparency` info entry and to `RGB` otherwise (`PA`/`1` convert
  similarly) before `sharpen`/`denoise` ever call `.filter()`. The output is
  therefore a full-color image, not requantized back to the source palette —
  correct for a filter that can introduce colors the original palette never
  had, but it means a `sharpen`/`denoise` pass on an indexed PNG will not
  itself come out indexed. Verified against both a plain adaptive-palette
  PNG and a GIF-style `P` image carrying a `transparency` info entry.
- **Animated GIFs: frame 0 only, with an explicit warning, never silent.**
  Pillow's `Image.open` loads frame 0 of a multi-frame image by default;
  this tool does not seek through or re-encode the remaining frames. Every
  operation prints `WARNING: <path> has N frames (animated). This tool
  processes frame 0 only -- the rest of the animation is dropped from the
  output.` before proceeding — confirmed against a real 3-frame test GIF.
  If you need the whole animation enhanced frame-by-frame, extract frames
  with a separate tool first and run `batch` against the extracted
  directory.

## Upscaling quality: Lanczos baseline vs. optional Real-ESRGAN

The default and only *guaranteed-available* upscale method is **Lanczos
resampling** (`Image.Resampling.LANCZOS`) — a well-established, deterministic
interpolation filter, not a learned super-resolution model. It produces
smooth, artifact-free enlargements but does not hallucinate detail that
wasn't in the source; a heavily downscaled photo upscaled with Lanczos will
look soft, not sharp, because there's no missing information for it to
invent.

`--method realesrgan` shells out to a `realesrgan-ncnn-vulkan` binary if one
is already on `PATH` (or at the path given via `--realesrgan-bin`) — this
script does **not** bundle, vendor, or install Real-ESRGAN, and does not
claim it's available without checking. If the binary isn't found, or the
subprocess call fails or times out, the tool prints a warning naming exactly
what happened and falls back to Lanczos rather than erroring or silently
producing no output. This fallback path was exercised in testing (no
Real-ESRGAN binary is installed in the environment this skill was built and
tested in):

```
$ python3 image_tool.py upscale sharp_original.png -o out.png --scale 2 --method realesrgan
WARNING: --method realesrgan requested but 'realesrgan-ncnn-vulkan' was not
found on PATH. Falling back to Lanczos. Install Real-ESRGAN-ncnn-vulkan
(https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases) to get this
method for real.
upscaled (lanczos) 640x480 -> 1280x960 -> out.png
```

If you install Real-ESRGAN and want to actually verify it's producing a
different (and hopefully better) result than the fallback, compare its
output's Laplacian-variance score against a Lanczos upscale *of the same
target size* — not against the original at its smaller size (see the
scale-dependence caveat above).

## Anti-patterns

- **Trusting a "before/after" claim with no number attached.** If an
  enhancement claim can't be backed by `metrics` output (or the automatic
  before/after this tool's subcommands print), it's a vibe, not a result —
  this is exactly the failure mode of the prose-only version this skill
  replaced.
- **Comparing Laplacian-variance scores across different image dimensions.**
  The metric is not scale-invariant (see above) — an upscale's score isn't
  comparable to its source's score, and two different-sized images aren't
  comparable to each other.
- **Assuming `--method realesrgan` is installed without checking the
  script's own warning.** It shells out to an external binary this script
  doesn't vendor; read the fallback warning rather than assuming the
  higher-quality path ran.
- **Running a sharpen or denoise filter across an alpha channel.** Use this
  tool's built-in split/merge behavior (automatic for `sharpen`/`denoise`)
  rather than filtering an RGBA image directly with a library call that
  touches all four bands — it will ring or blur the transparency mask.
- **Ignoring the animated-GIF warning and assuming the whole animation was
  processed.** This tool is frame-0-only; if the warning printed, every
  frame after the first is missing from the output entirely, not merely
  unenhanced.
- **Writing output to the same path as the input.** The script refuses this
  outright (see the safety pattern above); don't work around it by renaming
  after the fact in a way that could race with a partially-written file.
- **Reaching for "4K" or "retina" as a target without picking actual pixel
  numbers.** Use `resize --preset` (concrete dimensions) or compute the
  exact pixels a "retina" density multiplier implies for your layout.
- **Catching a broad exception and continuing** in any modification to this
  script — a missing file, an even `--size` for median filtering, or a
  corrupt image should stop the run with a specific message, not produce a
  silently wrong output file.

## Reference

- `scripts/image_tool.py` — the dispatcher covering upscale, resize,
  sharpen, denoise, metrics, and batch
- Pech-Pacheco et al., "Diatom autofocusing in brightfield microscopy: a
  comparative study" (2000) — origin of the variance-of-Laplacian
  sharpness metric
- Pillow docs: https://pillow.readthedocs.io/
- `ImageFilter.UnsharpMask`: https://pillow.readthedocs.io/en/stable/reference/ImageFilter.html#PIL.ImageFilter.UnsharpMask
- `ImageOps.exif_transpose`: https://pillow.readthedocs.io/en/stable/reference/ImageOps.html#PIL.ImageOps.exif_transpose
- Real-ESRGAN-ncnn-vulkan releases (optional, not vendored): https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases
- Related: `pdf-operations` (same validate-before-write, single-dispatcher
  house style, applied to PDFs instead of raster images)

## When NOT to use

- **Vector graphics or diagrams** (Mermaid, drawio) — see [diagram-patterns](../documentation/diagram-patterns/SKILL.md).
- **Video processing** — different toolchain (ffmpeg).
- **AI image generation** — this skill is for enhancing/processing existing images.


## Decision tree

```
What's wrong with the image?
├── Too small / low resolution?
│   ├── 2× upscale → image-enhancer upscale --scale 2 INPUT OUTPUT
│   ├── Target dimensions → image-enhancer upscale --width 1920 INPUT OUTPUT
│   └── Check quality → compare Laplacian variance before/after
├── Blurry / soft?
│   ├── Light sharpen → image-enhancer sharpen --strength low INPUT OUTPUT
│   ├── Heavy sharpen → image-enhancer sharpen --strength high INPUT OUTPUT
│   └── Already noisy? → denoise FIRST, then sharpen
├── Noisy / grainy?
│   ├── Uniform noise → image-enhancer denoise INPUT OUTPUT
│   ├── Preserve edges → image-enhancer denoise --preserve-edges INPUT OUTPUT
│   └── Extreme noise → multiple passes (diminishing returns after 2)
└── Need specific dimensions?
    ├── Downscale (for web) → image-enhancer resize --width 800 INPUT OUTPUT
    ├── Crop to aspect ratio → image-enhancer resize --crop 16:9 INPUT OUTPUT
    └── Never upscale via resize → use upscale subcommand instead
```

## Related skills

- [pdf-operations](../documentation/pdf-operations/SKILL.md) — images embedded in PDFs.
- [file-organizer](../documentation/file-organizer/SKILL.md) — organizing image assets.
- [markdown-docs](../documentation/markdown-docs/SKILL.md) — embedding enhanced images in docs.
