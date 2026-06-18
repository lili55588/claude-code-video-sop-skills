#!/usr/bin/env python3
"""Part A evidence collector for VVK image/keyframe audits.

This tool collects deterministic image facts, optional grid panel boxes, and
soft-signal evidence. It does not decide whether an image visually passes.

Soft-signal boundaries:
- Hash evidence is region/panel scoped and can compare against reference images.
- OCR and watermark hints use optional OCR engines when present.
- Face detection is intentionally not wired yet.
- Soft signals never change part_a_status; Part B visual review is required.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

try:  # Optional dependency. The tool must still run without it.
    import pytesseract
except Exception:  # pragma: no cover - depends on host environment
    pytesseract = None  # type: ignore[assignment]


RESAMPLE_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
DEFAULT_WATERMARK_KEYWORDS = [
    "watermark",
    "sample",
    "preview",
    "stock",
    "shutterstock",
    "getty",
    "alamy",
    "dreamina",
    "jimeng",
    "seedance",
    "pippit",
    "capcut",
    "tiktok",
    "douyin",
]
OCR_CRITICALITIES = {"must-match", "incidental"}
SOFT_SIGNAL_ONLY = "SOFT_SIGNAL_ONLY"
NOT_AVAILABLE = "NOT_AVAILABLE"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    issue_class: str | None = None


def parse_ratio(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip()
    if ":" in text:
        left, right = text.split(":", 1)
        return float(left) / float(right)
    return float(text)


def parse_grid(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    normalized = value.lower().replace("*", "x").replace(",", "x")
    parts = normalized.split("x")
    if len(parts) != 2:
        raise ValueError("--grid must use ROWSxCOLS, for example 2x3")
    rows, cols = int(parts[0]), int(parts[1])
    if rows <= 0 or cols <= 0:
        raise ValueError("--grid rows and cols must be positive")
    return rows, cols


def parse_expected_text_items(values: list[str] | None) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for value in values or []:
        text = value.strip()
        if not text:
            continue
        criticality = "must-match"
        if ":" in text:
            prefix, remainder = text.split(":", 1)
            if prefix in OCR_CRITICALITIES:
                criticality = prefix
                text = remainder.strip()
        if text:
            items.append({"text": text, "criticality": criticality})
    return items


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def unavailable_soft_signal(note: str) -> dict[str, Any]:
    return {"status": NOT_AVAILABLE, "note": f"soft signal only; {note}"}


def default_soft_signals() -> dict[str, Any]:
    return {
        "ocr": unavailable_soft_signal("OCR not requested or no OCR engine wired"),
        "face_count": unavailable_soft_signal("face detector intentionally deferred"),
        "watermark_or_text_overlay": unavailable_soft_signal("no OCR-derived detector wired"),
        "perceptual_hash_or_embedding": unavailable_soft_signal("hash evidence not collected"),
    }


def panel_boxes(width: int, height: int, rows: int, cols: int) -> list[dict[str, int]]:
    boxes: list[dict[str, int]] = []
    for row in range(rows):
        for col in range(cols):
            x0 = round(col * width / cols)
            x1 = round((col + 1) * width / cols)
            y0 = round(row * height / rows)
            y1 = round((row + 1) * height / rows)
            boxes.append(
                {
                    "panel": row * cols + col + 1,
                    "row": row + 1,
                    "col": col + 1,
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "width": x1 - x0,
                    "height": y1 - y0,
                }
            )
    return boxes


def hash_regions(width: int, height: int, grid: tuple[int, int] | None) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = [
        {"name": "full", "bbox": {"x0": 0, "y0": 0, "x1": width, "y1": height}},
    ]
    if width > 4 and height > 4:
        x_margin = round(width * 0.1)
        y_margin = round(height * 0.1)
        regions.append(
            {
                "name": "center_80",
                "bbox": {
                    "x0": x_margin,
                    "y0": y_margin,
                    "x1": width - x_margin,
                    "y1": height - y_margin,
                },
            }
        )
    if grid is not None:
        rows, cols = grid
        for panel in panel_boxes(width, height, rows, cols):
            regions.append(
                {
                    "name": f"panel_{panel['panel']}",
                    "bbox": {
                        "x0": panel["x0"],
                        "y0": panel["y0"],
                        "x1": panel["x1"],
                        "y1": panel["y1"],
                    },
                }
            )
    return regions


def crop_by_bbox(image: Image.Image, bbox: dict[str, int]) -> Image.Image:
    width, height = image.size
    x0 = max(0, min(width, int(bbox["x0"])))
    y0 = max(0, min(height, int(bbox["y0"])))
    x1 = max(x0 + 1, min(width, int(bbox["x1"])))
    y1 = max(y0 + 1, min(height, int(bbox["y1"])))
    return image.crop((x0, y0, x1, y1))


def dhash_hex(image: Image.Image, hash_size: int) -> tuple[str, int]:
    gray = image.convert("L").resize((hash_size + 1, hash_size), RESAMPLE_LANCZOS)
    pixels = list(gray.getdata())
    value = 0
    bit_count = hash_size * hash_size
    for row in range(hash_size):
        row_start = row * (hash_size + 1)
        for col in range(hash_size):
            left = pixels[row_start + col]
            right = pixels[row_start + col + 1]
            value = (value << 1) | int(left > right)
    return f"{value:0{bit_count // 4}x}", bit_count


def hamming_distance(left_hex: str, right_hex: str) -> int:
    return (int(left_hex, 16) ^ int(right_hex, 16)).bit_count()


def image_hashes(
    image: Image.Image,
    image_path: Path,
    grid: tuple[int, int] | None,
    hash_size: int,
) -> list[dict[str, Any]]:
    width, height = image.size
    records: list[dict[str, Any]] = []
    for region in hash_regions(width, height, grid):
        cropped = crop_by_bbox(image, region["bbox"])
        digest, bit_count = dhash_hex(cropped, hash_size)
        records.append(
            {
                "source_path": str(image_path),
                "region": region["name"],
                "bbox": region["bbox"],
                "method": "dhash",
                "hash": digest,
                "bit_count": bit_count,
            }
        )
    return records


def load_reference_image(ref_path: Path) -> tuple[Image.Image | None, str | None]:
    try:
        with Image.open(ref_path) as ref:
            ref.load()
            return ref.convert("RGB"), None
    except (UnidentifiedImageError, OSError) as exc:
        return None, str(exc)


def collect_hash_signal(
    image: Image.Image,
    image_path: Path,
    ref_paths: list[Path],
    grid: tuple[int, int] | None,
    hash_size: int,
    review_threshold: int,
) -> dict[str, Any]:
    hashes = image_hashes(image, image_path, grid, hash_size)
    comparisons: list[dict[str, Any]] = []
    unavailable_refs: list[dict[str, str]] = []

    current_by_region = {item["region"]: item for item in hashes}
    for ref_path in ref_paths:
        ref_image, error = load_reference_image(ref_path)
        if ref_image is None:
            unavailable_refs.append({"source_path": str(ref_path), "error": error or "cannot open reference image"})
            continue
        ref_hashes = image_hashes(ref_image, ref_path, grid, hash_size)
        for ref_hash in ref_hashes:
            current_hash = current_by_region.get(ref_hash["region"])
            if current_hash is None:
                continue
            distance = hamming_distance(current_hash["hash"], ref_hash["hash"])
            bit_count = current_hash["bit_count"]
            comparisons.append(
                {
                    "compared_to": str(ref_path),
                    "region": ref_hash["region"],
                    "current_hash": current_hash["hash"],
                    "reference_hash": ref_hash["hash"],
                    "distance": distance,
                    "normalized_distance": round(distance / bit_count, 6),
                    "review_hint": "REVIEW_DIFFERENCE" if distance > review_threshold else "NEAR_MATCH_SIGNAL",
                    "status": SOFT_SIGNAL_ONLY,
                }
            )

    signal = {
        "status": SOFT_SIGNAL_ONLY,
        "note": (
            "soft signal only; region/panel dhash evidence supports duplicate, drift, "
            "or wrong-export review but cannot hard-fail without visual confirmation"
        ),
        "method": "dhash",
        "scope": "full_center_and_grid_panel_regions",
        "angle_awareness": "limited region-aware hash; no face/body embedding wired",
        "hash_size": hash_size,
        "review_threshold": review_threshold,
        "hashes": hashes,
        "comparisons": comparisons,
    }
    if unavailable_refs:
        signal["unavailable_references"] = unavailable_refs
    if not ref_paths:
        signal["review_note"] = "No --ref-image provided; hashes are recorded for future or external comparison only."
    return signal


def ocr_tokens_from_image(image: Image.Image, max_items: int) -> tuple[list[dict[str, Any]] | None, str | None]:
    if pytesseract is None:
        return None, "pytesseract is not installed"
    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)  # type: ignore[union-attr]
    except Exception as exc:  # pragma: no cover - depends on host OCR binary
        return None, str(exc)

    tokens: list[dict[str, Any]] = []
    count = len(data.get("text", []))
    for index in range(count):
        text = str(data["text"][index]).strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1.0
        token = {
            "text": text,
            "confidence": confidence,
            "bbox": {
                "x0": int(data["left"][index]),
                "y0": int(data["top"][index]),
                "x1": int(data["left"][index]) + int(data["width"][index]),
                "y1": int(data["top"][index]) + int(data["height"][index]),
            },
        }
        tokens.append(token)
        if len(tokens) >= max_items:
            break
    return tokens, None


def collect_ocr_signal(
    image: Image.Image,
    expected_texts: list[dict[str, str]],
    max_items: int,
) -> dict[str, Any]:
    tokens, error = ocr_tokens_from_image(image, max_items)
    if tokens is None:
        return unavailable_soft_signal(f"OCR engine unavailable: {error}")

    detected_text = " ".join(token["text"] for token in tokens)
    normalized_detected = normalize_text(detected_text)
    expected_results: list[dict[str, Any]] = []
    for item in expected_texts:
        expected = item["text"]
        criticality = item["criticality"]
        match = normalize_text(expected) in normalized_detected
        expected_results.append(
            {
                "expected_text": expected,
                "criticality": criticality,
                "matches_expected": match,
                "status": SOFT_SIGNAL_ONLY,
                "review_hint": (
                    "MUST_MATCH_OCR_MISMATCH_REQUIRES_VISUAL_CONFIRMATION"
                    if criticality == "must-match" and not match
                    else "OCR_EVIDENCE_ONLY"
                ),
            }
        )

    return {
        "status": SOFT_SIGNAL_ONLY,
        "note": (
            "soft signal only; OCR text and bbox evidence support the VVK two-key rule "
            "but cannot hard-fail without visual confirmation"
        ),
        "engine": "pytesseract",
        "detected_text": detected_text,
        "tokens": tokens,
        "expected_text": expected_results,
    }


def bbox_touches_corner(bbox: dict[str, int], width: int, height: int, margin_ratio: float = 0.22) -> bool:
    x_center = (bbox["x0"] + bbox["x1"]) / 2
    y_center = (bbox["y0"] + bbox["y1"]) / 2
    x_margin = width * margin_ratio
    y_margin = height * margin_ratio
    near_left = x_center <= x_margin
    near_right = x_center >= width - x_margin
    near_top = y_center <= y_margin
    near_bottom = y_center >= height - y_margin
    return (near_left or near_right) and (near_top or near_bottom)


def derive_watermark_signal(
    image: Image.Image,
    ocr_signal: dict[str, Any],
    watermark_keywords: list[str],
) -> dict[str, Any]:
    if ocr_signal.get("status") != SOFT_SIGNAL_ONLY:
        return unavailable_soft_signal("watermark keyword scan needs OCR tokens")

    width, height = image.size
    keywords = [normalize_text(keyword) for keyword in watermark_keywords if keyword.strip()]
    detections: list[dict[str, Any]] = []
    for token in ocr_signal.get("tokens", []):
        normalized = normalize_text(token.get("text", ""))
        keyword_hits = [keyword for keyword in keywords if keyword and keyword in normalized]
        corner_hit = bbox_touches_corner(token["bbox"], width, height)
        if keyword_hits or corner_hit:
            detections.append(
                {
                    "text": token.get("text", ""),
                    "confidence": token.get("confidence"),
                    "bbox": token.get("bbox"),
                    "corner_region": corner_hit,
                    "keyword_hits": keyword_hits,
                    "status": SOFT_SIGNAL_ONLY,
                }
            )

    return {
        "status": SOFT_SIGNAL_ONLY,
        "note": (
            "soft signal only; OCR-derived corner/keyword hints may indicate watermark "
            "or incidental text overlay and require visual confirmation"
        ),
        "method": "ocr_corner_keyword_scan",
        "keywords": watermark_keywords,
        "detections": detections,
    }


def audit_image(
    image_path: Path,
    expected_ratio: float | None,
    ratio_tolerance: float,
    expected_width: int | None,
    expected_height: int | None,
    grid: tuple[int, int] | None,
    ref_paths: list[Path],
    hash_size: int,
    hash_review_threshold: int,
    enable_ocr: bool,
    expected_texts: list[dict[str, str]],
    watermark_keywords: list[str],
    ocr_max_items: int,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source_path": str(image_path),
        "exists": image_path.exists(),
        "readable": False,
        "checks": [],
        "soft_signals": default_soft_signals(),
        "vvk_issue_classes": [],
        "part_a_status": "AUDIT_READY",
        "visual_verdict": "REQUIRES_VISUAL_REVIEW",
    }

    checks: list[CheckResult] = []

    if not image_path.exists():
        checks.append(
            CheckResult(
                "file_exists",
                "AUDIT_INCOMPLETE",
                "file does not exist",
                "EVIDENCE_GAP",
            )
        )
        record["part_a_status"] = "AUDIT_INCOMPLETE"
        record["vvk_issue_classes"].append("EVIDENCE_GAP")
        record["checks"] = [asdict(item) for item in checks]
        return record

    try:
        with Image.open(image_path) as img:
            img.load()
            width, height = img.size
            image_format = img.format
            mode = img.mode
            image = img.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        checks.append(
            CheckResult(
                "file_readable",
                "AUDIT_INCOMPLETE",
                f"cannot open image: {exc}",
                "EVIDENCE_GAP",
            )
        )
        record["part_a_status"] = "AUDIT_INCOMPLETE"
        record["vvk_issue_classes"].append("EVIDENCE_GAP")
        record["checks"] = [asdict(item) for item in checks]
        return record

    record.update(
        {
            "readable": True,
            "width": width,
            "height": height,
            "format": image_format,
            "mode": mode,
            "aspect_ratio": width / height if height else None,
        }
    )
    checks.append(CheckResult("file_readable", "PASS", "image opens successfully"))

    if expected_width is not None:
        status = "PASS" if width == expected_width else "TECH_SPEC_BLOCKED"
        issue = None if status == "PASS" else "TECH_SPEC_BLOCKED"
        checks.append(CheckResult("expected_width", status, f"actual={width}, expected={expected_width}", issue))
    if expected_height is not None:
        status = "PASS" if height == expected_height else "TECH_SPEC_BLOCKED"
        issue = None if status == "PASS" else "TECH_SPEC_BLOCKED"
        checks.append(CheckResult("expected_height", status, f"actual={height}, expected={expected_height}", issue))

    if expected_ratio is not None:
        actual = width / height
        delta = abs(actual - expected_ratio)
        status = "PASS" if delta <= ratio_tolerance else "TECH_SPEC_BLOCKED"
        issue = None if status == "PASS" else "TECH_SPEC_BLOCKED"
        checks.append(
            CheckResult(
                "expected_ratio",
                status,
                f"actual={actual:.6f}, expected={expected_ratio:.6f}, delta={delta:.6f}, tolerance={ratio_tolerance}",
                issue,
            )
        )

    if grid is not None:
        rows, cols = grid
        boxes = panel_boxes(width, height, rows, cols)
        record["grid"] = {"rows": rows, "cols": cols, "panel_count": rows * cols, "boxes": boxes}
        checks.append(CheckResult("grid_panel_boxes", "PASS", f"computed {rows * cols} panel boxes"))

    record["soft_signals"]["perceptual_hash_or_embedding"] = collect_hash_signal(
        image=image,
        image_path=image_path,
        ref_paths=ref_paths,
        grid=grid,
        hash_size=hash_size,
        review_threshold=hash_review_threshold,
    )

    should_run_ocr = enable_ocr or bool(expected_texts) or bool(watermark_keywords)
    if should_run_ocr:
        ocr_signal = collect_ocr_signal(image, expected_texts, ocr_max_items)
        record["soft_signals"]["ocr"] = ocr_signal
        record["soft_signals"]["watermark_or_text_overlay"] = derive_watermark_signal(
            image,
            ocr_signal,
            watermark_keywords or DEFAULT_WATERMARK_KEYWORDS,
        )

    issue_classes = sorted({item.issue_class for item in checks if item.issue_class})
    if "EVIDENCE_GAP" in issue_classes:
        record["part_a_status"] = "AUDIT_INCOMPLETE"
    elif "TECH_SPEC_BLOCKED" in issue_classes:
        record["part_a_status"] = "TECH_SPEC_REVIEW"
    else:
        record["part_a_status"] = "AUDIT_READY"
    record["vvk_issue_classes"] = issue_classes
    record["checks"] = [asdict(item) for item in checks]
    return record


def md_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_soft_signal_markdown(item: dict[str, Any], lines: list[str]) -> None:
    signals = item.get("soft_signals", {})
    lines.extend(["", "#### Soft Signals", ""])
    lines.extend(["| Signal | Status | Detail |", "|---|---|---|"])
    for name, signal in signals.items():
        detail = signal.get("note") or signal.get("method") or ""
        lines.append(f"| {name} | {signal.get('status')} | {md_escape(detail)} |")

    hash_signal = signals.get("perceptual_hash_or_embedding", {})
    comparisons = hash_signal.get("comparisons") or []
    if comparisons:
        lines.extend(["", "Hash comparison evidence:", "", "| Compared To | Region | Distance | Hint |", "|---|---:|---:|---|"])
        for comparison in comparisons:
            lines.append(
                "| "
                f"{md_escape(Path(comparison['compared_to']).name)} | "
                f"{md_escape(comparison['region'])} | "
                f"{comparison['distance']} | "
                f"{md_escape(comparison['review_hint'])} |"
            )

    ocr_signal = signals.get("ocr", {})
    expected_items = ocr_signal.get("expected_text") or []
    if expected_items:
        lines.extend(["", "OCR expected-text evidence:", "", "| Expected Text | Criticality | Match | Hint |", "|---|---|---|---|"])
        for expected in expected_items:
            lines.append(
                "| "
                f"{md_escape(expected['expected_text'])} | "
                f"{md_escape(expected['criticality'])} | "
                f"{expected['matches_expected']} | "
                f"{md_escape(expected['review_hint'])} |"
            )

    watermark_signal = signals.get("watermark_or_text_overlay", {})
    detections = watermark_signal.get("detections") or []
    if detections:
        lines.extend(["", "Watermark/text-overlay hints:", "", "| Text | BBox | Corner | Keywords |", "|---|---|---|---|"])
        for detection in detections:
            lines.append(
                "| "
                f"{md_escape(detection.get('text', ''))} | "
                f"{md_escape(detection.get('bbox', ''))} | "
                f"{detection.get('corner_region')} | "
                f"{md_escape(', '.join(detection.get('keyword_hits') or []))} |"
            )


def write_markdown(manifest: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Image Asset Audit Evidence",
        "",
        f"- Created: {manifest['created_at']}",
        f"- Profile: {manifest['profile']}",
        f"- Overall Part A status: `{manifest['overall_part_a_status']}`",
        "",
        "Part A evidence does not decide visual PASS/FAIL. Use VVK Part B/C for visual judgment.",
        "Soft signals are evidence only and never change `part_a_status`.",
        "",
        "## Images",
        "",
    ]
    for item in manifest["images"]:
        lines.extend(
            [
                f"### {Path(item['source_path']).name}",
                "",
                f"- Path: `{item['source_path']}`",
                f"- Part A status: `{item['part_a_status']}`",
                f"- Visual verdict: `{item['visual_verdict']}`",
            ]
        )
        if item.get("readable"):
            lines.extend(
                [
                    f"- Size: {item['width']}x{item['height']}",
                    f"- Aspect ratio: {item['aspect_ratio']:.6f}",
                    f"- Format/mode: {item.get('format')}/{item.get('mode')}",
                ]
            )
        if item.get("grid"):
            grid = item["grid"]
            lines.append(f"- Grid: {grid['rows']}x{grid['cols']} ({grid['panel_count']} panels)")
        lines.extend(["", "| Check | Status | Detail | Issue Class |", "|---|---|---|---|"])
        for check in item["checks"]:
            lines.append(
                f"| {check['name']} | {check['status']} | {md_escape(check['detail'])} | "
                f"{check.get('issue_class') or ''} |"
            )
        write_soft_signal_markdown(item, lines)
        lines.append("")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect VVK Part A evidence for images/keyframes/grids.")
    parser.add_argument("--image", action="append", required=True, help="Image path. Repeat for multiple images.")
    parser.add_argument("--out-dir", required=True, help="Directory for manifest and markdown evidence.")
    parser.add_argument("--profile", choices=["phase7", "phase8.5", "direct-image"], default="phase7")
    parser.add_argument("--expected-ratio", help="Expected ratio such as 16:9 or 1.777777")
    parser.add_argument("--ratio-tolerance", type=float, default=0.01)
    parser.add_argument("--expected-width", type=int)
    parser.add_argument("--expected-height", type=int)
    parser.add_argument("--grid", help="Optional ROWSxCOLS, for example 2x3")
    parser.add_argument(
        "--ref-image",
        action="append",
        default=[],
        help="Reference image for region/panel hash comparison. Repeat for multiple references.",
    )
    parser.add_argument("--hash-size", type=int, default=8, help="dHash size; default 8 produces 64-bit hashes.")
    parser.add_argument(
        "--hash-review-threshold",
        type=int,
        default=10,
        help="Distance above this value is reported as REVIEW_DIFFERENCE, still soft-signal only.",
    )
    parser.add_argument(
        "--enable-ocr",
        action="store_true",
        help="Attempt optional OCR collection with pytesseract/Tesseract if available.",
    )
    parser.add_argument(
        "--expect-text",
        action="append",
        default=[],
        help="Expected OCR text. Use 'must-match:text' or 'incidental:text'. Repeat for multiple text fields.",
    )
    parser.add_argument(
        "--watermark-keyword",
        action="append",
        default=[],
        help="Extra OCR keyword for watermark/text-overlay hints. Repeat for multiple keywords.",
    )
    parser.add_argument("--ocr-max-items", type=int, default=200, help="Maximum OCR tokens to keep in the manifest.")
    args = parser.parse_args()

    if args.hash_size <= 0:
        raise ValueError("--hash-size must be positive")
    if args.hash_review_threshold < 0:
        raise ValueError("--hash-review-threshold must be zero or positive")
    if args.ocr_max_items <= 0:
        raise ValueError("--ocr-max-items must be positive")

    expected_ratio = parse_ratio(args.expected_ratio)
    grid = parse_grid(args.grid)
    expected_texts = parse_expected_text_items(args.expect_text)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    images = [
        audit_image(
            Path(path),
            expected_ratio=expected_ratio,
            ratio_tolerance=args.ratio_tolerance,
            expected_width=args.expected_width,
            expected_height=args.expected_height,
            grid=grid,
            ref_paths=[Path(ref_path) for ref_path in args.ref_image],
            hash_size=args.hash_size,
            hash_review_threshold=args.hash_review_threshold,
            enable_ocr=args.enable_ocr,
            expected_texts=expected_texts,
            watermark_keywords=args.watermark_keyword,
            ocr_max_items=args.ocr_max_items,
        )
        for path in args.image
    ]

    statuses = {item["part_a_status"] for item in images}
    if "AUDIT_INCOMPLETE" in statuses:
        overall = "AUDIT_INCOMPLETE"
    elif "TECH_SPEC_REVIEW" in statuses:
        overall = "TECH_SPEC_REVIEW"
    else:
        overall = "AUDIT_READY"

    manifest = {
        "tool": "image_asset_audit",
        "version": "0.2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile,
        "overall_part_a_status": overall,
        "images": images,
    }
    manifest_path = out_dir / "image_asset_audit_manifest.json"
    report_path = out_dir / "image_asset_audit_evidence.md"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
    write_markdown(manifest, report_path)
    print(f"wrote {manifest_path}")
    print(f"wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
