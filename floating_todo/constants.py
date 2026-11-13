"""Shared visual constants and limits for Floating Todo."""

from __future__ import annotations

from dataclasses import dataclass

APP_NAME = "悬浮待办"
APP_ID = "FloatingTodoCard"
APP_VERSION = 1

DATA_DIR_NAME = "FloatingTodoCard"
MUTEX_NAME = r"Local\FloatingTodoCard_v1"
WAKE_FILE_NAME = "wake.signal"
STATE_FILE_NAME = "state.json"
BACKUP_FILE_NAME = "state.json.bak"
LOG_FILE_NAME = "app.log"

# --- dimensions (logical pixels at 100% scaling) -------------------------
CARD_WIDTH = 372
CARD_WIDTH_MIN = 300
CARD_WIDTH_MAX = 560
CARD_HEIGHT_MIN = 340
CARD_HEIGHT_MAX = 1200
RESIZE_HANDLE_SIZE = 18
TITLE_WIDTH_OVERHEAD = 172
TASK_WIDTH_OVERHEAD = 122
MIN_TITLE_WIDTH = 120
MIN_TASK_WIDTH = 160
CARD_RADIUS = 22
CARD_PAD_X = 16
HEADER_TOP_PAD = 14
HEADER_BOTTOM_PAD = 8
HEADER_HEIGHT = 68
TASK_AREA_MAX_HEIGHT = 300
TASK_ROW_ONE_LINE = 32
TASK_ROW_TWO_LINE = 50
EMPTY_STATE_HEIGHT = 106
ADD_BAR_HEIGHT = 40
FOOTER_HEIGHT = 44
CARD_MIN_HEIGHT = 238
CARD_GAP = 10  # gap left between magnetically joined cards
SNAP_THRESHOLD = 14
DOCK_TOLERANCE = 7
DRAG_START_DISTANCE = 4
DEFAULT_MARGIN = 36
NEW_CARD_OFFSET = 30
MAX_VISIBLE_TASKS = 6
VISIBLE_MARGIN = 10

# --- appearance ------------------------------------------------------------
DEFAULT_APPEARANCE = "solid"
APPEARANCES = ("solid", "glass")
DEFAULT_GLASS_LEVEL = 1
GLASS_LEVELS = ("light", "standard", "deep")
GLASS_LEVEL_LABELS = ("清淡", "标准", "浓郁")
GLASS_BASE = "#0D121B"
GROUP_DETACH_GAP = 28  # extra gap added when a group is split manually

# --- limits ----------------------------------------------------------------
MAX_CARDS = 20
MAX_TASKS_PER_CARD = 300
MAX_TITLE_LEN = 60
MAX_TASK_LEN = 300

# --- timing ----------------------------------------------------------------
SAVE_DEBOUNCE_MS = 300
WAKE_POLL_MS = 800
COMBINE_HINT_MS = 2800
GEOMETRY_SETTLE_MS = 35

# --- colors ----------------------------------------------------------------
WINDOW_KEY = "#010203"  # chroma-key color; must never appear on the card
CARD_BG = "#171A20"
CARD_BG_ALT = "#1B1F27"
SURFACE = "#20252F"
SURFACE_HOVER = "#272D39"
SURFACE_ACTIVE = "#2D3441"
BORDER = "#2A303B"
BORDER_STRONG = "#394253"
TEXT = "#F3F5F9"
TEXT_MUTED = "#98A2B3"
TEXT_DIM = "#6F7888"
TEXT_ON_ACCENT = "#101319"
DANGER = "#FF7A7A"
DANGER_HOVER = "#3A252B"

UI_FONT_FAMILIES = ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "Arial")
UI_FONT_FALLBACK = "TkDefaultFont"


@dataclass(frozen=True)
class Accent:
    key: str
    name: str
    color: str


ACCENTS: tuple[Accent, ...] = (
    Accent("coral", "珊瑚", "#FF7A6B"),
    Accent("mint", "薄荷", "#59D3A5"),
    Accent("sky", "天青", "#5FB8FF"),
    Accent("amber", "杏黄", "#FFC35C"),
    Accent("lilac", "紫藤", "#B79CFF"),
    Accent("rose", "玫瑰", "#FF8FB8"),
)
ACCENT_BY_KEY = {accent.key: accent for accent in ACCENTS}
DEFAULT_ACCENT = ACCENTS[0].key


def accent_color(key: str) -> str:
    return ACCENT_BY_KEY.get(key, ACCENT_BY_KEY[DEFAULT_ACCENT]).color


# --- theme palettes --------------------------------------------------------
@dataclass(frozen=True)
class ThemePalette:
    """Concrete colours used by a card or popup in one appearance mode."""

    card_bg: str
    card_border: str
    card_highlight: str
    surface: str
    surface_hover: str
    surface_active: str
    border: str
    border_strong: str
    scrollbar_bg: str
    scrollbar_button: str
    scrollbar_button_hover: str
    menu_bg: str
    menu_border: str
    menu_hover: str
    menu_separator: str


def _rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Invalid colour: {color!r}")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def mix_color(base: str, overlay: str, amount: float) -> str:
    """Blend two hex colours; amount is the weight of ``overlay``."""
    amount = max(0.0, min(1.0, float(amount)))
    ar, ag, ab = _rgb(base)
    br, bg, bb = _rgb(overlay)
    return "#{:02X}{:02X}{:02X}".format(
        round(ar + (br - ar) * amount),
        round(ag + (bg - ag) * amount),
        round(ab + (bb - ab) * amount),
    )


def solid_palette() -> ThemePalette:
    return ThemePalette(
        card_bg=CARD_BG,
        card_border=BORDER,
        card_highlight=CARD_BG,
        surface=SURFACE,
        surface_hover=SURFACE_HOVER,
        surface_active=SURFACE_ACTIVE,
        border=BORDER,
        border_strong=BORDER_STRONG,
        scrollbar_bg=CARD_BG,
        scrollbar_button=SURFACE_ACTIVE,
        scrollbar_button_hover=BORDER_STRONG,
        menu_bg=CARD_BG_ALT,
        menu_border=BORDER_STRONG,
        menu_hover=SURFACE_HOVER,
        menu_separator=BORDER,
    )


def glass_palette(accent_key: str = DEFAULT_ACCENT, level: int = DEFAULT_GLASS_LEVEL) -> ThemePalette:
    """A coloured translucent-looking (but opaque) glass palette.

    ``level`` 0/1/2 controls the tint density (清淡/标准/浓郁).
    """
    level = max(0, min(2, int(level)))
    accent = accent_color(accent_key)
    tint = (0.16, 0.26, 0.38)[level]
    surface_amount = (0.10, 0.15, 0.21)[level]
    border_amount = (0.34, 0.48, 0.60)[level]
    menu_amount = (0.14, 0.20, 0.28)[level]
    background = mix_color(GLASS_BASE, accent, tint)
    surface = mix_color(background, accent, surface_amount)
    border = mix_color(background, accent, border_amount)
    menu_bg = mix_color("#0F141D", accent, menu_amount)
    return ThemePalette(
        card_bg=background,
        card_border=border,
        card_highlight=mix_color(background, "#FFFFFF", 0.22 + 0.05 * level),
        surface=surface,
        surface_hover=mix_color(surface, "#FFFFFF", 0.055),
        surface_active=mix_color(surface, "#FFFFFF", 0.10),
        border=border,
        border_strong=mix_color(background, accent, 0.55 + 0.07 * level),
        scrollbar_bg=background,
        scrollbar_button=mix_color(background, accent, 0.38),
        scrollbar_button_hover=mix_color(background, accent, 0.62),
        menu_bg=menu_bg,
        menu_border=mix_color(menu_bg, accent, 0.44 + 0.04 * level),
        menu_hover=mix_color(menu_bg, "#FFFFFF", 0.07),
        menu_separator=mix_color(menu_bg, accent, 0.24 + 0.04 * level),
    )


def theme_palette(
    appearance: str,
    accent_key: str = DEFAULT_ACCENT,
    glass_level: int = DEFAULT_GLASS_LEVEL,
) -> ThemePalette:
    if appearance == "glass":
        return glass_palette(accent_key, glass_level)
    return solid_palette()
