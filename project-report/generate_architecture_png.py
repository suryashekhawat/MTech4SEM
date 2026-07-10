#!/usr/bin/env python3
"""Generate system_architecture.png for the project report."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "system_architecture.png"

WIDTH, HEIGHT = 1200, 900
MARGIN = 40

LAYERS = [
    ("Presentation", "#2563EB", [
        "app.py (CLI)",
        "streamlit_app.py — hour scrubber, Critical Brief, doctor dialogue",
    ]),
    ("Clinical decision support", "#059669", [
        "critical_brief.py — SBAR, trends, alerts, actions",
        "feedback_overlay.py — clinician-adjusted brief",
        "temporal_timeline.py — point-in-time snapshots",
    ]),
    ("Orchestration", "#D97706", [
        "patient_pipeline.py / pipeline_source.py",
        "Apache Airflow DAGs — batch + temporal reasoning",
    ]),
    ("Agent layer", "#7C3AED", [
        "RiskAgent, NarrativeAgent, VitalsAgent, LabsAgent, …",
        "Synthetic generators when eICU fields are missing",
    ]),
    ("Data", "#64748B", [
        "eICU-CRD demo SQLite + CSV.gz (eicu_loader.py)",
        "ICU_DATA_SOURCE=eicu | synthetic fallback",
    ]),
]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def draw_arrow(draw: ImageDraw.ImageDraw, x: int, y1: int, y2: int, color: str) -> None:
    draw.line([(x, y1), (x, y2)], fill=color, width=3)
    draw.polygon([(x - 8, y2 - 14), (x + 8, y2 - 14), (x, y2)], fill=color)


def main() -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), "#F8FAFC")
    draw = ImageDraw.Draw(img)

    title_font = _font(28, bold=True)
    layer_font = _font(20, bold=True)
    body_font = _font(16)
    small_font = _font(14)

    draw.text((WIDTH // 2, MARGIN), "ICU Multi-Agent System Architecture", fill="#0F172A", font=title_font, anchor="mt")

    side_x = MARGIN + 20
    box_x = MARGIN + 120
    box_w = WIDTH - box_x - MARGIN
    layer_h = 130
    gap = 12
    y = MARGIN + 50

    for idx, (name, color, bullets) in enumerate(LAYERS):
        top = y + idx * (layer_h + gap)
        bottom = top + layer_h

        draw.rounded_rectangle(
            (box_x, top, box_x + box_w, bottom),
            radius=12,
            fill="#FFFFFF",
            outline=color,
            width=3,
        )
        draw.rounded_rectangle(
            (box_x, top, box_x + 18, bottom),
            radius=12,
            fill=color,
        )

        draw.text((box_x + 28, top + 14), name, fill=color, font=layer_font)
        by = top + 48
        for bullet in bullets:
            draw.text((box_x + 28, by), f"• {bullet}", fill="#334155", font=body_font)
            by += 26

        if idx < len(LAYERS) - 1:
            arrow_x = box_x + box_w // 2
            draw_arrow(draw, arrow_x, bottom, bottom + gap, "#94A3B8")

    # Side labels: eICU path vs synthetic
    draw.text((side_x, HEIGHT - 120), "eICU", fill="#059669", font=small_font)
    draw.text((side_x, HEIGHT - 98), "path", fill="#059669", font=small_font)
    draw.line([(side_x + 50, HEIGHT - 108), (box_x - 10, HEIGHT - 108)], fill="#059669", width=2)

    draw.text((side_x, HEIGHT - 70), "synthetic", fill="#64748B", font=small_font)
    draw.line([(side_x + 50, HEIGHT - 58), (box_x - 10, HEIGHT - 58)], fill="#64748B", width=2, joint="curve")

    draw.text(
        (WIDTH // 2, HEIGHT - 28),
        "Airflow + Docker orchestrate batch runs; Streamlit provides interactive point-in-time review",
        fill="#64748B",
        font=small_font,
        anchor="ms",
    )

    img.save(OUT, format="PNG", optimize=True)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
