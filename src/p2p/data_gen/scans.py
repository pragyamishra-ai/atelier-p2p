"""Scan degradation: turn a share of the clean PDFs into messy, image-only scans.

The clean PDFs (with a text layer) are rasterized, degraded, and written back as one JPEG per
page, so there is no text layer left. A share of invoices stays untouched as a text-PDF baseline.
The ground-truth CSVs do not change: they describe what the invoice says, not how it was scanned.
"""

import io
import random
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pymupdf
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

CLEAN_SHARE = 0.40  # stay as text PDFs
MILD_SHARE = 0.35  # the rest (25%) is "bad"

# (low, high) ranges, drawn per invoice.
PROFILES = {
    "mild": {
        "dpi": (150, 200),
        "rotation": (0.2, 1.0),
        "blur": (0.3, 0.5),
        "noise": (4, 8),
        "jpeg": (70, 85),
        "contrast": (0.90, 1.0),
        "specks": (0, 5),
        "stamp": 0.0,
    },
    "bad": {
        "dpi": (120, 140),
        "rotation": (1.5, 3.5),
        "blur": (0.5, 0.9),
        "noise": (10, 18),
        "jpeg": (40, 55),
        "contrast": (0.78, 0.90),
        "specks": (20, 50),
        "stamp": 0.5,
    },
}

SPECK_CLEARANCE = 12  # points of blank paper required around a speck
STAMP_TEXTS = ["RECEIVED", "REGISTERED", "ENTERED"]
PARAM_COLUMNS = [
    "dpi",
    "rotation_deg",
    "blur_radius",
    "noise_sigma",
    "jpeg_quality",
    "contrast",
    "specks",
    "stamp",
]
META_COLUMNS = ["invoice_id", "pdf_file", "scan_quality", *PARAM_COLUMNS]


def assign_scan_quality(invoice_ids: list[str], rng: random.Random) -> dict[str, str]:
    """Shuffle once, then hand out slices: clean, mild, and the rest bad."""
    order = sorted(invoice_ids)
    rng.shuffle(order)
    n = len(order)
    n_clean = round(CLEAN_SHARE * n)
    n_mild = round(MILD_SHARE * n)
    labels = ["clean"] * n_clean + ["mild"] * n_mild + ["bad"] * (n - n_clean - n_mild)
    return dict(zip(order, labels, strict=True))


def draw_params(rng: random.Random, quality: str) -> dict:
    p = PROFILES[quality]
    return {
        "dpi": rng.randint(*p["dpi"]),
        "rotation_deg": round(rng.choice([-1, 1]) * rng.uniform(*p["rotation"]), 2),
        "blur_radius": round(rng.uniform(*p["blur"]), 2),
        "noise_sigma": round(rng.uniform(*p["noise"]), 1),
        "jpeg_quality": rng.randint(*p["jpeg"]),
        "contrast": round(rng.uniform(*p["contrast"]), 2),
        "specks": rng.randint(*p["specks"]),
        "stamp": rng.random() < p["stamp"],
    }


def _add_stamp(img: Image.Image, rng: random.Random, scale: float) -> Image.Image:
    """A faint, rotated 'received' stamp, placed where the page has no ink underneath."""
    size = int(14 * scale)
    font = ImageFont.load_default(size=size)
    text = rng.choice(STAMP_TEXTS)
    left, top, right, bottom = font.getbbox(text)
    pad = size // 3
    tile = Image.new("RGBA", (right - left + 2 * pad, bottom - top + 2 * pad), (0, 0, 0, 0))
    colour = rng.choice([(180, 30, 30, 110), (30, 50, 160, 110)])
    draw = ImageDraw.Draw(tile)
    draw.rectangle(
        (0, 0, tile.width - 1, tile.height - 1), outline=colour, width=max(2, size // 10)
    )
    draw.text((pad - left, pad - top), text, font=font, fill=colour)
    tile = tile.rotate(rng.uniform(-15, 15), expand=True, resample=Image.Resampling.BICUBIC)
    dark = np.asarray(img.convert("L")) < 215
    best, best_ink = (0, 0), None
    for _ in range(40):
        x = min(int(img.width * rng.uniform(0.05, 0.75)), img.width - tile.width)
        y = min(int(img.height * rng.uniform(0.04, 0.85)), img.height - tile.height)
        ink = int(dark[y : y + tile.height, x : x + tile.width].sum())
        if best_ink is None or ink < best_ink:
            best, best_ink = (x, y), ink
        if ink == 0:
            break
    base = img.convert("RGBA")
    base.alpha_composite(tile, best)
    return base.convert("RGB")


def _degrade_image(
    img: Image.Image, params: dict, rng: random.Random, np_rng: np.random.Generator
) -> Image.Image:
    img = ImageEnhance.Contrast(img).enhance(params["contrast"])
    img = img.rotate(
        params["rotation_deg"], resample=Image.Resampling.BICUBIC, fillcolor=(255, 255, 255)
    )
    scale = params["dpi"] / 72
    draw = ImageDraw.Draw(img)
    gray = np.asarray(img.convert("L"))
    for _ in range(params["specks"]):
        x, y = rng.uniform(0, img.width), rng.uniform(0, img.height)
        r = rng.uniform(0.4, 1.2) * scale
        grey = rng.randint(60, 140)
        pad = max(int(r * 4) + 2, int(SPECK_CLEARANCE * scale))
        patch = gray[max(0, int(y) - pad) : int(y) + pad, max(0, int(x) - pad) : int(x) + pad]
        if patch.size and int(patch.max()) - int(patch.min()) > 25:
            continue  # would touch ink or a table line, so no digit can be misread
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(grey, grey, grey))
    if params["stamp"]:
        img = _add_stamp(img, rng, scale)
    img = img.filter(ImageFilter.GaussianBlur(params["blur_radius"]))
    pixels = np.asarray(img, dtype=np.float32)
    noise = np_rng.normal(0, params["noise_sigma"], pixels.shape[:2])[..., None]
    return Image.fromarray(np.clip(pixels + noise, 0, 255).astype(np.uint8))


def degrade_pdf(src: Path, dst: Path, params: dict, seed: int) -> None:
    """Rasterize every page, degrade it, and write an image-only PDF of the same page size."""
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    with pymupdf.open(str(src)) as source, pymupdf.open() as out:
        for page in source:
            pix = page.get_pixmap(dpi=params["dpi"])
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img = _degrade_image(img, params, rng, np_rng)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=params["jpeg_quality"])
            new_page = out.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, stream=buf.getvalue())
        out.save(str(dst), garbage=3, deflate=True)


def make_scans(invoices: pd.DataFrame, clean_dir: Path, out_dir: Path, seed: int) -> pd.DataFrame:
    """Fill out_dir with clean copies or degraded scans. Return the per-invoice metadata."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed + 6)
    files = invoices.set_index("invoice_id")["pdf_file"].to_dict()
    quality = assign_scan_quality(list(files), rng)

    rows = []
    for invoice_id in sorted(files):
        kind = quality[invoice_id]
        src, dst = clean_dir / files[invoice_id], out_dir / files[invoice_id]
        row = {"invoice_id": invoice_id, "pdf_file": files[invoice_id], "scan_quality": kind}
        if kind == "clean":
            shutil.copyfile(src, dst)
        else:
            params = draw_params(rng, kind)
            degrade_pdf(src, dst, params, rng.getrandbits(32))
            row.update({k: params[k] for k in PARAM_COLUMNS})
        rows.append(row)
    meta = pd.DataFrame(rows, columns=META_COLUMNS)
    for col in ("dpi", "jpeg_quality", "specks"):
        meta[col] = meta[col].astype("Int64")
    return meta
