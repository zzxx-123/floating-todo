"""One independent, chroma-keyed floating card window."""

from __future__ import annotations

import logging
import math
import tkinter as tk
from typing import Any, Callable

import customtkinter as ctk

from . import constants as C
from .icons import get_icon
from .models import Card, clean_task_text, clean_title
from .platform_win import apply_topmost, make_overlay
from .snapping import Rect
from .widgets import (
    AddTaskBar,
    CardFooter,
    CardHeader,
    EmptyState,
    OnboardingTip,
    TaskList,
    bind_widget,
    set_cursor,
)

log = logging.getLogger(__name__)


class CardWindow:
    """A single card.  The manager owns z-order and dragging across cards."""

    def __init__(
        self,
        root: Any,
        card: Card,
        screen_manager: Any,
        *,
        show_tip: bool,
        on_changed: Callable[[], None],
        on_menu: Callable[[Any], None],
        on_drag_start: Callable[[Any], None],
        on_drag_motion: Callable[[Any], None],
        on_drag_end: Callable[[Any], None],
        on_tip_dismissed: Callable[[], None],
        appearance: str = C.DEFAULT_APPEARANCE,
        glass_level: int = C.DEFAULT_GLASS_LEVEL,
        on_resized: Callable[[], None] | None = None,
    ) -> None:
        self.card = card
        self.appearance = appearance if appearance in C.APPEARANCES else C.DEFAULT_APPEARANCE
        self.glass_level = max(0, min(2, int(glass_level)))
        self.palette = C.theme_palette(self.appearance, card.accent, self.glass_level)
        self.screen = screen_manager
        self.on_changed = on_changed
        self.on_menu = on_menu
        self.on_drag_start = on_drag_start
        self.on_drag_motion = on_drag_motion
        self.on_drag_end = on_drag_end
        self.on_tip_dismissed = on_tip_dismissed
        self.on_resized = on_resized
        self.on_toggle_task = self._toggle_task
        self.on_delete_task = self._delete_task
        self.on_edit_task = self._edit_task

        self._hint_text: str | None = None
        self._hint_after: str | None = None
        self._autosize_after: str | None = None
        self._destroyed = False
        self._logical_width = (
            card.width if card.width else C.CARD_WIDTH
        )
        self._logical_height = card.height if card.height else C.CARD_MIN_HEIGHT
        self._manual_width = bool(card.width)
        self._manual_height = bool(card.height)
        self._resizing = False
        self._resize_origin: tuple[int, int, int, int] | None = None
        self._scale = 1.0

        self.top = ctk.CTkToplevel(root)
        self.top.withdraw()
        try:
            self._scale = float(ctk.ScalingTracker.get_window_scaling(self.top))
        except Exception:
            self._scale = 1.0
        if self._scale <= 0:
            self._scale = 1.0
        self.width = max(1, int(round(self._logical_width * self._scale)))
        self.height = max(1, int(round(self._logical_height * self._scale)))
        self.x, self.y = self.screen.ensure_rect_visible(
            int(card.x), int(card.y), self.width, self.height
        )
        card.x, card.y = self.x, self.y

        make_overlay(self.top)
        try:
            self.top.configure(fg_color=C.WINDOW_KEY)
        except Exception:
            log.debug("Could not set window key colour", exc_info=True)
            try:
                self.top.configure(fg_color=C.CARD_BG)
            except Exception:
                pass
        self.top.protocol("WM_DELETE_WINDOW", self.raise_card)

        self.shell = ctk.CTkFrame(
            self.top,
            fg_color=self.palette.card_bg,
            corner_radius=C.CARD_RADIUS,
            border_width=1,
            border_color=self.palette.card_border,
            width=self._logical_width,
        )
        self.shell.pack(fill="both", expand=True)

        self._accent = C.accent_color(card.accent)
        self._build_header()
        self._build_body(show_tip)
        self._build_footer()
        self._build_resize_handle()
        self._apply_layout()
        self._apply_palette()
        self._render_content()
        self._update_header()
        self.top.update_idletasks()
        self._autosize()
        self.top.withdraw()

    # ------------------------------------------------------------------ build
    def _title_width(self) -> int:
        return max(C.MIN_TITLE_WIDTH, self._logical_width - C.TITLE_WIDTH_OVERHEAD)

    def _task_width(self) -> int:
        return max(C.MIN_TASK_WIDTH, self._logical_width - C.TASK_WIDTH_OVERHEAD)

    def _build_header(self) -> None:
        self._header = CardHeader(
            self.shell,
            self.card,
            self._accent,
            on_toggle_pin=self.toggle_pin,
            on_toggle_collapse=self.toggle_collapse,
            on_menu=self.on_menu,
            on_rename=self.rename,
            on_drag_start=self.on_drag_start,
            on_drag_motion=self.on_drag_motion,
            on_drag_end=self.on_drag_end,
            palette=self.palette,
            title_width=self._title_width(),
        )

    def _build_body(self, show_tip: bool) -> None:
        self._body = ctk.CTkFrame(self.shell, fg_color="transparent", corner_radius=0)
        self._tip = (
            OnboardingTip(self._body, self._dismiss_tip, self.palette) if show_tip else None
        )
        if self._tip is not None:
            self._tip.pack(fill="x", pady=(0, 8))
        self._host = ctk.CTkFrame(self._body, fg_color="transparent", corner_radius=0)
        self._host.pack(fill="both", expand=True)
        self._empty = EmptyState(self._host, self._accent, self.focus_input)
        self._tasks = TaskList(
            self._host,
            on_toggle=self.on_toggle_task,
            on_delete=self.on_delete_task,
            on_edit=self.on_edit_task,
            palette=self.palette,
            text_width=self._task_width(),
        )
        self._add_bar = AddTaskBar(
            self.shell, self._accent, self._add_task, palette=self.palette
        )

    def _build_footer(self) -> None:
        self._footer = CardFooter(self.shell, self._accent, palette=self.palette)

    def _build_resize_handle(self) -> None:
        size = C.RESIZE_HANDLE_SIZE
        self._grip = ctk.CTkLabel(
            self.shell,
            text="",
            image=get_icon("resize", C.TEXT_DIM, 14, 1.5),
            width=size,
            height=size,
            fg_color=self.palette.card_bg,
            corner_radius=0,
        )
        self._grip.place(relx=1.0, rely=1.0, x=-7, y=-7, anchor="se")
        set_cursor(self._grip, "size_nwse")
        bind_widget(self._grip, "<ButtonPress-1>", self._resize_start)
        bind_widget(self._grip, "<B1-Motion>", self._resize_motion)
        bind_widget(self._grip, "<ButtonRelease-1>", self._resize_end)
        self._grip.lift()

    # ----------------------------------------------------------------- layout
    def _apply_layout(self) -> None:
        self._header.pack_forget()
        self._body.pack_forget()
        self._add_bar.pack_forget()
        self._footer.pack_forget()
        grip = getattr(self, "_grip", None)
        if grip is not None:
            try:
                grip.place_forget()
            except Exception:
                pass

        if self.card.collapsed:
            self._header.pack(fill="x", padx=C.CARD_PAD_X, pady=(14, 14))
            return

        self._header.pack(fill="x", padx=C.CARD_PAD_X, pady=(C.HEADER_TOP_PAD, 8))
        self._footer.pack(
            side="bottom", fill="x", padx=C.CARD_PAD_X, pady=(8, 14)
        )
        self._add_bar.pack(
            side="bottom", fill="x", padx=C.CARD_PAD_X, pady=(8, 0)
        )
        self._body.pack(fill="both", expand=True, padx=C.CARD_PAD_X)
        if grip is not None:
            try:
                grip.place(relx=1.0, rely=1.0, x=-7, y=-7, anchor="se")
                grip.lift()
            except Exception:
                pass

    def _autosize(self) -> None:
        if self._destroyed:
            return
        self._autosize_after = None
        try:
            self.top.update_idletasks()
            req_height = self.shell.winfo_reqheight()
        except Exception:
            return
        logical = int(math.ceil(req_height / self._scale)) if req_height > 0 else 1
        if not self.card.collapsed:
            logical = max(C.CARD_MIN_HEIGHT, logical)
            if self.card.height:
                logical = max(C.CARD_HEIGHT_MIN, min(C.CARD_HEIGHT_MAX, int(self.card.height)))
            else:
                logical = min(logical, C.CARD_HEIGHT_MAX)
        else:
            logical = max(40, min(logical, C.CARD_HEIGHT_MAX))
        self._logical_height = logical
        self.width = max(1, int(round(self._logical_width * self._scale)))
        self.height = max(1, int(round(logical * self._scale)))
        try:
            self.top.geometry(
                f"{self._logical_width}x{logical}+{int(self.x)}+{int(self.y)}"
            )
        except Exception:
            log.debug("Card geometry failed", exc_info=True)
            return
        if self._is_visible():
            self._keep_in_workarea()
        self.top.update_idletasks()
        try:
            actual_w = self.top.winfo_width()
            actual_h = self.top.winfo_height()
            if actual_w > 1:
                self.width = actual_w
            if actual_h > 1:
                self.height = actual_h
        except Exception:
            pass
        if self.card.height and not self.card.collapsed:
            self._sync_task_viewport()

    def _schedule_autosize(self) -> None:
        if self._destroyed or self._autosize_after is not None:
            return
        try:
            self._autosize_after = self.top.after(30, self._autosize)
        except Exception:
            self._autosize_after = None

    def _sync_task_viewport(self) -> None:
        if not self.card.tasks or self.card.collapsed:
            self._tasks.set_max_height(C.TASK_AREA_MAX_HEIGHT)
            return
        try:
            host_height = self._host.winfo_height()
        except Exception:
            return
        if host_height <= 1:
            return
        available = max(1, int((host_height - 2) / self._scale))
        self._tasks.set_max_height(available)

    def _apply_text_widths(self) -> None:
        try:
            self._header.set_title_width(self._title_width())
            self._tasks.set_text_width(self._task_width())
        except Exception:
            log.debug("Could not apply dynamic text widths", exc_info=True)

    # ---------------------------------------------------------------- resizing
    def _resize_start(self, event: Any) -> None:
        if self._destroyed or self.card.collapsed:
            return
        self._resizing = True
        self._resize_origin = (
            int(event.x_root),
            int(event.y_root),
            int(self._logical_width),
            int(self._logical_height),
        )

    def _resize_motion(self, event: Any) -> None:
        if not self._resizing or self._resize_origin is None:
            return
        start_x, start_y, start_w, start_h = self._resize_origin
        dx = (int(event.x_root) - start_x) / self._scale
        dy = (int(event.y_root) - start_y) / self._scale
        width = max(C.CARD_WIDTH_MIN, min(C.CARD_WIDTH_MAX, int(round(start_w + dx))))
        height = max(C.CARD_HEIGHT_MIN, min(C.CARD_HEIGHT_MAX, int(round(start_h + dy))))
        self._apply_size(width, height)

    def _resize_end(self, _event: Any = None) -> None:
        if not self._resizing:
            return
        self._resizing = False
        self._resize_origin = None
        self._apply_text_widths()
        self._render_tasks()
        self._schedule_autosize()
        self._finish_resize()

    def _finish_resize(self) -> None:
        self.on_changed()
        if self.on_resized is not None:
            try:
                self.on_resized()
            except Exception:
                log.exception("Card resize callback failed")

    def _apply_size(self, width: int, height: int) -> None:
        if self._destroyed:
            return
        width = max(C.CARD_WIDTH_MIN, min(C.CARD_WIDTH_MAX, int(width)))
        height = max(C.CARD_HEIGHT_MIN, min(C.CARD_HEIGHT_MAX, int(height)))
        self._logical_width = width
        self._logical_height = height
        self.card.width = width
        self.card.height = height
        self.width = max(1, int(round(width * self._scale)))
        self.height = max(1, int(round(height * self._scale)))
        try:
            self.shell.configure(width=width)
            self.top.geometry(f"{width}x{height}+{int(self.x)}+{int(self.y)}")
        except Exception:
            log.debug("Resize geometry failed", exc_info=True)
        self._apply_text_widths()
        self._sync_task_viewport()

    def reset_size(self) -> None:
        if self._destroyed:
            return
        self.card.width = 0
        self.card.height = 0
        self._logical_width = C.CARD_WIDTH
        self._manual_width = False
        self._manual_height = False
        self._tasks.set_max_height(C.TASK_AREA_MAX_HEIGHT)
        try:
            self.shell.configure(width=C.CARD_WIDTH)
        except Exception:
            pass
        self._apply_text_widths()
        self._render_tasks()
        self._autosize()
        # The first geometry pass can run before Tk has recomputed the requested
        # height of every child; run one more deferred pass to settle on the
        # real auto height.
        self._schedule_autosize()
        self._finish_resize()

    def _keep_in_workarea(self) -> None:
        left, top, right, bottom = self.screen.workarea_for_rect(
            (self.x, self.y, self.x + self.width, self.y + self.height)
        )
        new_x, new_y = self.x, self.y
        if self.x < left:
            new_x = left
        if self.x + self.width > right:
            new_x = max(left, right - self.width)
        if self.y < top:
            new_y = top
        if self.y + self.height > bottom:
            new_y = max(top, bottom - self.height)
        if new_x != self.x or new_y != self.y:
            self.x, self.y = int(new_x), int(new_y)
            self.card.x, self.card.y = self.x, self.y
            try:
                self.top.geometry(f"+{self.x}+{self.y}")
            except Exception:
                pass

    def _is_visible(self) -> bool:
        try:
            return bool(self.top.winfo_ismapped())
        except Exception:
            return False

    # ------------------------------------------------------------------ show
    def show(self) -> None:
        if self._destroyed:
            return
        self._apply_layout()
        self._update_header()
        self.top.update_idletasks()
        self._autosize()
        try:
            self.top.geometry(f"+{self.x}+{self.y}")
            self.top.deiconify()
            self.top.update_idletasks()
            self._keep_in_workarea()
            self.top.lift()
            apply_topmost(self.top, self.card.pinned)
        except Exception:
            log.exception("Could not show card %s", self.card.id)
            return
        self.top.after(80, self._settle)

    def _settle(self) -> None:
        if self._destroyed:
            return
        try:
            self.top.update_idletasks()
            width = self.top.winfo_width()
            height = self.top.winfo_height()
            if width > 1:
                self.width = width
            if height > 1:
                self.height = height
            self._keep_in_workarea()
        except Exception:
            pass

    def raise_card(self) -> None:
        if self._destroyed:
            return
        try:
            if not self._is_visible():
                self.top.deiconify()
            self.top.lift()
            if self.card.pinned:
                apply_topmost(self.top, True)
        except Exception:
            log.debug("Could not raise card", exc_info=True)

    def focus_input(self) -> None:
        if self._destroyed:
            return
        self.raise_card()
        try:
            self.top.focus_force()
            self._add_bar.focus_entry()
        except Exception:
            pass

    # --------------------------------------------------------------- geometry
    def bounds(self) -> Rect:
        return (
            int(self.x),
            int(self.y),
            int(self.x + self.width),
            int(self.y + self.height),
        )

    def move_to(self, x: int, y: int, *, update_model: bool = True) -> None:
        if self._destroyed:
            return
        self.x, self.y = int(x), int(y)
        if update_model:
            self.card.x, self.card.y = self.x, self.y
        try:
            self.top.geometry(f"+{self.x}+{self.y}")
        except Exception:
            pass

    # ----------------------------------------------------------------- render
    def _update_header(self) -> None:
        try:
            self._header.set_state(self.card, self._accent)
            if self._hint_text:
                self._header.set_meta(self._hint_text)
        except Exception:
            log.debug("Header refresh failed", exc_info=True)

    def _render_content(self) -> None:
        if self._destroyed:
            return
        self._update_header()
        try:
            self._footer.update_for(
                self.card.completed_count, self.card.total_count, self._accent
            )
        except Exception:
            log.debug("Footer refresh failed", exc_info=True)
        self._render_tasks()
        self._schedule_autosize()

    def _render_tasks(self, *, scroll_to_bottom: bool = False) -> None:
        if self._destroyed:
            return
        if self.card.tasks:
            try:
                self._empty.pack_forget()
            except Exception:
                pass
            try:
                self._tasks.pack(fill="both", expand=True)
                self._tasks.rebuild(
                    self.card.tasks, self._accent, scroll_to_bottom=scroll_to_bottom
                )
            except Exception:
                log.exception("Task list refresh failed")
        else:
            try:
                self._tasks.pack_forget()
            except Exception:
                pass
            try:
                self._empty.pack(fill="both", expand=True)
            except Exception:
                log.debug("Empty state pack failed", exc_info=True)

    # --------------------------------------------------------------- callbacks
    def _add_task(self, text: str) -> bool:
        if self.card.total_count >= C.MAX_TASKS_PER_CARD:
            self.show_hint("每张卡片最多 300 项", accent=False)
            return False
        task = self.card.add_task(text)
        if task is None:
            return False
        self._update_header()
        self._footer.update_for(
            self.card.completed_count, self.card.total_count, self._accent
        )
        self._render_tasks(scroll_to_bottom=True)
        self._schedule_autosize()
        self.on_changed()
        return True

    def _toggle_task(self, task_id: str) -> None:
        task = self.card.find_task(task_id)
        if task is None:
            return
        task.done = not task.done
        self._render_content()
        self.on_changed()

    def _delete_task(self, task_id: str) -> None:
        if not self.card.remove_task(task_id):
            return
        self._render_content()
        self.on_changed()

    def _edit_task(self, task_id: str, text: str) -> bool:
        task = self.card.find_task(task_id)
        if task is None:
            return False
        cleaned = clean_task_text(text)
        if cleaned is None:
            return False
        task.text = cleaned
        self._render_content()
        self.on_changed()
        return True

    def toggle_pin(self) -> None:
        self.card.pinned = not self.card.pinned
        apply_topmost(self.top, self.card.pinned)
        self._update_header()
        self.on_changed()

    def toggle_collapse(self) -> None:
        self.card.collapsed = not self.card.collapsed
        self._apply_layout()
        self._update_header()
        self._schedule_autosize()
        self.on_changed()

    def clear_completed(self) -> None:
        if self.card.clear_completed() <= 0:
            return
        self._render_content()
        self.on_changed()

    def rename(self, text: str) -> None:
        cleaned = clean_title(text, self.card.title)
        if cleaned == self.card.title:
            self._update_header()
            return
        self.card.title = cleaned
        self._update_header()
        self.on_changed()

    def begin_rename(self, event: Any = None) -> str:
        try:
            return self._header.begin_rename(event)
        except Exception:
            log.exception("Could not start card rename")
            return "break"

    def set_accent(self, key: str) -> None:
        accent = C.accent_color(key)
        self.card.accent = key if key in C.ACCENT_BY_KEY else C.DEFAULT_ACCENT
        self._accent = accent
        self.palette = C.theme_palette(self.appearance, self.card.accent, self.glass_level)
        try:
            self._add_bar.set_accent(accent)
            self._footer.update_for(
                self.card.completed_count, self.card.total_count, accent
            )
            self._replace_empty_state()
            self._apply_palette()
            self._render_tasks()
        except Exception:
            log.exception("Applying accent failed")
        self._update_header()
        self._schedule_autosize()
        self.on_changed()

    def set_appearance(self, appearance: str, glass_level: int | None = None) -> None:
        new_level = self.glass_level if glass_level is None else max(0, min(2, int(glass_level)))
        if appearance not in C.APPEARANCES:
            appearance = C.DEFAULT_APPEARANCE
        if appearance == self.appearance and new_level == self.glass_level:
            return
        self.appearance = appearance
        self.glass_level = new_level
        self.palette = C.theme_palette(self.appearance, self.card.accent, self.glass_level)
        self._apply_palette()
        self._render_tasks()
        self._schedule_autosize()

    def set_glass_level(self, level: int) -> None:
        self.set_appearance(self.appearance, level)

    def _apply_palette(self) -> None:
        try:
            # Keep the whole surface opaque; "glass" is a tinted frost, not a
            # window-alpha overlay, so text stays crisp over any desktop.
            self.shell.configure(
                fg_color=self.palette.card_bg,
                border_color=self.palette.card_border,
            )
            rim = getattr(self, "_glass_rim", None)
            if rim is None:
                rim = tk.Frame(
                    self.shell,
                    height=2,
                    bd=0,
                    highlightthickness=0,
                    bg=self.palette.card_highlight,
                    takefocus=0,
                )
                rim.place(relx=0.055, rely=0, relwidth=0.89, height=2)
                self._glass_rim = rim
            else:
                rim.configure(bg=self.palette.card_highlight)
            rim.lift()
            self._header.set_palette(self.palette)
            self._add_bar.set_palette(self.palette)
            self._footer.set_palette(self.palette)
            self._tasks.set_palette(self.palette)
            grip = getattr(self, "_grip", None)
            if grip is not None:
                grip.configure(fg_color=self.palette.card_bg)
            if self._tip is not None:
                self._tip.set_palette(self.palette)
        except Exception:
            log.exception("Applying card palette failed")

    def _replace_empty_state(self) -> None:
        try:
            self._empty.destroy()
        except Exception:
            pass
        self._empty = EmptyState(self._host, self._accent, self.focus_input)
        if not self.card.tasks:
            self._empty.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ hints
    def show_hint(self, text: str, *, accent: bool = True, ms: int | None = None) -> None:
        self._hint_text = text
        try:
            self._header.set_meta(text, accent=accent)
        except Exception:
            pass
        if self._hint_after is not None:
            try:
                self.top.after_cancel(self._hint_after)
            except Exception:
                pass
        try:
            self._hint_after = self.top.after(
                ms if ms is not None else C.COMBINE_HINT_MS, self._clear_hint
            )
        except Exception:
            self._hint_after = None

    def _clear_hint(self) -> None:
        self._hint_after = None
        self._hint_text = None
        try:
            self._header.set_meta(None)
        except Exception:
            pass

    # ------------------------------------------------------------------- tips
    def _dismiss_tip(self) -> None:
        self.hide_tip()
        try:
            self.on_tip_dismissed()
        except Exception:
            log.exception("Onboarding dismissal failed")

    def hide_tip(self) -> None:
        if self._tip is not None:
            try:
                self._tip.pack_forget()
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None
            self._schedule_autosize()

    def has_tip(self) -> bool:
        return self._tip is not None

    # ------------------------------------------------------------------ close
    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        if self._hint_after is not None:
            try:
                self.top.after_cancel(self._hint_after)
            except Exception:
                pass
        if self._autosize_after is not None:
            try:
                self.top.after_cancel(self._autosize_after)
            except Exception:
                pass
        try:
            self.top.destroy()
        except Exception:
            pass
