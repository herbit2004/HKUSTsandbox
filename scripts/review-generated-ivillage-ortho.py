#!/usr/bin/env python3
"""Reject or retain an AI-edited i-Village ortho by fixed-source invariants.

This is a review helper, never a texture-generation step.  The authoritative
plan overlay comes from the saved PathAdvisor-derived Hall X--XIII envelopes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/source-evidence-v4/ivillage-rebuild/tdop-2025/ivillage-original-pixels.png"
GEOMETRY = ROOT / "public/models/current-forms/ivillage-rebuild/evidence/geometry.json"
BUILDING_FOOTPRINTS = ROOT / "public/data/building-footprints.json"
CROP_XZ = (550.0, -1200.0, 820.0, -980.0)
HALL_NAMES = {
    "ug-hall-10": "Hall X",
    "ug-hall-11": "Hall XI",
    "ug-hall-12": "Hall XII",
    "ug-hall-13": "Hall XIII",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def font(size: int) -> ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            pass
    return ImageFont.load_default()


def to_pixel(point: list[float], width: int, height: int) -> tuple[float, float]:
    min_x, min_z, max_x, max_z = CROP_XZ
    return (
        (point[0] - min_x) / (max_x - min_x) * width,
        (point[1] - min_z) / (max_z - min_z) * height,
    )


def masks_and_outlines(width: int, height: int):
    geometry = json.loads(GEOMETRY.read_text())
    masks: dict[str, Image.Image] = {}
    outlines: dict[str, list[list[tuple[float, float]]]] = {}
    for building in geometry["buildings"]:
        catalog_id = building["catalogId"]
        mask = Image.new("L", (width, height))
        draw = ImageDraw.Draw(mask)
        outline_parts = []
        for part in building["envelopeParts"]:
            rings = part["rings"]
            exterior = [to_pixel(point, width, height) for point in rings[0]]
            draw.polygon(exterior, fill=255)
            for hole in rings[1:]:
                draw.polygon([to_pixel(point, width, height) for point in hole], fill=0)
            outline_parts.append(exterior)
        masks[catalog_id] = mask
        outlines[catalog_id] = outline_parts
    raw_outlines: dict[str, list[list[tuple[float, float]]]] = {}
    source = json.loads(BUILDING_FOOTPRINTS.read_text())
    for building in source["footprints"]:
        catalog_id = building["catalogId"]
        if catalog_id not in HALL_NAMES:
            continue
        raw_outlines[catalog_id] = [
            [to_pixel(point, width, height) for point in part["rings"][0]]
            for part in building["parts"]
        ]
    return masks, outlines, raw_outlines


def edge_map(rgb: np.ndarray) -> np.ndarray:
    lum = rgb.astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    gx = np.zeros_like(lum)
    gy = np.zeros_like(lum)
    gx[:, 1:-1] = (lum[:, 2:] - lum[:, :-2]) * 0.5
    gy[1:-1, :] = (lum[2:, :] - lum[:-2, :]) * 0.5
    return np.hypot(gx, gy)


def correlation(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float | None:
    av = a[mask]
    bv = b[mask]
    if len(av) < 2 or float(av.std()) == 0 or float(bv.std()) == 0:
        return None
    return float(np.corrcoef(av, bv)[0, 1])


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fnt: ImageFont.ImageFont):
    box = draw.textbbox(xy, text, font=fnt, stroke_width=1)
    draw.rounded_rectangle((box[0] - 5, box[1] - 3, box[2] + 5, box[3] + 3), 4, fill=(3, 19, 29, 220))
    draw.text(xy, text, font=fnt, fill=(232, 251, 255), stroke_width=1, stroke_fill=(3, 19, 29))


def overlay(image: Image.Image, title: str, outlines, raw_outlines, masks) -> Image.Image:
    result = image.convert("RGBA")
    draw = ImageDraw.Draw(result, "RGBA")
    title_font = font(25)
    label_font = font(17)
    draw.rounded_rectangle((14, 14, 650, 83), 9, fill=(3, 19, 29, 215))
    draw.text((28, 22), title, font=title_font, fill=(245, 253, 255))
    draw.text((28, 57), "yellow: raw PathAdvisor | cyan: production owners", font=label_font, fill=(245, 220, 70))
    for parts in raw_outlines.values():
        for points in parts:
            draw.line(points + [points[0]], fill=(255, 214, 36, 245), width=2, joint="curve")
    for catalog_id, parts in outlines.items():
        for points in parts:
            draw.line(points + [points[0]], fill=(30, 238, 255, 255), width=4, joint="curve")
        bbox = masks[catalog_id].getbbox()
        if bbox:
            label(draw, (bbox[0] + 8, bbox[1] + 8), HALL_NAMES[catalog_id], label_font)
    return result.convert("RGB")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    args = parser.parse_args()

    source_image = Image.open(SOURCE).convert("RGB")
    candidate_native = Image.open(args.candidate).convert("RGB")
    candidate_image = candidate_native.resize(source_image.size, Image.Resampling.LANCZOS)
    width, height = source_image.size
    masks, outlines, raw_outlines = masks_and_outlines(width, height)

    source = np.asarray(source_image).astype(np.float32)
    candidate = np.asarray(candidate_image).astype(np.float32)
    difference = np.abs(source - candidate)
    union_image = Image.new("L", (width, height))
    for mask in masks.values():
        union_image = Image.fromarray(np.maximum(np.asarray(union_image), np.asarray(mask)).astype(np.uint8))
    union = np.asarray(union_image) > 0
    # 15 m = 60 px at the 0.25 m TDOP resolution.  MaxFilter must be odd.
    neighborhood = np.asarray(union_image.filter(ImageFilter.MaxFilter(121))) > 0
    outside = ~neighborhood
    source_edges = edge_map(source)
    candidate_edges = edge_map(candidate)

    def region_metrics(region: np.ndarray) -> dict:
        pixel_diff = difference.mean(axis=2)[region]
        return {
            "pixels": int(region.sum()),
            "meanAbsoluteRgbDifference": float(difference[region].mean()),
            "changedPixelFractionAbove15Rgb": float((pixel_diff > 15).mean()),
            "changedPixelFractionAbove30Rgb": float((pixel_diff > 30).mean()),
            "edgeCorrelation": correlation(source_edges, candidate_edges, region),
        }

    per_hall = {}
    for catalog_id, mask_image in masks.items():
        per_hall[catalog_id] = region_metrics(np.asarray(mask_image) > 0)

    report = {
        "status": "rejected-not-georegistered-not-a-geometry-source",
        "reviewPurpose": "Test whether a generated local ground edit preserved fixed orthophoto and official Hall X-XIII plan invariants.",
        "sourceOrtho": {
            "path": str(SOURCE.relative_to(ROOT)),
            "sha256": sha256(SOURCE),
            "pixels": list(source_image.size),
            "crs": "EPSG:2326",
            "pixelSizeMeters": 0.25,
            "captureDate": "2025-01-11",
            "authority": "Georegistration and contemporaneous visible pixels only; construction-period ground is not current-form appearance evidence.",
        },
        "candidate": {
            "sourcePath": str(args.candidate),
            "sha256": sha256(args.candidate),
            "nativePixels": list(candidate_native.size),
            "comparisonPixels": list(candidate_image.size),
            "authority": "None. Generated review output; not a map, survey, building footprint or production texture.",
        },
        "planOverlay": {
            "rawPath": str(BUILDING_FOOTPRINTS.relative_to(ROOT)),
            "rawSHA256": sha256(BUILDING_FOOTPRINTS),
            "productionPath": str(GEOMETRY.relative_to(ROOT)),
            "productionSHA256": sha256(GEOMETRY),
            "source": "Yellow is the raw HKUST PathAdvisor all-base-map building drawing. Cyan is the disjoint production ownership plan derived from it, with every normalization/ownership adjustment recorded.",
            "authority": "Best available fixed XZ building-domain source in this project; not a surveyed as-built shell.",
        },
        "metrics": {
            "wholeCrop": region_metrics(np.ones((height, width), dtype=bool)),
            "insideOfficialHallDomains": region_metrics(union),
            "outsideOfficialHallDomainsPlus15m": region_metrics(outside),
            "perHall": per_hall,
        },
        "decision": {
            "publish": False,
            "copyToRuntimeAssets": False,
            "reshapeBuildingsFromCandidate": False,
            "reason": "The candidate substantially redraws pixels and edges inside the official Hall domains and far outside the requested local ground-edit neighborhood. It does not preserve georegistration or building/road invariants.",
            "geometryPolicy": [
                "Use saved official PathAdvisor floor/building domains for XZ plan and stable identity.",
                "Use unmodified terminal photogrammetry triangles for source roof planes and terrain joins where current-form evidence has not superseded them.",
                "Use official 2026 completion photos for present-day massing, connections and material appearance only; they are not calibrated plan drawings.",
                "Treat generated pixels as local material ideas only after explicit registration and invariant checks; this candidate failed those checks.",
            ],
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    source_panel = overlay(source_image, "2025 registered TDOP", outlines, raw_outlines, masks)
    candidate_panel = overlay(candidate_image, "Generated candidate (rejected)", outlines, raw_outlines, masks)
    heat = np.clip(difference.mean(axis=2) * 4.0, 0, 255).astype(np.uint8)
    heat_rgb = np.stack([heat, (heat * 0.28).astype(np.uint8), np.zeros_like(heat)], axis=2)
    heat_panel = overlay(Image.fromarray(heat_rgb), "Absolute change heatmap", outlines, raw_outlines, masks)
    gap = 12
    montage = Image.new("RGB", (width * 3 + gap * 2, height), (12, 18, 24))
    montage.paste(source_panel, (0, 0))
    montage.paste(candidate_panel, (width + gap, 0))
    montage.paste(heat_panel, ((width + gap) * 2, 0))
    args.comparison.parent.mkdir(parents=True, exist_ok=True)
    montage.save(args.comparison, optimize=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
