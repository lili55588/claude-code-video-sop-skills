#!/usr/bin/env python3
"""Render image-space annotations without calling any generation service."""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


@dataclass
class Annotation:
    kind: str
    coords: list[float]
    color: str
    width: int
    text: str = ""


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    for name in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        path = windir / "Fonts" / name
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                pass
    return ImageFont.load_default()


def split_color(value: str, default: str) -> tuple[str, str]:
    if "|" not in value:
        return default, value
    color, payload = value.split("|", 1)
    return color.strip(), payload.strip()


def numbers(value: str, expected: int, option: str) -> list[float]:
    try:
        result = [float(item.strip()) for item in value.split(",")]
    except ValueError as exc:
        raise ValueError(f"{option} requires comma-separated numbers: {value}") from exc
    if len(result) != expected:
        raise ValueError(f"{option} requires {expected} numbers: {value}")
    return result


def parse_shape(kind: str, value: str, default_color: str, width: int) -> Annotation:
    color, payload = split_color(value, default_color)
    return Annotation(kind, numbers(payload, 4, f"--{kind}"), color, width)


def parse_label(value: str, default_color: str, width: int) -> Annotation:
    color, payload = split_color(value, default_color)
    parts = payload.split(",", 2)
    if len(parts) != 3:
        raise ValueError("--label format is [COLOR|]x,y,text")
    return Annotation("label", [float(parts[0]), float(parts[1])], color, width, parts[2].strip())


def draw_arrow(draw: ImageDraw.ImageDraw, ann: Annotation) -> None:
    x1, y1, x2, y2 = ann.coords
    draw.line((x1, y1, x2, y2), fill=ann.color, width=ann.width)
    angle = math.atan2(y2 - y1, x2 - x1)
    head = max(18, ann.width * 4)
    spread = math.radians(28)
    p1 = (x2 - head * math.cos(angle - spread), y2 - head * math.sin(angle - spread))
    p2 = (x2 - head * math.cos(angle + spread), y2 - head * math.sin(angle + spread))
    draw.polygon(((x2, y2), p1, p2), fill=ann.color)


def render(source: Path, output: Path, annotations: list[Annotation]) -> None:
    with Image.open(source) as image_file:
        image = image_file.convert("RGBA")
    draw = ImageDraw.Draw(image)
    for ann in annotations:
        if ann.kind == "circle":
            draw.ellipse(tuple(ann.coords), outline=ann.color, width=ann.width)
        elif ann.kind == "box":
            draw.rectangle(tuple(ann.coords), outline=ann.color, width=ann.width)
        elif ann.kind == "arrow":
            draw_arrow(draw, ann)
        elif ann.kind == "label":
            draw.text(
                tuple(ann.coords),
                ann.text,
                fill=ann.color,
                font=load_font(max(20, ann.width * 4)),
                stroke_width=1,
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG")
    output.with_suffix(".annotations.json").write_text(
        json.dumps(
            {
                "source": str(source.resolve()),
                "output": str(output.resolve()),
                "generation_called": False,
                "annotations": [asdict(item) for item in annotations],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def self_test(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    source = output.with_name(output.stem + "_source.png")
    Image.new("RGB", (640, 360), "white").save(source)
    sample = [
        Annotation("box", [80, 90, 220, 250], "#ff0000", 8),
        Annotation("arrow", [220, 170, 430, 120], "#ff0000", 8),
        Annotation("label", [85, 45], "#ff0000", 6, "CAMERA"),
        Annotation("circle", [420, 180, 570, 320], "#00aa00", 8),
    ]
    render(source, output, sample)
    source.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline image annotation renderer; never calls image generation")
    parser.add_argument("image", nargs="?", help="source image")
    parser.add_argument("--output", help="output PNG")
    parser.add_argument("--circle", action="append", help="[COLOR|]x1,y1,x2,y2")
    parser.add_argument("--box", action="append", help="[COLOR|]x1,y1,x2,y2")
    parser.add_argument("--arrow", action="append", help="[COLOR|]x1,y1,x2,y2")
    parser.add_argument("--label", action="append", help="[COLOR|]x,y,text")
    parser.add_argument("--color", default="#ff0000", help="default annotation color")
    parser.add_argument("--width", type=int, default=8, help="annotation width")
    parser.add_argument("--self-test", metavar="OUTPUT", help="render a local test image")
    args = parser.parse_args()

    if args.self_test:
        self_test(Path(args.self_test).resolve())
        print(f"self-test ok: {Path(args.self_test).resolve()}")
        return 0
    if not args.image or not args.output:
        parser.error("image and --output are required")

    annotations: list[Annotation] = []
    for value in args.circle or []:
        annotations.append(parse_shape("circle", value, args.color, args.width))
    for value in args.box or []:
        annotations.append(parse_shape("box", value, args.color, args.width))
    for value in args.arrow or []:
        annotations.append(parse_shape("arrow", value, args.color, args.width))
    for value in args.label or []:
        annotations.append(parse_label(value, args.color, args.width))
    if not annotations:
        parser.error("at least one annotation is required")

    output = Path(args.output).resolve()
    render(Path(args.image).resolve(), output, annotations)
    print(f"marked image saved: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
