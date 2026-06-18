#!/usr/bin/env python3
"""Part A evidence collector for VVK image/keyframe audits.

This tool collects deterministic image facts and optional grid panel boxes.
It does not decide whether an image visually passes. OCR, face detection,
watermark detection, and perceptual hashing are soft-signal extensions and are
reported as unavailable until a reliable implementation is wired in.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


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


def audit_image(
    image_path: Path,
    expected_ratio: float | None,
    ratio_tolerance: float,
    expected_width: int | None,
    expected_height: int | None,
    grid: tuple[int, int] | None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source_path": str(image_path),
        "exists": image_path.exists(),
        "readable": False,
        "checks": [],
        "soft_signals": {
            "ocr": {"status": "NOT_AVAILABLE", "note": "soft signal only; no OCR engine wired"},
            "face_count": {"status": "NOT_AVAILABLE", "note": "soft signal only; no face detector wired"},
            "watermark_or_text_overlay": {
                "status": "NOT_AVAILABLE",
                "note": "soft signal only; no detector wired",
            },
            "perceptual_hash_or_embedding": {
                "status": "NOT_AVAILABLE",
                "note": "soft signal only; no hash/embedding implementation wired",
            },
        },
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


def write_markdown(manifest: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Image Asset Audit Evidence",
        "",
        f"- Created: {manifest['created_at']}",
        f"- Profile: {manifest['profile']}",
        f"- Overall Part A status: `{manifest['overall_part_a_status']}`",
        "",
        "Part A evidence does not decide visual PASS/FAIL. Use VVK Part B/C for visual judgment.",
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
                f"| {check['name']} | {check['status']} | {check['detail']} | {check.get('issue_class') or ''} |"
            )
        lines.extend(
            [
                "",
                "Soft signals currently unavailable: OCR, face count, watermark/text overlay, perceptual hash/embedding.",
                "",
            ]
        )
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
    args = parser.parse_args()

    expected_ratio = parse_ratio(args.expected_ratio)
    grid = parse_grid(args.grid)
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
        "version": "0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile,
        "overall_part_a_status": overall,
        "images": images,
    }
    manifest_path = out_dir / "image_asset_audit_manifest.json"
    report_path = out_dir / "image_asset_audit_evidence.md"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(manifest, report_path)
    print(f"wrote {manifest_path}")
    print(f"wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
