"""Small, crisp line icons rendered with Pillow."""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable

import customtkinter as ctk
from PIL import Image, ImageColor, ImageDraw

from . import constants as C

SUPERSAMPLE = 4


def _rounded_line(draw: ImageDraw.ImageDraw, points: Iterable[tuple[float, float]], width: int, fill: str) -> None:
    points = list(points)
    if len(points) < 2:
        return
    draw.line(points, fill=fill, width=width, joint="curve")
    radius = max(1, width // 2)
    for x, y in (points[0], points[-1]):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def _icon_draw(name: str, draw: ImageDraw.ImageDraw, n: int, color: str, stroke: float) -> None:
    unit = n / 18.0
    width = max(1, round(stroke * unit))

    def p(x: float, y: float) -> tuple[float, float]:
        return (x * unit, y * unit)

    def pts(values: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
        return [p(x, y) for x, y in values]

    def line(values: Iterable[tuple[float, float]]) -> None:
        _rounded_line(draw, pts(values), width, color)

    def dot(x: float, y: float, radius: float = 1.35) -> None:
        cx, cy = p(x, y)
        r = radius * unit
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)

    if name == "plus":
        line([(9, 4), (9, 14)])
        line([(4, 9), (14, 9)])
    elif name == "more":
        for x in (4.2, 9, 13.8):
            dot(x, 9, 1.45)
    elif name == "close":
        line([(5, 5), (13, 13)])
        line([(13, 5), (5, 13)])
    elif name == "check":
        line([(4, 9.5), (7.5, 13), (14, 5.5)])
    elif name in ("chevron_down", "chevron_up"):
        if name == "chevron_down":
            line([(4.5, 7), (9, 11.5), (13.5, 7)])
        else:
            line([(4.5, 11), (9, 6.5), (13.5, 11)])
    elif name in ("pin", "pin_filled"):
        if name == "pin_filled":
            cx, cy = p(9, 6.6)
            r = 4.6 * unit
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
            line([(5.9, 9.0), (9, 16)])
            line([(12.1, 9.0), (9, 16)])
            hole = 1.8 * unit
            draw.ellipse((cx - hole, cy - hole, cx + hole, cy + hole), fill=(0, 0, 0, 0))
        else:
            cx, cy = p(9, 6.6)
            r = 4.2 * unit
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=width)
            line([(6.0, 9.2), (9, 16)])
            line([(12.0, 9.2), (9, 16)])
            dot(9, 6.6, 1.1)
    elif name == "grip":
        for y in (5, 9, 13):
            for x in (7, 11):
                dot(x, y, 1.05)
    elif name == "edit":
        line([(4.2, 13.8), (12.2, 5.8)])
        line([(10.8, 4.4), (13.6, 7.2)])
        line([(4.2, 13.8), (3.2, 15.8)])
        line([(3.2, 15.8), (5.2, 14.8)])
        line([(12.2, 5.8), (13.6, 7.2)])
    elif name == "trash":
        line([(4, 5.2), (14, 5.2)])
        line([(6.8, 5.2), (7.5, 3.3), (10.5, 3.3), (11.2, 5.2)])
        line([(5.3, 5.2), (6.1, 15.7), (11.9, 15.7), (12.7, 5.2)])
        line([(8, 8), (8, 13)])
        line([(10, 8), (10, 13)])
    elif name == "power":
        draw.arc((4 * unit, 4 * unit, 14 * unit, 14 * unit), start=300, end=240, fill=color, width=width)
        line([(9, 2.5), (9, 8.5)])
    elif name == "new_card":
        draw.rounded_rectangle(
            (5 * unit, 4 * unit, 13 * unit, 12 * unit),
            radius=1.8 * unit,
            outline=color,
            width=width,
        )
        draw.rounded_rectangle(
            (2.8 * unit, 6.5 * unit, 10.8 * unit, 14.5 * unit),
            radius=1.8 * unit,
            outline=color,
            width=width,
        )
        line([(12.7, 12.6), (12.7, 16.4)])
        line([(10.8, 14.5), (14.6, 14.5)])
    elif name == "sparkle":
        points = pts([(9, 2.5), (10.6, 7.4), (15.5, 9), (10.6, 10.6), (9, 15.5), (7.4, 10.6), (2.5, 9), (7.4, 7.4)])
        draw.polygon(points, fill=color)
    elif name == "check_circle":
        cx, cy = p(9, 9)
        r = 6.5 * unit
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=width)
        line([(5.9, 9.2), (8.2, 11.5), (12.2, 6.8)])
    elif name == "hint":
        cx, cy = p(9, 9)
        r = 6.5 * unit
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=width)
        dot(9, 5.8, 1.05)
        line([(9, 8.6), (9, 12.7)])
    elif name == "arrow_up_right":
        line([(6, 12), (12, 6)])
        line([(7, 6), (12, 6), (12, 11)])
    else:  # safe fallback
        cx, cy = p(9, 9)
        r = 2.2 * unit
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)


@lru_cache(maxsize=256)
def get_icon(name: str, color: str, size: int = 18, stroke: float = 1.7, filled: bool = False) -> ctk.CTkImage:
    pixels = max(8, int(size)) * SUPERSAMPLE
    image = Image.new("RGBA", (pixels, pixels), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    _icon_draw(f"{name}_filled" if filled else name, draw, pixels, color, stroke)
    image = image.resize((max(8, int(size)), max(8, int(size))), Image.Resampling.LANCZOS)
    return ctk.CTkImage(light_image=image, dark_image=image, size=(max(8, int(size)), max(8, int(size))))


@lru_cache(maxsize=16)
def get_empty_art(accent: str, size: int = 62) -> ctk.CTkImage:
    """A soft checklist illustration used by an empty card."""
    pixels = size * SUPERSAMPLE
    image = Image.new("RGBA", (pixels, pixels), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    u = pixels / 64.0
    width = max(1, round(1.4 * u))

    border = ImageColor.getrgb(C.BORDER_STRONG) + (255,)
    accent_rgb = ImageColor.getrgb(accent) + (255,)
    muted = ImageColor.getrgb(C.TEXT_DIM) + (255,)

    draw.rounded_rectangle(
        (11 * u, 8 * u, 53 * u, 55 * u),
        radius=9 * u,
        fill=ImageColor.getrgb(C.SURFACE) + (255,),
        outline=border,
        width=width,
    )
    # Three list rows.  The top row is checked and tinted with the accent.
    draw.ellipse((19 * u, 19 * u, 27 * u, 27 * u), outline=accent_rgb, width=width)
    draw.line(
        [(22 * u, 23 * u), (23.6 * u, 24.6 * u), (25.8 * u, 21.6 * u)],
        fill=accent_rgb,
        width=width,
        joint="curve",
    )
    draw.rounded_rectangle((31 * u, 21 * u, 46 * u, 24 * u), radius=1.5 * u, fill=muted)
    for y in (33, 44):
        draw.ellipse((19 * u, y * u, 27 * u, (y + 8) * u), outline=border, width=width)
        draw.rounded_rectangle((31 * u, (y + 2) * u, 45 * u, (y + 5) * u), radius=1.5 * u, fill=border)
    # A tiny accent spark at the top-right.
    draw.polygon(
        [
            (52 * u, 4 * u),
            (54 * u, 9 * u),
            (59 * u, 11 * u),
            (54 * u, 13 * u),
            (52 * u, 18 * u),
            (50 * u, 13 * u),
            (45 * u, 11 * u),
            (50 * u, 9 * u),
        ],
        fill=accent_rgb,
    )
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))
