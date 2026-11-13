"""Reusable custom widgets for the floating cards."""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Sequence

import customtkinter as ctk

from . import constants as C
from .icons import get_empty_art, get_icon
from .models import Card, Task
from .platform_win import left_button_down, raise_topmost
from .typography import ellipsize, line_count, ui_font, wrap_two_lines

log = logging.getLogger(__name__)

# The labels are laid out inside a scrollable frame, so their real width is a
# little smaller than the arithmetic card width.  Keep a safety margin; then
# the trailing ellipsis stays visible instead of being clipped by Tk.
TASK_TEXT_WIDTH = 250
TITLE_TEXT_WIDTH = 200


# --------------------------------------------------------------------- helpers
def walk_masters(widget: Any) -> Iterable[Any]:
    current = widget
    while current is not None:
        yield current
        current = getattr(current, "master", None)


def point_over(widget: Any) -> bool:
    try:
        x, y = widget.winfo_pointerxy()
        target = widget.winfo_containing(x, y)
    except Exception:
        return False
    if target is None:
        return False
    return any(item is widget for item in walk_masters(target))


def bind_widget(widget: Any, sequence: str, callback: Callable[..., Any]) -> None:
    """Bind both CTk widgets and the canvases some of them use internally."""
    try:
        widget.bind(sequence, callback, add="+")
        return
    except NotImplementedError:
        pass
    except Exception:
        log.debug("bind failed on %r", widget, exc_info=True)
    canvas = getattr(widget, "_canvas", None)
    if canvas is not None:
        try:
            canvas.bind(sequence, callback, add="+")
        except Exception:
            log.debug("canvas bind failed on %r", widget, exc_info=True)


def set_cursor(widget: Any, cursor: str) -> None:
    for target in (widget, getattr(widget, "_canvas", None), getattr(widget, "_label", None)):
        if target is None:
            continue
        try:
            target.configure(cursor=cursor)
        except Exception:
            pass


class IconButton(ctk.CTkButton):
    def __init__(
        self,
        master: Any,
        image: ctk.CTkImage,
        command: Callable[[], Any],
        *,
        width: int = 26,
        height: int = 26,
        corner_radius: int = 8,
        hover_color: str = C.SURFACE,
        fg_color: str = "transparent",
    ) -> None:
        super().__init__(
            master,
            text="",
            image=image,
            command=command,
            width=width,
            height=height,
            corner_radius=corner_radius,
            fg_color=fg_color,
            hover_color=hover_color,
            border_width=0,
            border_spacing=2,
        )
        set_cursor(self, "hand2")


# --------------------------------------------------------------------- task row
class TaskRow(ctk.CTkFrame):
    """One task row with a circular check, two-line text, hover delete and inline edit."""

    def __init__(
        self,
        master: Any,
        task: Task,
        accent: str,
        *,
        on_toggle: Callable[[str], None],
        on_delete: Callable[[str], None],
        on_edit: Callable[[str, str], bool],
        palette: C.ThemePalette | None = None,
        text_width: int = TASK_TEXT_WIDTH,
    ) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=10)
        self.task = task
        self.accent = accent
        self.on_toggle = on_toggle
        self.on_delete = on_delete
        self.on_edit = on_edit
        self.palette = palette or C.solid_palette()
        self.text_width = max(C.MIN_TASK_WIDTH, int(text_width))
        self._editing = False
        self._hover = False
        self._hover_after: str | None = None

        text_font = ui_font(13, overstrike=task.done)
        display = wrap_two_lines(task.text, text_font, self.text_width, 2)
        one_line = line_count(display) <= 1
        self.desired_height = C.TASK_ROW_ONE_LINE if one_line else C.TASK_ROW_TWO_LINE
        self.configure(height=self.desired_height)
        self.grid_propagate(False)
        self.grid_columnconfigure(1, weight=1)

        self._check = ctk.CTkButton(
            self,
            text="",
            image=get_icon("check", C.TEXT_ON_ACCENT, 11, 2.4) if task.done else None,
            width=22,
            height=22,
            corner_radius=11,
            border_width=1,
            border_color=accent if task.done else self.palette.border_strong,
            fg_color=accent if task.done else self.palette.card_bg,
            hover_color=accent if task.done else self.palette.surface_active,
            border_spacing=3,
            command=lambda: self.on_toggle(self.task.id),
        )
        self._check.grid(row=0, column=0, padx=(3, 8), pady=(4, 4), sticky="n")
        set_cursor(self._check, "hand2")
        self._check.bind("<Enter>", self._on_enter)
        self._check.bind("<Leave>", self._on_leave)

        self._label = ctk.CTkLabel(
            self,
            text=display,
            font=text_font,
            text_color=C.TEXT_MUTED if task.done else C.TEXT,
            anchor="w",
            justify="left",
            fg_color="transparent",
            height=self.desired_height - 4,
        )
        self._label.grid(row=0, column=1, sticky="ew", pady=(5, 5))
        self._label.configure(wraplength=0)
        set_cursor(self._label, "arrow")
        self._label.bind("<Double-Button-1>", self._start_edit)
        self._label.bind("<Enter>", self._on_enter)
        self._label.bind("<Leave>", self._on_leave)

        self._delete_holder = ctk.CTkFrame(
            self,
            width=24,
            height=24,
            fg_color="transparent",
            corner_radius=8,
        )
        self._delete_holder.grid(row=0, column=2, padx=(2, 3), pady=(4, 4), sticky="n")
        self._delete_holder.pack_propagate(False)
        self._delete_holder.grid_propagate(False)

        self._delete = ctk.CTkButton(
            self._delete_holder,
            text="",
            image=get_icon("close", C.TEXT_MUTED, 13, 2.0),
            width=24,
            height=24,
            corner_radius=8,
            fg_color="transparent",
            hover_color=C.DANGER_HOVER,
            command=lambda: self.on_delete(self.task.id),
        )
        self._delete.bind("<Enter>", self._on_delete_enter)
        self._delete.bind("<Leave>", self._on_delete_leave)
        set_cursor(self._delete, "hand2")

        for widget in (self, self._label, self._check, self._delete_holder, self._delete):
            bind_widget(widget, "<Enter>", self._on_enter)
            bind_widget(widget, "<Leave>", self._on_leave)

    # ------------------------------------------------------------------ hover
    def _on_enter(self, _event: Any = None) -> None:
        if self._hover_after is not None:
            try:
                self.after_cancel(self._hover_after)
            except Exception:
                pass
            self._hover_after = None
        if self._editing:
            return
        self._hover = True
        try:
            self.configure(fg_color=self.palette.surface)
            self._delete.pack(expand=True)
        except Exception:
            pass

    def _on_leave(self, _event: Any = None) -> None:
        if self._hover_after is not None:
            try:
                self.after_cancel(self._hover_after)
            except Exception:
                pass
        try:
            self._hover_after = self.after(40, self._hide_if_outside)
        except Exception:
            self._hover_after = None

    def _hide_if_outside(self) -> None:
        self._hover_after = None
        try:
            if self.winfo_exists() and point_over(self):
                return
            self._set_hover(False)
        except Exception:
            pass

    def _set_hover(self, hovering: bool) -> None:
        if self._editing:
            hovering = False
        self._hover = hovering
        try:
            self.configure(fg_color=self.palette.surface if hovering else "transparent")
        except Exception:
            pass
        try:
            if hovering:
                self._delete.pack(expand=True)
            else:
                self._delete.pack_forget()
        except Exception:
            pass

    def _on_delete_enter(self, _event: Any = None) -> None:
        try:
            self._delete.configure(image=get_icon("close", C.DANGER, 13, 2.0))
        except Exception:
            pass

    def _on_delete_leave(self, _event: Any = None) -> None:
        try:
            self._delete.configure(image=get_icon("close", C.TEXT_MUTED, 13, 2.0))
        except Exception:
            pass

    # ------------------------------------------------------------------ edit
    def _start_edit(self, _event: Any = None) -> str:
        if self._editing:
            return "break"
        self._editing = True
        self._set_hover(False)
        self._label.grid_remove()
        self._edit = ctk.CTkEntry(
            self,
            height=30,
            fg_color=self.palette.surface_hover,
            border_width=1,
            border_color=self.accent,
            corner_radius=8,
            font=ui_font(13),
            text_color=C.TEXT,
        )
        self._edit.grid(row=0, column=1, sticky="ew", pady=(4, 4), padx=(0, 2))
        self._edit.insert(0, self.task.text)
        self._edit.select_range(0, "end")
        self._edit.bind("<Return>", self._commit_edit)
        self._edit.bind("<KP_Enter>", self._commit_edit)
        self._edit.bind("<Escape>", self._cancel_edit)
        self._edit.bind("<FocusOut>", self._focus_out)
        self._edit.after(20, self._focus_edit)
        return "break"

    def _focus_edit(self) -> None:
        try:
            self._edit.focus_set()
            self._edit.icursor("end")
        except Exception:
            pass

    def _focus_out(self, _event: Any = None) -> None:
        if self._editing:
            self._commit_edit()

    def _cancel_edit(self, _event: Any = None) -> str:
        if not self._editing:
            return "break"
        self._editing = False
        try:
            self._edit.destroy()
        except Exception:
            pass
        try:
            self._label.grid()
        except Exception:
            pass
        return "break"

    def _commit_edit(self, _event: Any = None) -> str:
        if not self._editing:
            return "break"
        try:
            new_text = self._edit.get().strip()
        except Exception:
            new_text = self.task.text
        self._editing = False
        try:
            self._edit.destroy()
        except Exception:
            pass
        try:
            self._label.grid()
        except Exception:
            pass
        if new_text and new_text != self.task.text:
            try:
                self.on_edit(self.task.id, new_text)
            except Exception:
                log.exception("Could not save task edit")
        return "break"


# --------------------------------------------------------------------- task list
class TaskList(ctk.CTkScrollableFrame):
    def __init__(
        self,
        master: Any,
        *,
        on_toggle: Callable[[str], None],
        on_delete: Callable[[str], None],
        on_edit: Callable[[str, str], bool],
        palette: C.ThemePalette | None = None,
        text_width: int = TASK_TEXT_WIDTH,
    ) -> None:
        self.palette = palette or C.solid_palette()
        self.text_width = max(C.MIN_TASK_WIDTH, int(text_width))
        super().__init__(
            master,
            width=1,
            height=1,
            corner_radius=0,
            border_width=0,
            fg_color=self.palette.card_bg,
            scrollbar_fg_color=self.palette.scrollbar_bg,
            scrollbar_button_color=self.palette.scrollbar_button,
            scrollbar_button_hover_color=self.palette.scrollbar_button_hover,
        )
        self.on_toggle = on_toggle
        self.on_delete = on_delete
        self.on_edit = on_edit
        self.rows: list[TaskRow] = []
        self._scrollbar_needed = False
        self.max_height = C.TASK_AREA_MAX_HEIGHT

    def set_palette(self, palette: C.ThemePalette) -> None:
        self.palette = palette
        try:
            self.configure(
                fg_color=palette.card_bg,
                scrollbar_fg_color=palette.scrollbar_bg,
                scrollbar_button_color=palette.scrollbar_button,
                scrollbar_button_hover_color=palette.scrollbar_button_hover,
            )
        except Exception:
            log.debug("Could not update task list palette", exc_info=True)

    def set_text_width(self, width: int) -> None:
        self.text_width = max(C.MIN_TASK_WIDTH, int(width))

    def set_max_height(self, height: int) -> None:
        height = max(1, int(height))
        if height == self.max_height:
            return
        self.max_height = height
        content_height = sum(row.desired_height + 3 for row in self.rows)
        visible_height = min(max(1, content_height), self.max_height)
        try:
            self.configure(height=visible_height)
        except Exception:
            pass
        self._scrollbar_needed = content_height > self.max_height
        self._sync_scrollbar()

    def rebuild(self, tasks: Sequence[Task], accent: str, *, scroll_to_bottom: bool = False) -> None:
        old_view = 0.0
        try:
            old_view = float(self._parent_canvas.yview()[0])
        except Exception:
            old_view = 0.0

        for row in self.rows:
            try:
                row.destroy()
            except Exception:
                pass
        self.rows.clear()

        for task in tasks:
            row = TaskRow(
                self,
                task,
                accent,
                on_toggle=self.on_toggle,
                on_delete=self.on_delete,
                on_edit=self.on_edit,
                palette=self.palette,
                text_width=self.text_width,
            )
            row.pack(fill="x", pady=(0, 3))
            self.rows.append(row)

        content_height = sum(row.desired_height + 3 for row in self.rows)
        visible_height = min(max(1, content_height), self.max_height)
        try:
            self.configure(height=visible_height)
        except Exception:
            pass
        self._scrollbar_needed = content_height > self.max_height
        self._sync_scrollbar()
        self.after(0, lambda: self._restore_view(old_view, scroll_to_bottom))

    def _sync_scrollbar(self) -> None:
        scrollbar = getattr(self, "_scrollbar", None)
        if scrollbar is None:
            return
        try:
            if self._scrollbar_needed:
                scrollbar.grid()
            else:
                scrollbar.grid_remove()
        except Exception:
            log.debug("Could not toggle task scrollbar", exc_info=True)

    def _restore_view(self, fraction: float, scroll_to_bottom: bool) -> None:
        try:
            self._parent_canvas.update_idletasks()
            if scroll_to_bottom and self._scrollbar_needed:
                self._parent_canvas.yview_moveto(1.0)
            else:
                self._parent_canvas.yview_moveto(fraction)
        except Exception:
            pass

    @property
    def scrollbar_visible(self) -> bool:
        return self._scrollbar_needed


# --------------------------------------------------------------------- add bar
class AddTaskBar(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        accent: str,
        on_add: Callable[[str], bool],
        palette: C.ThemePalette | None = None,
    ) -> None:
        self.palette = palette or C.solid_palette()
        super().__init__(
            master,
            fg_color=self.palette.surface,
            border_width=1,
            border_color=self.palette.border,
            corner_radius=12,
        )
        self.accent = accent
        self.on_add = on_add
        self._focused = False
        self.grid_columnconfigure(1, weight=1)

        self._plus = ctk.CTkButton(
            self,
            text="",
            image=get_icon("plus", C.TEXT_MUTED, 15, 1.8),
            width=26,
            height=26,
            corner_radius=8,
            fg_color="transparent",
            hover_color=self.palette.surface_hover,
            command=self.submit,
        )
        self._plus.grid(row=0, column=0, padx=(6, 2), pady=6)
        set_cursor(self._plus, "hand2")

        self.entry = ctk.CTkEntry(
            self,
            placeholder_text="添加待办，回车确认",
            height=32,
            fg_color=self.palette.surface,
            border_width=0,
            corner_radius=0,
            text_color=C.TEXT,
            placeholder_text_color=C.TEXT_DIM,
            font=ui_font(12),
        )
        self.entry.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=4)
        self.entry.bind("<Return>", self._on_return)
        self.entry.bind("<KP_Enter>", self._on_return)
        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Escape>", self._on_escape)

    def _on_return(self, _event: Any = None) -> str:
        self.submit()
        return "break"

    def _on_escape(self, _event: Any = None) -> str:
        if not self.entry.get().strip():
            try:
                self.winfo_toplevel().focus_set()
            except Exception:
                pass
        else:
            self.entry.delete(0, "end")
        return "break"

    def submit(self) -> bool:
        text = self.entry.get().strip()
        if not text:
            self.entry.focus_set()
            return False
        if self.on_add(text):
            self.entry.delete(0, "end")
            self.entry.focus_set()
            return True
        self.entry.focus_set()
        return False

    def _on_focus_in(self, _event: Any = None) -> None:
        self._focused = True
        try:
            self.configure(border_color=self.accent)
        except Exception:
            pass

    def _on_focus_out(self, _event: Any = None) -> None:
        self._focused = False
        try:
            self.configure(border_color=self.palette.border)
        except Exception:
            pass

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        if self._focused:
            try:
                self.configure(border_color=accent)
            except Exception:
                pass

    def set_palette(self, palette: C.ThemePalette) -> None:
        self.palette = palette
        try:
            self.configure(
                fg_color=palette.surface,
                border_color=palette.border if not self._focused else self.accent,
            )
            self.entry.configure(fg_color=palette.surface)
            self._plus.configure(hover_color=palette.surface_hover)
        except Exception:
            log.debug("Could not update add bar palette", exc_info=True)

    def focus_entry(self) -> None:
        try:
            self.entry.focus_set()
        except Exception:
            pass

    def clear(self) -> None:
        try:
            self.entry.delete(0, "end")
        except Exception:
            pass

    def set_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        try:
            self.entry.configure(state=state)
            self._plus.configure(state=state)
        except Exception:
            pass


# --------------------------------------------------------------------- empty state
class EmptyState(ctk.CTkFrame):
    def __init__(self, master: Any, accent: str, on_click: Callable[[], Any]) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.on_click = on_click
        self.grid_columnconfigure(0, weight=1)

        art = ctk.CTkLabel(self, text="", image=get_empty_art(accent, 60), fg_color="transparent")
        art.grid(row=0, column=0, pady=(6, 2))
        title = ctk.CTkLabel(
            self,
            text="还没有待办",
            font=ui_font(13, "bold"),
            text_color=C.TEXT,
            fg_color="transparent",
        )
        title.grid(row=1, column=0, pady=(0, 2))
        subtitle = ctk.CTkLabel(
            self,
            text="把第一件小事写下来吧",
            font=ui_font(11),
            text_color=C.TEXT_DIM,
            fg_color="transparent",
        )
        subtitle.grid(row=2, column=0, pady=(0, 8))

        for widget in (self, art, title, subtitle):
            bind_widget(widget, "<Button-1>", lambda _e=None: self.on_click())
            set_cursor(widget, "hand2")


# --------------------------------------------------------------------- tip strip
class OnboardingTip(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        on_dismiss: Callable[[], Any],
        palette: C.ThemePalette | None = None,
    ) -> None:
        self.palette = palette or C.solid_palette()
        super().__init__(
            master,
            fg_color=self.palette.surface,
            border_width=1,
            border_color=self.palette.border,
            corner_radius=10,
        )
        self.grid_columnconfigure(1, weight=1)
        icon = ctk.CTkLabel(
            self,
            text="",
            image=get_icon("sparkle", C.ACCENTS[3].color, 15, 1.5),
            fg_color="transparent",
            width=20,
        )
        icon.grid(row=0, column=0, padx=(9, 5), pady=8, sticky="n")
        text = ctk.CTkLabel(
            self,
            text="拖动标题移动，靠近自动拼合；Alt 拖动可自由摆放或拆出组合。",
            font=ui_font(10),
            text_color=C.TEXT_MUTED,
            anchor="w",
            justify="left",
            wraplength=258,
            fg_color="transparent",
        )
        text.grid(row=0, column=1, padx=(0, 4), pady=8, sticky="ew")
        close = IconButton(
            self,
            get_icon("close", C.TEXT_DIM, 11, 1.8),
            on_dismiss,
            width=22,
            height=22,
            corner_radius=7,
            hover_color=self.palette.surface_hover,
        )
        close.grid(row=0, column=2, padx=(0, 5), pady=6, sticky="n")
        self._close = close

    def set_palette(self, palette: C.ThemePalette) -> None:
        self.palette = palette
        try:
            self.configure(fg_color=palette.surface, border_color=palette.border)
            self._close.configure(hover_color=palette.surface_hover)
        except Exception:
            log.debug("Could not update onboarding tip palette", exc_info=True)


# --------------------------------------------------------------------- footer
class CardFooter(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        accent: str,
        palette: C.ThemePalette | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.palette = palette or C.solid_palette()
        self.grid_columnconfigure(1, weight=1)
        self._count = ctk.CTkLabel(
            self,
            text="",
            font=ui_font(11),
            text_color=C.TEXT_MUTED,
            anchor="w",
            fg_color="transparent",
        )
        self._count.grid(row=0, column=0, sticky="w")
        self._remaining = ctk.CTkLabel(
            self,
            text="",
            font=ui_font(10),
            text_color=C.TEXT_DIM,
            anchor="e",
            fg_color="transparent",
        )
        self._remaining.grid(row=0, column=1, sticky="e")
        self.progress = ctk.CTkProgressBar(
            self,
            height=4,
            corner_radius=999,
            fg_color=self.palette.surface,
            progress_color=accent,
            border_width=0,
        )
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        self.progress.set(0)
        self.update_for(0, 0, accent)

    def update_for(self, completed: int, total: int, accent: str) -> None:
        if total <= 0:
            self._count.configure(text="还没有事项")
            self._remaining.configure(text="")
            self.progress.set(0)
        else:
            remaining = max(0, total - completed)
            self._count.configure(text=f"{completed} / {total} 已完成")
            if remaining == 0:
                self._remaining.configure(text="全部完成 ✓", text_color=accent)
            else:
                self._remaining.configure(text=f"还剩 {remaining} 项", text_color=C.TEXT_DIM)
            self.progress.set(completed / total if total else 0)
        try:
            self.progress.configure(progress_color=accent)
        except Exception:
            pass

    def set_palette(self, palette: C.ThemePalette) -> None:
        self.palette = palette
        try:
            self.progress.configure(fg_color=palette.surface)
        except Exception:
            log.debug("Could not update footer palette", exc_info=True)


# --------------------------------------------------------------------- header
class CardHeader(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        card: Card,
        accent: str,
        *,
        on_toggle_pin: Callable[[], None],
        on_toggle_collapse: Callable[[], None],
        on_menu: Callable[[Any], None],
        on_rename: Callable[[str], None],
        on_drag_start: Callable[[Any], None],
        on_drag_motion: Callable[[Any], None],
        on_drag_end: Callable[[Any], None],
        palette: C.ThemePalette | None = None,
        title_width: int = TITLE_TEXT_WIDTH,
    ) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.card = card
        self.accent = accent
        self.palette = palette or C.solid_palette()
        self.title_width = max(C.MIN_TITLE_WIDTH, int(title_width))
        self.on_toggle_pin = on_toggle_pin
        self.on_toggle_collapse = on_toggle_collapse
        self.on_menu = on_menu
        self.on_rename = on_rename
        self.on_drag_start = on_drag_start
        self.on_drag_motion = on_drag_motion
        self.on_drag_end = on_drag_end
        self._renaming = False
        self._rename_entry: ctk.CTkEntry | None = None
        self._name_before_edit = card.title
        self._meta_override: str | None = None
        self._meta_accent = False

        self.grid_columnconfigure(0, weight=1)
        self._left = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._left.grid(row=0, column=0, sticky="nsew")
        self._controls = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._controls.grid(row=0, column=1, sticky="ne", padx=(2, 0))

        self._title_line = ctk.CTkFrame(self._left, fg_color="transparent", corner_radius=0)
        self._title_line.pack(fill="x")
        self._dot = ctk.CTkLabel(
            self._title_line,
            text="●",
            font=ui_font(9),
            text_color=accent,
            width=10,
            fg_color="transparent",
        )
        self._dot.pack(side="left", padx=(0, 5), pady=(7, 0))
        self._title = ctk.CTkLabel(
            self._title_line,
            text="",
            font=ui_font(17, "bold"),
            text_color=C.TEXT,
            anchor="w",
            justify="left",
            fg_color="transparent",
        )
        self._title.pack(side="left", fill="x", expand=True)
        self._meta = ctk.CTkLabel(
            self._left,
            text="",
            font=ui_font(11),
            text_color=C.TEXT_MUTED,
            anchor="w",
            justify="left",
            fg_color="transparent",
        )
        self._meta.pack(fill="x", padx=(15, 0), pady=(1, 0))

        self._pin_btn = IconButton(
            self._controls,
            get_icon("pin", accent, 15, 1.7, filled=card.pinned),
            on_toggle_pin,
            hover_color=self.palette.surface,
        )
        self._pin_btn.grid(row=0, column=0, padx=2)
        self._collapse_btn = IconButton(
            self._controls,
            get_icon("chevron_down" if card.collapsed else "chevron_up", C.TEXT_MUTED, 15, 1.8),
            on_toggle_collapse,
            hover_color=self.palette.surface,
        )
        self._collapse_btn.grid(row=0, column=1, padx=2)
        self._menu_btn = IconButton(
            self._controls,
            get_icon("more", C.TEXT_MUTED, 16, 1.7),
            lambda: on_menu(self._menu_btn),
            hover_color=self.palette.surface,
        )
        self._menu_btn.grid(row=0, column=2, padx=2)

        for widget in (
            self,
            self._left,
            self._title_line,
            self._dot,
            self._title,
            self._meta,
        ):
            for sequence, callback in (
                ("<ButtonPress-1>", self._start_drag),
                ("<B1-Motion>", self._motion_drag),
                ("<ButtonRelease-1>", self._end_drag),
            ):
                bind_widget(widget, sequence, callback)
            set_cursor(widget, "fleur")

        self._title.bind("<Double-Button-1>", self.begin_rename)
        self.set_state(card, accent)

    # ------------------------------------------------------------------ state
    def set_state(self, card: Card, accent: str, meta_override: str | None = None) -> None:
        self.card = card
        self.accent = accent
        if meta_override is not None:
            self._meta_override = meta_override
            self._meta_accent = False
        if not self._renaming:
            self._title.configure(text=ellipsize(card.title, ui_font(17, "bold"), self.title_width))
        self._dot.configure(text_color=accent)
        self._pin_btn.configure(
            image=get_icon("pin", accent, 15, 1.7, filled=card.pinned)
        )
        self._collapse_btn.configure(
            image=get_icon(
                "chevron_down" if card.collapsed else "chevron_up",
                C.TEXT_MUTED,
                15,
                1.8,
            )
        )
        self._set_default_meta(card)

    def _default_meta(self, card: Card) -> str:
        if card.total_count == 0:
            return "准备开始"
        if card.completed_count == card.total_count:
            return f"{card.total_count} 项 · 全部完成"
        return f"{card.remaining_count} 项未完成 · {card.completed_count}/{card.total_count} 已完成"

    def _set_default_meta(self, card: Card) -> None:
        if self._meta_override is not None:
            self._meta.configure(
                text=self._meta_override,
                text_color=self.accent if self._meta_accent else C.TEXT_MUTED,
            )
            return
        self._meta.configure(text=self._default_meta(card), text_color=C.TEXT_MUTED)

    def set_meta(self, text: str | None, accent: bool = True) -> None:
        self._meta_override = text
        self._meta_accent = accent
        if text is None:
            self._set_default_meta(self.card)
        else:
            self._meta.configure(text=text, text_color=self.accent if accent else C.TEXT_MUTED)

    def set_accent(self, accent: str, card: Card | None = None) -> None:
        self.accent = accent
        self.set_state(card or self.card, accent)

    def set_title_width(self, width: int) -> None:
        self.title_width = max(C.MIN_TITLE_WIDTH, int(width))
        if not self._renaming:
            self._title.configure(
                text=ellipsize(self.card.title, ui_font(17, "bold"), self.title_width)
            )

    def set_palette(self, palette: C.ThemePalette) -> None:
        self.palette = palette
        for button in (self._pin_btn, self._collapse_btn, self._menu_btn):
            try:
                button.configure(hover_color=palette.surface)
            except Exception:
                pass

    # ------------------------------------------------------------------ drag
    def _start_drag(self, event: Any) -> None:
        if not self._renaming:
            self.on_drag_start(event)

    def _motion_drag(self, event: Any) -> None:
        if not self._renaming:
            self.on_drag_motion(event)

    def _end_drag(self, event: Any) -> None:
        if not self._renaming:
            self.on_drag_end(event)

    # ------------------------------------------------------------------ rename
    def begin_rename(self, _event: Any = None) -> str:
        if self._renaming:
            return "break"
        self._renaming = True
        self._name_before_edit = self.card.title
        try:
            self._title.pack_forget()
        except Exception:
            pass
        entry = ctk.CTkEntry(
            self._title_line,
            height=28,
            fg_color=self.palette.surface,
            border_width=1,
            border_color=self.accent,
            corner_radius=7,
            font=ui_font(16, "bold"),
            text_color=C.TEXT,
        )
        entry.pack(side="left", fill="x", expand=True, pady=(1, 0))
        entry.insert(0, self._name_before_edit)
        entry.select_range(0, "end")
        entry.bind("<Return>", self._commit_rename)
        entry.bind("<KP_Enter>", self._commit_rename)
        entry.bind("<Escape>", self._cancel_rename)
        entry.bind("<FocusOut>", self._rename_focus_out)
        self._rename_entry = entry
        entry.after(20, self._focus_rename)
        return "break"

    def _focus_rename(self) -> None:
        try:
            if self._rename_entry is not None:
                self._rename_entry.focus_set()
                self._rename_entry.icursor("end")
        except Exception:
            pass

    def _finish_rename(self) -> None:
        self._renaming = False
        entry = self._rename_entry
        self._rename_entry = None
        if entry is not None:
            try:
                entry.destroy()
            except Exception:
                pass
        try:
            self._title.pack(side="left", fill="x", expand=True)
        except Exception:
            pass

    def _commit_rename(self, _event: Any = None) -> str:
        if not self._renaming:
            return "break"
        entry = self._rename_entry
        text = entry.get().strip() if entry is not None else self.card.title
        self._finish_rename()
        if text and text != self.card.title:
            try:
                self.on_rename(text)
            except Exception:
                log.exception("Rename failed")
        return "break"

    def _cancel_rename(self, _event: Any = None) -> str:
        self._finish_rename()
        return "break"

    def _rename_focus_out(self, _event: Any = None) -> None:
        if self._renaming:
            self._commit_rename()

    def is_renaming(self) -> bool:
        return self._renaming


# --------------------------------------------------------------------- menu
class CardMenu:
    """A small borderless popup menu bound to one card."""

    WIDTH = 224

    def __init__(
        self,
        master: Any,
        card: Card,
        accent: str,
        *,
        on_new: Callable[[], None],
        on_rename: Callable[[], None],
        on_collapse: Callable[[], None],
        on_color: Callable[[str], None],
        on_clear_completed: Callable[[], None],
        on_delete: Callable[[], None],
        on_quit: Callable[[], None],
        on_appearance: Callable[[], None] | None = None,
        appearance: str = C.DEFAULT_APPEARANCE,
        palette: C.ThemePalette | None = None,
        screen: Any = None,
        on_closed: Callable[[], None] | None = None,
        on_ungroup: Callable[[], None] | None = None,
        group_size: int = 0,
        on_autostart: Callable[[], None] | None = None,
        autostart_enabled: bool = False,
        on_glass_level: Callable[[], None] | None = None,
        glass_level: int = C.DEFAULT_GLASS_LEVEL,
        on_reset_size: Callable[[], None] | None = None,
        manual_size: bool = False,
    ) -> None:
        self.card = card
        self.accent = accent
        self.master = master
        self.screen = screen
        self.on_closed = on_closed
        self.on_new = on_new
        self.on_rename = on_rename
        self.on_collapse = on_collapse
        self.on_color = on_color
        self.on_clear_completed = on_clear_completed
        self.on_delete = on_delete
        self.on_quit = on_quit
        self.on_appearance = on_appearance
        self.on_ungroup = on_ungroup
        self.group_size = max(0, int(group_size))
        self.on_autostart = on_autostart
        self.autostart_enabled = bool(autostart_enabled)
        self.on_glass_level = on_glass_level
        self.glass_level = max(0, min(2, int(glass_level)))
        self.on_reset_size = on_reset_size
        self.manual_size = bool(manual_size)
        self.appearance = appearance if appearance in C.APPEARANCES else C.DEFAULT_APPEARANCE
        self.palette = palette or C.solid_palette()
        self.top: ctk.CTkToplevel | None = None
        self._color_buttons: dict[str, ctk.CTkButton] = {}
        self._collapse_btn: ctk.CTkButton | None = None
        self._clear_btn: ctk.CTkButton | None = None
        self._raise_after: str | None = None
        self._watch_after: str | None = None
        self._mouse_was_down = False
        self._closed = False

        self._build()
        self._refresh_state()

    def _build(self) -> None:
        top = ctk.CTkToplevel(master=self.master)
        top.withdraw()
        try:
            top.overrideredirect(True)
        except Exception:
            pass
        try:
            top.attributes("-topmost", True)
        except Exception:
            pass
        try:
            top.configure(fg_color=C.WINDOW_KEY)
            top.wm_attributes("-transparentcolor", C.WINDOW_KEY)
        except Exception:
            try:
                top.configure(fg_color=self.palette.menu_bg)
            except Exception:
                pass
        self.top = top

        outer = ctk.CTkFrame(
            top,
            fg_color=self.palette.menu_bg,
            border_width=1,
            border_color=self.palette.menu_border,
            corner_radius=15,
            width=self.WIDTH,
        )
        outer.pack(fill="both", expand=True)
        body = ctk.CTkFrame(outer, fg_color="transparent", corner_radius=0)
        body.pack(fill="both", expand=True, padx=7, pady=7)

        self._item(
            body,
            "新建卡片",
            "new_card",
            lambda: self._run(self.on_new),
            shortcut="Ctrl+N",
        )
        self._item(body, "重命名", "edit", lambda: self._run(self.on_rename))
        self._collapse_btn = self._item(
            body,
            "折叠卡片",
            "chevron_up",
            lambda: self._run(self.on_collapse),
        )

        sep = ctk.CTkFrame(body, fg_color=self.palette.menu_separator, height=1, corner_radius=0)
        sep.pack(fill="x", padx=7, pady=5)

        color_title = ctk.CTkLabel(
            body,
            text="  卡片颜色",
            font=ui_font(10, "bold"),
            text_color=C.TEXT_DIM,
            anchor="w",
            fg_color="transparent",
        )
        color_title.pack(fill="x", padx=6, pady=(2, 5))
        color_row = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        color_row.pack(fill="x", padx=8, pady=(0, 3))
        for accent in C.ACCENTS:
            btn = ctk.CTkButton(
                color_row,
                text="",
                width=23,
                height=23,
                corner_radius=12,
                fg_color=accent.color,
                hover_color=accent.color,
                border_width=1,
                border_color=self.palette.menu_bg,
                command=lambda key=accent.key: self._run(lambda: self.on_color(key)),
            )
            btn.pack(side="left", expand=True, padx=2)
            self._color_buttons[accent.key] = btn

        if self.on_appearance is not None:
            appearance_text = (
                "切换为深色雾面背景"
                if self.appearance == "glass"
                else "切换为玻璃彩色背景"
            )
            self._appearance_btn = self._item(
                body,
                appearance_text,
                "sparkle",
                lambda: self._run(self.on_appearance),
            )

        if self.group_size > 1 and self.on_ungroup is not None:
            self._item(body, "拆分组合", "grip", lambda: self._run(self.on_ungroup))

        if self.on_glass_level is not None and self.appearance == "glass":
            level_label = C.GLASS_LEVEL_LABELS[self.glass_level]
            self._item(
                body,
                f"玻璃质感：{level_label}",
                "sparkle",
                lambda: self._run(self.on_glass_level),
            )

        if self.on_autostart is not None:
            state_text = "已开启" if self.autostart_enabled else "未开启"
            self._item(
                body,
                f"开机自启：{state_text}",
                "power",
                lambda: self._run(self.on_autostart),
            )

        if self.on_reset_size is not None and self.manual_size:
            self._item(
                body,
                "重置卡片大小",
                "grip",
                lambda: self._run(self.on_reset_size),
            )

        sep2 = ctk.CTkFrame(body, fg_color=self.palette.menu_separator, height=1, corner_radius=0)
        sep2.pack(fill="x", padx=7, pady=6)

        self._clear_btn = self._item(
            body,
            "清除已完成",
            "check_circle",
            lambda: self._run(self.on_clear_completed),
        )
        self._item(
            body,
            "删除这张卡片",
            "trash",
            lambda: self._run(self.on_delete),
            danger=True,
        )

        sep3 = ctk.CTkFrame(body, fg_color=self.palette.menu_separator, height=1, corner_radius=0)
        sep3.pack(fill="x", padx=7, pady=6)
        self._item(body, "退出悬浮待办", "power", lambda: self._run(self.on_quit))

        hint = ctk.CTkLabel(
            body,
            text="双击标题也可以重命名",
            font=ui_font(9),
            text_color=C.TEXT_DIM,
            anchor="center",
            fg_color="transparent",
        )
        hint.pack(fill="x", pady=(7, 1))

        top.bind("<Escape>", lambda _e: self.close())
        top.protocol("WM_DELETE_WINDOW", self.close)

    def _item(
        self,
        parent: Any,
        text: str,
        icon_name: str,
        command: Callable[[], None],
        *,
        danger: bool = False,
        shortcut: str = "",
    ) -> ctk.CTkButton:
        label = text if not shortcut else f"{text}          {shortcut}"
        color = C.DANGER if danger else C.TEXT
        btn = ctk.CTkButton(
            parent,
            text=label,
            image=get_icon(icon_name, color, 15, 1.7),
            compound="left",
            anchor="w",
            height=35,
            corner_radius=9,
            border_width=0,
            fg_color="transparent",
            hover_color=C.DANGER_HOVER if danger else self.palette.menu_hover,
            text_color=color,
            font=ui_font(11),
            command=command,
        )
        btn.pack(fill="x", pady=1)
        set_cursor(btn, "hand2")
        return btn

    def _refresh_state(self) -> None:
        if self._collapse_btn is not None:
            self._collapse_btn.configure(
                text="展开卡片" if self.card.collapsed else "折叠卡片",
                image=get_icon(
                    "chevron_down" if self.card.collapsed else "chevron_up",
                    C.TEXT,
                    15,
                    1.7,
                ),
            )
        if self._clear_btn is not None:
            has_done = any(task.done for task in self.card.tasks)
            self._clear_btn.configure(
                state="normal" if has_done else "disabled",
                text_color=C.TEXT if has_done else C.TEXT_DIM,
                image=get_icon("check_circle", C.TEXT if has_done else C.TEXT_DIM, 15, 1.7),
            )
        for key, btn in self._color_buttons.items():
            selected = key == self.card.accent
            btn.configure(
                text="✓" if selected else "",
                text_color=C.TEXT_ON_ACCENT,
                font=ui_font(10, "bold"),
                border_color=C.TEXT if selected else self.palette.menu_bg,
                border_width=2 if selected else 1,
            )

    def show(self, anchor: Any) -> None:
        top = self.top
        if top is None:
            return
        try:
            top.update_idletasks()
            scale = ctk.ScalingTracker.get_window_scaling(top)
            req_height = top.winfo_reqheight()
            logical_height = max(1, int(round(req_height / scale))) if req_height > 1 else 300
            physical_width = int(round(self.WIDTH * scale))
            physical_height = int(round(logical_height * scale))
            ax = anchor.winfo_rootx()
            ay = anchor.winfo_rooty()
            aw = max(1, anchor.winfo_width())
            ah = max(1, anchor.winfo_height())
        except Exception:
            log.exception("Could not measure menu")
            self.close()
            return
        x = ax + aw - physical_width
        y = ay + ah + 7
        try:
            if self.screen is not None:
                left, top_edge, right, bottom = self.screen.workarea_for_rect(
                    (ax, ay, ax + aw, ay + ah)
                )
            else:
                left, top_edge = 0, 0
                right = top.winfo_screenwidth()
                bottom = top.winfo_screenheight()
            inset = 8
            x = max(left + inset, min(x, right - physical_width - inset))
            if y + physical_height > bottom - inset:
                y = max(top_edge + inset, ay - physical_height - 7)
            else:
                y = max(top_edge + inset, y)
        except Exception:
            pass
        try:
            top.geometry(f"{self.WIDTH}x{logical_height}+{x}+{y}")
            top.deiconify()
            top.lift()
            top.focus_force()
            raise_topmost(top)
            self._raise_after = top.after(70, self._raise_again)
            self._mouse_was_down = left_button_down()
            self._watch_after = top.after(60, self._watch_pointer)
        except Exception:
            log.exception("Menu popup failed")
            self.close()

    def _raise_again(self) -> None:
        self._raise_after = None
        if self._closed or self.top is None:
            return
        try:
            raise_topmost(self.top)
        except Exception:
            pass

    def _watch_pointer(self) -> None:
        self._watch_after = None
        if self._closed or self.top is None:
            return
        try:
            down = left_button_down()
            new_press = down and not self._mouse_was_down
            self._mouse_was_down = down
            if new_press and not self._pointer_inside():
                self.close()
                return
        except Exception:
            log.debug("Menu outside-click check failed", exc_info=True)
        try:
            # Poll while the menu is open.  Physical clicks last longer than a
            # 20 ms sample on Windows, and this is much cheaper than a global
            # mouse hook.  Edge detection ignores the press that opened the menu.
            self._watch_after = self.top.after(20, self._watch_pointer)
        except Exception:
            self._watch_after = None

    def _pointer_inside(self) -> bool:
        top = self.top
        if top is None:
            return False
        try:
            x, y = top.winfo_pointerxy()
            left = top.winfo_rootx()
            top_edge = top.winfo_rooty()
            right = left + top.winfo_width()
            bottom = top_edge + top.winfo_height()
            return left <= x < right and top_edge <= y < bottom
        except Exception:
            return False

    def _cancel_watchers(self) -> None:
        top = self.top
        for attribute in ("_raise_after", "_watch_after"):
            identifier = getattr(self, attribute)
            setattr(self, attribute, None)
            if identifier is None:
                continue
            try:
                if top is not None:
                    top.after_cancel(identifier)
            except Exception:
                pass

    def _run(self, callback: Callable[[], None]) -> None:
        if self._closed:
            return
        self.close()
        try:
            callback()
        except Exception:
            log.exception("Menu action failed")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._cancel_watchers()
        top = self.top
        if top is not None:
            try:
                top.withdraw()
            except Exception:
                pass
            try:
                top.destroy()
            except Exception:
                pass
        self.top = None
        if self.on_closed is not None:
            try:
                self.on_closed()
            except Exception:
                log.exception("Menu close callback failed")


