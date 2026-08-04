#!/usr/bin/env python3
"""image_tool.py -- single-entry-point dispatcher for classical image
enhancement operations: upscale, resize, sharpen, denoise, metrics, batch.

Design goal, matching pdf_tool.py's house style: the caller picks a *task*,
not a *library*. Everything here is classical image processing (resampling,
convolution filters) via Pillow -- there is no AI generation, inpainting, or
content-aware upscaling model bundled with this script. `upscale --method
realesrgan` will shell out to a Real-ESRGAN ncnn-vulkan binary IF one is
already installed and on PATH, and falls back to Lanczos with a printed
warning if it is not -- this script never claims that dependency is present
without checking.

House style (see SKILL.md's "Objective quality metric" and "Safety pattern"
sections): every subcommand refuses to overwrite its input file, and
upscale/sharpen/denoise print a before/after sharpness number (variance of
the Laplacian, a real, well-known blur metric -- see `laplacian_variance`)
instead of an unverifiable claim like "enhanced clarity".

Usage:
    python3 image_tool.py upscale input.png -o out.png --scale 2 [--method lanczos|realesrgan]
    python3 image_tool.py resize input.png -o out.png (--width W --height H | --preset 4k) [--keep-aspect]
    python3 image_tool.py sharpen input.png -o out.png [--radius 2.0] [--percent 150] [--threshold 3]
    python3 image_tool.py denoise input.png -o out.png [--method median|gaussian] [--size 3]
    python3 image_tool.py metrics input.png
    python3 image_tool.py batch indir/ --op sharpen --outdir out/ [op-specific flags]

Each subcommand exits 0 on success and non-zero with a message on stderr on
failure. There is no "partial success" exit path.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif"}

# Concrete pixel targets -- see SKILL.md's "Concrete pixel targets" section
# for why these replace vague terms like "4K" or "retina" in this tool's
# vocabulary. (width, height), all landscape/native orientation; swap width
# and height yourself for a portrait crop.
RESIZE_PRESETS: dict[str, tuple[int, int]] = {
    "4k": (3840, 2160),  # 4K UHD
    "1440p": (2560, 1440),  # QHD
    "1080p": (1920, 1080),  # Full HD
    "720p": (1280, 720),  # HD
    "instagram-square": (1080, 1080),
    "instagram-portrait": (1080, 1350),
    "twitter-post": (1600, 900),
    "linkedin-post": (1200, 627),
    "facebook-post": (1200, 630),
}


class ImageToolError(Exception):
    """Raised for any expected failure. Caught once, at the top level, and
    printed without a traceback -- tracebacks are for bugs in this script,
    not for a caller passing a bad path or an out-of-range parameter."""


def _require_file(path_str: str) -> Path:
    path = Path(path_str)
    if not path.exists():
        raise ImageToolError(f"input file not found: {path}")
    if not path.is_file():
        raise ImageToolError(f"not a file: {path}")
    return path


def _require_new_output(output_str: str, input_path: Path) -> Path:
    """Hard safety gate: refuse to write to the same file the input was
    read from. This is not a suggestion in prose -- every subcommand that
    writes an image calls this before touching the filesystem, the same
    way pdf_tool.py never lets a caller clobber a source PDF in place.
    """
    output_path = Path(output_str)
    if output_path.exists() and output_path.resolve() == input_path.resolve():
        raise ImageToolError(
            f"refusing to overwrite the input file in place ({output_path}). "
            "Write to a new path -- this tool never modifies an original."
        )
    if output_path.parent != Path("") and not output_path.parent.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def open_image(path: Path):
    """Open an image, apply EXIF orientation, and warn (but not fail) on
    formats/frames this tool has a documented limitation with.

    EXIF orientation: this tool ALWAYS calls `ImageOps.exif_transpose`
    before doing anything else, so a photo taken with a phone held
    sideways comes out right-side-up in the output rather than carrying a
    now-stale orientation tag forward. See SKILL.md's "Format/edge-case
    handling" section.

    Animated GIFs: Pillow's `Image.open` loads frame 0 of a multi-frame
    GIF by default; this tool does not seek to or re-encode the remaining
    frames. Every operation here (upscale/resize/sharpen/denoise) is
    frame-0-only and prints a warning naming the frame count so this is
    never a silent behavior.
    """
    from PIL import Image, ImageOps

    try:
        image = Image.open(path)
    except Exception as exc:  # Pillow raises many distinct decoder errors
        raise ImageToolError(f"{path} could not be opened as an image: {exc}") from exc

    frame_count = getattr(image, "n_frames", 1)
    if frame_count > 1:
        print(
            f"WARNING: {path} has {frame_count} frames (animated). This "
            "tool processes frame 0 only -- the rest of the animation is "
            "dropped from the output. See SKILL.md's animated-GIF note.",
            file=sys.stderr,
        )

    # ImageOps.exif_transpose always returns a NEW Image object (even when
    # no rotation is needed) and that new object's `.format` comes back
    # None -- Pillow does not carry it through. Preserve it explicitly so
    # `metrics` and `.save()`'s format-from-extension inference both still
    # see the source format, not a blank.
    original_format = image.format
    image = ImageOps.exif_transpose(image)
    image.format = original_format
    return image


def split_alpha(image):
    """Split an RGBA/LA image into an alpha-free image plus its alpha band
    (or (image, None) if there is no alpha). Filters in this script
    (sharpen, denoise) are applied to color data only and the alpha band is
    reattached unchanged afterward -- running an unsharp mask or median
    filter across the alpha band too would blur/ring transparency edges,
    which is rarely what "sharpen this screenshot" or "denoise this photo"
    means. See SKILL.md's "Format/edge-case handling" section.

    Palette ("P"), palette-with-alpha ("PA"), and 1-bit ("1") images are
    converted up front -- Pillow's ImageFilter kernels only operate on
    "L"/"RGB"/"CMYK"-class modes, so GIFs and indexed PNGs would otherwise
    raise ValueError inside .filter() the moment sharpen/denoise touch them.
    A palette image's own "transparency" info entry (rather than its mode
    alone) decides whether the converted image still carries alpha.
    """
    if image.mode == "P":
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
    elif image.mode == "PA":
        image = image.convert("RGBA")
    elif image.mode == "1":
        image = image.convert("L")
    if image.mode in ("RGBA", "LA"):
        alpha = image.getchannel("A")
        base_mode = "RGB" if image.mode == "RGBA" else "L"
        return image.convert(base_mode), alpha
    return image, None


def merge_alpha(image, alpha):
    if alpha is None:
        return image
    target_mode = "RGBA" if image.mode == "RGB" else "LA"
    image = image.convert(target_mode)
    image.putalpha(alpha)
    return image


# ---------------------------------------------------------------------------
# Objective quality metric: variance of the Laplacian
# ---------------------------------------------------------------------------


def laplacian_variance(image, long_edge_cap: int = 1600) -> float:
    """Compute the variance of the Laplacian of `image` -- the standard,
    well-known blur/sharpness metric (Pech-Pacheco et al., 2000): convolve
    a grayscale copy with the discrete Laplacian kernel

        0  1  0
        1 -4  1
        0  1  0

    (the sum of a pixel's four direct neighbors minus four times the pixel
    itself) and take the variance of the response. A sharp image has a lot
    of high-frequency edge content, so the Laplacian response varies
    widely (high variance); a blurry image's edges are smoothed out, so
    the response stays close to zero everywhere (low variance).

    This is a genuine per-pixel convolution done in plain Python floats
    (not Pillow's 8-bit `ImageFilter.Kernel`, which clips negative
    responses to 0 and would bias the variance) -- there is no numpy in
    this environment, so it is a nested loop, not a vectorized one. For
    speed on large inputs, images with a long edge above `long_edge_cap`
    are downsampled (Lanczos) before the convolution; this is a
    documented approximation for speed, not free -- it discards
    high-frequency detail above the cap's resolution, so absolute scores
    for a heavily-downsampled huge image are not comparable to one
    computed at full resolution. Comparing a before/after pair processed
    through the SAME cap (which every subcommand here does) is always
    valid regardless.

    Returns a non-negative float. There is no universal "good" threshold
    -- see SKILL.md's "Objective quality metric" section for how to read
    the number.
    """
    from PIL import Image

    gray = image.convert("L")
    width, height = gray.size

    if width < 3 or height < 3:
        raise ImageToolError(
            f"image is {width}x{height}, too small in one dimension to "
            "compute a Laplacian (needs at least 3x3)"
        )

    if max(width, height) > long_edge_cap:
        scale = long_edge_cap / max(width, height)
        new_size = (max(3, round(width * scale)), max(3, round(height * scale)))
        gray = gray.resize(new_size, Image.Resampling.LANCZOS)
        width, height = gray.size

    # get_flattened_data() replaces the deprecated getdata() in newer
    # Pillow; fall back for older installs that don't have it yet.
    if hasattr(gray, "get_flattened_data"):
        pixels = gray.get_flattened_data()
    else:  # pragma: no cover -- exercised only on Pillow < 12
        pixels = list(gray.getdata())
    responses = []
    for y in range(1, height - 1):
        row = y * width
        row_above = row - width
        row_below = row + width
        for x in range(1, width - 1):
            idx = row + x
            center = pixels[idx]
            response = (
                pixels[row_above + x]
                + pixels[row_below + x]
                + pixels[idx - 1]
                + pixels[idx + 1]
                - 4 * center
            )
            responses.append(response)

    n = len(responses)
    mean = sum(responses) / n
    return sum((r - mean) ** 2 for r in responses) / n


# ---------------------------------------------------------------------------
# Core operations (Image in, Image out) -- shared by single-file and batch
# ---------------------------------------------------------------------------


def op_upscale(image, scale: float, method: str, realesrgan_bin: str, realesrgan_model: str):
    """Return (new_image, method_actually_used)."""
    from PIL import Image

    if scale <= 1.0:
        raise ImageToolError(f"--scale must be > 1.0 (got {scale}); use `resize` to shrink")

    if method == "realesrgan":
        binary = shutil.which(realesrgan_bin) or (
            realesrgan_bin if Path(realesrgan_bin).is_file() else None
        )
        if binary is None:
            print(
                f"WARNING: --method realesrgan requested but '{realesrgan_bin}' "
                "was not found on PATH. Falling back to Lanczos. Install "
                "Real-ESRGAN-ncnn-vulkan (https://github.com/xinntao/"
                "Real-ESRGAN-ncnn-vulkan/releases) to get this method for real.",
                file=sys.stderr,
            )
        else:
            import tempfile

            with tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / "in.png"
                dst = Path(tmp) / "out.png"
                image.convert("RGB").save(src)
                # Real-ESRGAN-ncnn-vulkan's own scale factors are fixed
                # (2/3/4x depending on model); round the requested scale to
                # the nearest supported integer factor it understands.
                int_scale = max(2, min(4, round(scale)))
                try:
                    subprocess.run(
                        [
                            binary,
                            "-i",
                            str(src),
                            "-o",
                            str(dst),
                            "-n",
                            realesrgan_model,
                            "-s",
                            str(int_scale),
                        ],
                        check=True,
                        capture_output=True,
                        timeout=300,
                    )
                    return Image.open(dst).convert(image.mode if image.mode != "P" else "RGB"), "realesrgan"
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                    print(
                        f"WARNING: realesrgan invocation failed ({exc}); "
                        "falling back to Lanczos.",
                        file=sys.stderr,
                    )

    width, height = image.size
    new_size = (round(width * scale), round(height * scale))
    return image.resize(new_size, Image.Resampling.LANCZOS), "lanczos"


def op_resize(image, width: int | None, height: int | None, preset: str | None, keep_aspect: bool):
    from PIL import Image, ImageOps

    if preset:
        if preset not in RESIZE_PRESETS:
            known = ", ".join(sorted(RESIZE_PRESETS))
            raise ImageToolError(f"unknown --preset '{preset}'; known presets: {known}")
        width, height = RESIZE_PRESETS[preset]

    if not width or not height:
        raise ImageToolError("resize needs either --preset or both --width and --height")

    if keep_aspect:
        return ImageOps.contain(image, (width, height), method=Image.Resampling.LANCZOS)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def op_sharpen(image, radius: float, percent: int, threshold: int):
    from PIL import ImageFilter

    base, alpha = split_alpha(image)
    sharpened = base.filter(
        ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold)
    )
    return merge_alpha(sharpened, alpha)


def op_denoise(image, method: str, size: int):
    from PIL import ImageFilter

    if method == "median" and size % 2 == 0:
        raise ImageToolError(f"--size must be odd for median filter (got {size})")

    base, alpha = split_alpha(image)
    if method == "median":
        denoised = base.filter(ImageFilter.MedianFilter(size=size))
    elif method == "gaussian":
        # Honest framing: this is a plain Gaussian blur, not a
        # noise-aware bilateral filter. It reduces high-frequency noise
        # by averaging it away, but it also softens real edges -- unlike
        # median filtering, it does not preserve edges. Use `size` here
        # as the blur radius in pixels.
        denoised = base.filter(ImageFilter.GaussianBlur(radius=size))
    else:
        raise ImageToolError(f"unknown --method '{method}' (expected median or gaussian)")
    return merge_alpha(denoised, alpha)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def _report_sharpness_delta(before_image, after_image) -> None:
    before = laplacian_variance(before_image)
    after = laplacian_variance(after_image)
    print(
        f"sharpness (variance of Laplacian): {before:.1f} -> {after:.1f}",
        file=sys.stderr,
    )


def cmd_upscale(args: argparse.Namespace) -> None:
    input_path = _require_file(args.input)
    output_path = _require_new_output(args.output, input_path)

    image = open_image(input_path)
    before_size = image.size
    result, method_used = op_upscale(
        image, args.scale, args.method, args.realesrgan_bin, args.realesrgan_model
    )
    result.save(output_path)

    print(
        f"upscaled ({method_used}) {before_size[0]}x{before_size[1]} -> "
        f"{result.size[0]}x{result.size[1]} -> {output_path}",
        file=sys.stderr,
    )
    _report_sharpness_delta(image, result)


def cmd_resize(args: argparse.Namespace) -> None:
    input_path = _require_file(args.input)
    output_path = _require_new_output(args.output, input_path)

    image = open_image(input_path)
    before_size = image.size
    result = op_resize(image, args.width, args.height, args.preset, args.keep_aspect)
    result.save(output_path)

    print(
        f"resized {before_size[0]}x{before_size[1]} -> "
        f"{result.size[0]}x{result.size[1]} -> {output_path}",
        file=sys.stderr,
    )


def cmd_sharpen(args: argparse.Namespace) -> None:
    input_path = _require_file(args.input)
    output_path = _require_new_output(args.output, input_path)

    image = open_image(input_path)
    result = op_sharpen(image, args.radius, args.percent, args.threshold)
    result.save(output_path)

    print(f"sharpened -> {output_path}", file=sys.stderr)
    _report_sharpness_delta(image, result)


def cmd_denoise(args: argparse.Namespace) -> None:
    input_path = _require_file(args.input)
    output_path = _require_new_output(args.output, input_path)

    image = open_image(input_path)
    result = op_denoise(image, args.method, args.size)
    result.save(output_path)

    print(f"denoised ({args.method}) -> {output_path}", file=sys.stderr)
    _report_sharpness_delta(image, result)


def cmd_metrics(args: argparse.Namespace) -> None:
    input_path = _require_file(args.input)
    image = open_image(input_path)
    width, height = image.size
    variance = laplacian_variance(image)
    has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
    frame_count = getattr(image, "n_frames", 1)

    print(f"path: {input_path}")
    print(f"format: {image.format}")
    print(f"mode: {image.mode}")
    print(f"dimensions: {width}x{height}")
    print(f"file size: {input_path.stat().st_size} bytes")
    print(f"alpha channel: {has_alpha}")
    print(f"frame count: {frame_count}")
    print(f"sharpness (variance of Laplacian): {variance:.1f}")


def cmd_batch(args: argparse.Namespace) -> None:
    indir = Path(args.indir)
    if not indir.is_dir():
        raise ImageToolError(f"not a directory: {indir}")

    outdir = Path(args.outdir)
    if outdir.exists() and outdir.resolve() == indir.resolve():
        raise ImageToolError(
            "refusing to use the same directory for --outdir and the input "
            "directory -- batch never overwrites originals in place"
        )
    outdir.mkdir(parents=True, exist_ok=True)

    inputs = sorted(p for p in indir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)
    if not inputs:
        raise ImageToolError(f"no image files found in {indir}")

    processed = 0
    for input_path in inputs:
        image = open_image(input_path)
        if args.op == "upscale":
            # batch upscaling always uses Lanczos -- the realesrgan path
            # (with its own --method/--realesrgan-bin flags) is only
            # exposed on the single-file `upscale` subcommand, to avoid a
            # --method flag that would mean two different things
            # depending on --op.
            result, _ = op_upscale(image, args.scale, "lanczos", "", "")
        elif args.op == "resize":
            result = op_resize(image, args.width, args.height, args.preset, args.keep_aspect)
        elif args.op == "sharpen":
            result = op_sharpen(image, args.radius, args.percent, args.threshold)
        elif args.op == "denoise":
            result = op_denoise(image, args.method, args.size)
        else:  # pragma: no cover -- argparse `choices` already prevents this
            raise ImageToolError(f"unknown --op '{args.op}'")

        output_path = outdir / input_path.name
        result.save(output_path)
        processed += 1
        print(f"  {input_path.name} -> {output_path}", file=sys.stderr)

    print(f"batch {args.op}: processed {processed} file(s) -> {outdir}/", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def _add_sharpen_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--radius", type=float, default=2.0, help="UnsharpMask blur radius (default 2.0)")
    p.add_argument("--percent", type=int, default=150, help="UnsharpMask strength %% (default 150)")
    p.add_argument("--threshold", type=int, default=3, help="UnsharpMask threshold (default 3)")


def _add_denoise_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--method", choices=["median", "gaussian"], default="median")
    p.add_argument("--size", type=int, default=3, help="median kernel size (odd) or gaussian radius")


def _add_resize_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--preset", choices=sorted(RESIZE_PRESETS), help="named target size, see SKILL.md")
    p.add_argument(
        "--keep-aspect",
        action="store_true",
        help="fit within the target box instead of stretching to it exactly",
    )


def _add_upscale_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--scale", type=float, default=2.0, help="scale factor, must be > 1.0 (default 2.0)")
    p.add_argument("--method", choices=["lanczos", "realesrgan"], default="lanczos")
    p.add_argument(
        "--realesrgan-bin",
        default="realesrgan-ncnn-vulkan",
        help="binary name or path used when --method realesrgan",
    )
    p.add_argument("--realesrgan-model", default="realesrgan-x4plus")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="image_tool.py",
        description="Dispatcher for classical image enhancement operations. "
        "Run a subcommand with -h for its full option list.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("upscale", help="enlarge by a scale factor (Lanczos, or Real-ESRGAN if installed)")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    _add_upscale_args(p)
    p.set_defaults(func=cmd_upscale)

    p = sub.add_parser("resize", help="resize to explicit dimensions or a named preset")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    _add_resize_args(p)
    p.set_defaults(func=cmd_resize)

    p = sub.add_parser("sharpen", help="unsharp mask (edge/detail enhancement)")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    _add_sharpen_args(p)
    p.set_defaults(func=cmd_sharpen)

    p = sub.add_parser("denoise", help="median filter (default) or gaussian blur")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    _add_denoise_args(p)
    p.set_defaults(func=cmd_denoise)

    p = sub.add_parser("metrics", help="report dimensions, alpha, frames, and sharpness score")
    p.add_argument("input")
    p.set_defaults(func=cmd_metrics)

    p = sub.add_parser("batch", help="apply one operation across every image in a directory")
    p.add_argument("indir")
    p.add_argument("--outdir", required=True)
    p.add_argument("--op", choices=["upscale", "resize", "sharpen", "denoise"], required=True)
    p.add_argument(
        "--scale", type=float, default=2.0, help="upscale scale factor, used when --op upscale (default 2.0)"
    )
    _add_resize_args(p)
    _add_sharpen_args(p)
    _add_denoise_args(p)  # --method here means median/gaussian (denoise only)
    p.set_defaults(func=cmd_batch)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ImageToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
