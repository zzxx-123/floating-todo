"""Application manager for the floating todo cards."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import customtkinter as ctk

from . import constants as C
from .card_window import CardWindow
from .models import AppState, Card
from .platform_win import (
    ScreenManager,
    SingleInstance,
    apply_topmost,
    confirm,
    setup_logging,
    show_error,
    show_info,
    signal_wake,
    wake_stamp,
)
from .snapping import (
    Rect,
    clamp_delta_to_workarea,
    find_group,
    group_bounds,
    rect_for,
    snap_move,
)
from .storage import LoadResult, StateStore, StorageError
from .widgets import CardMenu

log = logging.getLogger(__name__)

SHIFT_MASK = 0x0001
ALT_MASK = 0x0008 | 0x20000


@dataclass
class DragSession:
    card_id: str
    start_pointer: tuple[int, int]
    group_ids: tuple[str, ...]
    starts: dict[str, tuple[int, int]]
    sizes: dict[str, tuple[int, int]]
    bounds: Rect
    alt: bool = False
    shift: bool = False
    moved: bool = False


def data_directory() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / C.DATA_DIR_NAME


class TodoApp:
    """Owns all card windows, drag sessions, menus and persistence."""

    def __init__(
        self,
        root: ctk.CTk,
        store: StateStore,
        state: AppState,
        screen: ScreenManager,
        instance: SingleInstance | None = None,
    ) -> None:
        self.root = root
        self.store = store
        self.state = state
        self.screen = screen
        self.instance = instance
        self.windows: dict[str, CardWindow] = {}
        self._menu: CardMenu | None = None
        self._drag: DragSession | None = None
        self._save_after: str | None = None
        self._wake_after: str | None = None
        self._quitting = False
        self._shutdown_done = False
        self._saved_on_quit = False
        self._active_id: str | None = None
        self._tip_card_id: str | None = None
        self._last_save_error: str = ""

        try:
            self.scale = float(ctk.ScalingTracker.get_window_scaling(root))
        except Exception:
            self.scale = 1.0
        if self.scale <= 0:
            self.scale = 1.0
        self.snap_gap = max(1, int(round(C.CARD_GAP * self.scale)))
        self.snap_threshold = max(2, int(round(C.SNAP_THRESHOLD * self.scale)))
        self.dock_tolerance = max(1, int(round(C.DOCK_TOLERANCE * self.scale)))
        self.drag_threshold = max(3, int(round(C.DRAG_START_DISTANCE * self.scale)))
        self.margin = max(8, int(round(C.DEFAULT_MARGIN * self.scale)))
        self.new_offset = max(6, int(round(C.NEW_CARD_OFFSET * self.scale)))

        if self.state.cards and not self.state.onboarding_dismissed:
            self._tip_card_id = self.state.cards[0].id

        for card in self.state.cards:
            self._create_window(card)

        self.root.report_callback_exception = self._report_exception
        self.root.bind_all("<Control-n>", self._on_ctrl_n)
        self.root.bind_all("<Control-N>", self._on_ctrl_n)
        self._wake_marker = wake_stamp(self._wake_path())
        self._wake_cursor = self._wake_marker

    # ------------------------------------------------------------------ boot
    def start(self) -> None:
        for window in self.windows.values():
            window.show()
        if self.windows:
            if self._active_id is None:
                self._active_id = next(iter(self.windows))
        self._schedule_wake_poll()
        self._schedule_save()

    def _create_window(self, card: Card) -> None:
        window = CardWindow(
            self.root,
            card,
            self.screen,
            show_tip=(card.id == self._tip_card_id),
            on_changed=lambda card_id=card.id: self._on_card_changed(card_id),
            on_menu=lambda anchor, card_id=card.id: self._show_menu(card_id, anchor),
            on_drag_start=lambda event, card_id=card.id: self._drag_start(card_id, event),
            on_drag_motion=lambda event, card_id=card.id: self._drag_motion(card_id, event),
            on_drag_end=lambda event, card_id=card.id: self._drag_end(card_id, event),
            on_tip_dismissed=self._dismiss_onboarding,
            appearance=self.state.appearance,
        )
        self.windows[card.id] = window
        try:
            window.top.bind("<FocusIn>", lambda _e, card_id=card.id: self._set_active(card_id))
        except Exception:
            pass

    # ------------------------------------------------------------------ save
    def _schedule_save(self) -> None:
        if self._quitting:
            return
        if self._save_after is not None:
            try:
                self.root.after_cancel(self._save_after)
            except Exception:
                pass
        try:
            self._save_after = self.root.after(C.SAVE_DEBOUNCE_MS, self._save_now)
        except Exception:
            self._save_after = None

    def _sync_positions(self) -> None:
        for window in list(self.windows.values()):
            try:
                window.card.x = int(window.x)
                window.card.y = int(window.y)
            except Exception:
                pass

    def _save_now(self, *, report: bool = False) -> bool:
        self._save_after = None
        if self._quitting:
            return True
        self._sync_positions()
        try:
            self.store.save(self.state)
        except StorageError as exc:
            self._last_save_error = str(exc)
            log.warning("Save failed: %s", exc)
            if report:
                show_error(f"保存失败：{exc}\n\n请检查磁盘空间或数据目录权限。")
            return False
        self._last_save_error = ""
        return True

    # ------------------------------------------------------------------ menu
    def _show_menu(self, card_id: str, anchor: Any) -> None:
        window = self.windows.get(card_id)
        if window is None:
            return
        self._close_menu()
        self._set_active(card_id)
        window.raise_card()
        card = window.card
        try:
            menu = CardMenu(
                self.root,
                card,
                C.accent_color(card.accent),
                on_new=lambda: self._new_card(card_id),
                on_rename=window.begin_rename,
                on_collapse=window.toggle_collapse,
                on_color=lambda key: self._apply_color(card_id, key),
                on_clear_completed=window.clear_completed,
                on_delete=lambda: self._delete_card(card_id),
                on_quit=self.quit,
                screen=self.screen,
                appearance=self.state.appearance,
                palette=C.theme_palette(self.state.appearance, card.accent),
                on_appearance=self.toggle_appearance,
            )
            self._menu = menu
            menu.on_closed = lambda: self._forget_menu(menu)
            menu.show(anchor)
        except Exception:
            log.exception("Could not open card menu")
            self._close_menu()

    def _forget_menu(self, menu: CardMenu) -> None:
        if self._menu is menu:
            self._menu = None

    def _close_menu(self) -> None:
        menu = self._menu
        self._menu = None
        if menu is not None:
            try:
                menu.close()
            except Exception:
                pass

    def _apply_color(self, card_id: str, key: str) -> None:
        window = self.windows.get(card_id)
        if window is not None:
            window.set_accent(key)

    def toggle_appearance(self) -> None:
        new_appearance = (
            "glass" if self.state.appearance == "solid" else "solid"
        )
        self.state.appearance = new_appearance
        for window in self.windows.values():
            window.set_appearance(new_appearance)
        target = self.windows.get(self._last_card_id() or "")
        if target is not None:
            label = "彩色玻璃背景" if new_appearance == "glass" else "深色雾面背景"
            target.show_hint(f"已切换为{label}")
        self._schedule_save()

    # --------------------------------------------------------------- actions
    def _on_card_changed(self, card_id: str) -> None:
        self._set_active(card_id)
        self._schedule_save()

    def _set_active(self, card_id: str) -> None:
        if card_id in self.windows:
            self._active_id = card_id

    def _last_card_id(self) -> str | None:
        if self._active_id in self.windows:
            return self._active_id
        if self.state.cards:
            return self.state.cards[-1].id
        return None

    def _on_ctrl_n(self, _event: Any = None) -> str:
        self._new_card(self._last_card_id())
        return "break"

    def _new_card(self, source_id: str | None = None) -> None:
        if len(self.state.cards) >= C.MAX_CARDS:
            show_info(f"最多只能同时摆放 {C.MAX_CARDS} 张卡片。")
            return
        accent = C.ACCENTS[len(self.state.cards) % len(C.ACCENTS)].key
        card = self.state.add_card("新清单", accent)
        if card is None:
            return
        self._close_menu()
        x, y = self._new_card_position(source_id)
        card.x, card.y = x, y
        self._create_window(card)
        window = self.windows[card.id]
        window.show()
        self._active_id = card.id
        self._schedule_save()
        self.root.after(90, window.focus_input)

    def _new_card_position(self, source_id: str | None) -> tuple[int, int]:
        width = max(1, int(round(C.CARD_WIDTH * self.scale)))
        height = max(1, int(round(300 * self.scale)))
        source = self.windows.get(source_id) if source_id else None
        if source is not None:
            x, y = source.x + self.new_offset, source.y + self.new_offset
        else:
            left, top, right, _bottom = self.screen.primary_workarea()
            x, y = right - width - self.margin, top + self.margin
        left, top, right, bottom = self.screen.workarea_for_rect(
            (x, y, x + width, y + height)
        )
        if x + width > right:
            x = left + self.margin
        if y + height > bottom:
            y = top + self.margin
        return self.screen.ensure_rect_visible(x, y, width, height)

    def _delete_card(self, card_id: str) -> None:
        window = self.windows.get(card_id)
        if window is None:
            return
        self._close_menu()
        card = window.card
        last = len(self.state.cards) <= 1
        if last:
            text = (
                f"这是最后一张卡片，删除后将退出悬浮待办。\n\n"
                f"确定删除「{card.title}」和它的全部待办吗？"
            )
        else:
            text = f"确定删除「{card.title}」和它的全部待办吗？\n\n此操作无法撤销。"
        if not confirm(text, "删除卡片"):
            return
        self.state.remove_card(card_id)
        try:
            window.destroy()
        except Exception:
            log.debug("Card destroy failed", exc_info=True)
        self.windows.pop(card_id, None)
        if self._active_id == card_id:
            self._active_id = next(iter(self.windows), None)
        self._sync_positions()
        if last or not self.state.cards:
            self.quit()
            return
        try:
            self.store.save(self.state)
        except StorageError as exc:
            log.warning("Save after card delete failed: %s", exc)
            show_error(f"删除已生效，但保存失败：{exc}")
        self._schedule_save()

    def _dismiss_onboarding(self) -> None:
        self.state.onboarding_dismissed = True
        for window in self.windows.values():
            try:
                window.hide_tip()
            except Exception:
                pass
        self._schedule_save()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._close_menu()
        if self._save_after is not None:
            try:
                self.root.after_cancel(self._save_after)
            except Exception:
                pass
            self._save_after = None
        if self._wake_after is not None:
            try:
                self.root.after_cancel(self._wake_after)
            except Exception:
                pass
            self._wake_after = None
        self._sync_positions()
        saved = True
        try:
            self.store.save(self.state)
        except StorageError as exc:
            saved = False
            self._last_save_error = str(exc)
            log.error("Save on quit failed: %s", exc)
            show_error(f"退出前保存失败：{exc}")
        self._saved_on_quit = saved
        for window in list(self.windows.values()):
            try:
                window.destroy()
            except Exception:
                pass
        self.windows.clear()
        try:
            self.root.quit()
        except Exception:
            pass

    def shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self._close_menu()
        if self._wake_after is not None:
            try:
                self.root.after_cancel(self._wake_after)
            except Exception:
                pass
            self._wake_after = None
        if self._save_after is not None:
            try:
                self.root.after_cancel(self._save_after)
            except Exception:
                pass
            self._save_after = None
        if self.windows:
            self._sync_positions()
            for window in list(self.windows.values()):
                try:
                    window.destroy()
                except Exception:
                    pass
            self.windows.clear()
        if not self._saved_on_quit:
            try:
                self.store.save(self.state)
            except StorageError as exc:
                log.error("Final save failed: %s", exc)
                if not self._quitting:
                    show_error(f"保存失败：{exc}")
        self._shutdown_done = True

    # ------------------------------------------------------------ wake signal
    def _wake_path(self) -> Path:
        return self.store.data_dir / C.WAKE_FILE_NAME

    def _schedule_wake_poll(self) -> None:
        if self._quitting:
            return
        try:
            self._wake_after = self.root.after(C.WAKE_POLL_MS, self._poll_wake)
        except Exception:
            self._wake_after = None

    def _poll_wake(self) -> None:
        self._wake_after = None
        if self._quitting:
            return
        stamp = wake_stamp(self._wake_path())
        if stamp and stamp != self._wake_cursor:
            self._wake_cursor = stamp
            self._surface_all()
        self._schedule_wake_poll()

    def _surface_all(self) -> None:
        self._close_menu()
        for window in self.windows.values():
            try:
                window.raise_card()
                apply_topmost(window.top, window.card.pinned)
            except Exception:
                pass

    # ---------------------------------------------------------------- dragging
    def _drag_start(self, card_id: str, event: Any) -> None:
        window = self.windows.get(card_id)
        if window is None:
            return
        self._close_menu()
        self._set_active(card_id)
        window.raise_card()
        try:
            state = int(event.state)
        except Exception:
            state = 0
        shift = bool(state & SHIFT_MASK)
        alt = bool(state & ALT_MASK)
        rects = {cid: item.bounds() for cid, item in self.windows.items()}
        if shift:
            group_ids = find_group(card_id, rects, self.snap_gap, self.dock_tolerance)
        else:
            group_ids = (card_id,)
        if not group_ids:
            group_ids = (card_id,)
        starts: dict[str, tuple[int, int]] = {}
        sizes: dict[str, tuple[int, int]] = {}
        group_rects: list[Rect] = []
        for cid in group_ids:
            item = self.windows.get(cid)
            if item is None:
                continue
            starts[cid] = (int(item.x), int(item.y))
            sizes[cid] = (int(item.width), int(item.height))
            group_rects.append(item.bounds())
        if not starts:
            return
        self._drag = DragSession(
            card_id=card_id,
            start_pointer=(int(event.x_root), int(event.y_root)),
            group_ids=tuple(starts),
            starts=starts,
            sizes=sizes,
            bounds=group_bounds(group_rects),
            alt=alt,
            shift=shift,
        )

    def _drag_motion(self, card_id: str, event: Any) -> None:
        session = self._drag
        if session is None or session.card_id != card_id:
            return
        dx = int(event.x_root) - session.start_pointer[0]
        dy = int(event.y_root) - session.start_pointer[1]
        if not session.moved:
            if dx * dx + dy * dy < self.drag_threshold * self.drag_threshold:
                return
            session.moved = True

        if len(session.group_ids) > 1:
            left, top, right, bottom = self.screen.workarea_for_rect(session.bounds)
            adx, ady = clamp_delta_to_workarea(
                session.bounds[0],
                session.bounds[1],
                session.bounds[2] - session.bounds[0],
                session.bounds[3] - session.bounds[1],
                dx,
                dy,
                (left, top, right, bottom),
            )
            for cid in session.group_ids:
                window = self.windows.get(cid)
                if window is None:
                    continue
                start_x, start_y = session.starts[cid]
                window.move_to(start_x + adx, start_y + ady)
            return

        window = self.windows.get(card_id)
        if window is None:
            return
        start_x, start_y = session.starts[card_id]
        desired_x, desired_y = start_x + dx, start_y + dy
        width, height = window.width, window.height
        left, top, right, bottom = self.screen.workarea_for_rect(
            rect_for(desired_x, desired_y, width, height)
        )
        if not session.alt:
            others = [
                (cid, item.bounds())
                for cid, item in self.windows.items()
                if cid != card_id
            ]
            snapped = snap_move(
                desired_x,
                desired_y,
                width,
                height,
                others,
                (left, top, right, bottom),
                self.snap_gap,
                self.snap_threshold,
            )
            final_x, final_y = snapped.x, snapped.y
        else:
            final_x = min(max(desired_x, left), max(left, right - width))
            final_y = min(max(desired_y, top), max(top, bottom - height))
        window.move_to(final_x, final_y)

    def _drag_end(self, card_id: str, _event: Any) -> None:
        session = self._drag
        self._drag = None
        if session is None:
            return
        if not session.moved:
            return
        self._sync_positions()
        window = self.windows.get(card_id)
        if window is not None:
            if len(session.group_ids) > 1:
                window.show_hint(f"整组 {len(session.group_ids)} 张卡片一起移动")
            elif not session.alt:
                rects = {cid: item.bounds() for cid, item in self.windows.items()}
                group = find_group(card_id, rects, self.snap_gap, self.dock_tolerance)
                if len(group) > 1:
                    window.show_hint("已拼合 · 按住 Shift 拖动整组")
        self._schedule_save()

    # ---------------------------------------------------------------- errors
    def _report_exception(self, exc_type: Any, exc_value: Any, tb: Any) -> None:
        log.error(
            "Unhandled Tk callback exception",
            exc_info=(exc_type, exc_value, tb),
        )


def _make_first_card(state: AppState, root: Any, screen: ScreenManager) -> Card:
    card = state.ensure_card()
    try:
        scale = float(ctk.ScalingTracker.get_window_scaling(root))
    except Exception:
        scale = 1.0
    scale = max(0.5, scale)
    width = int(round(C.CARD_WIDTH * scale))
    height = int(round(290 * scale))
    left, top, right, _bottom = screen.primary_workarea()
    margin = max(8, int(round(C.DEFAULT_MARGIN * scale)))
    x = max(left, right - width - margin)
    y = top + margin
    card.x, card.y = screen.ensure_rect_visible(x, y, width, height)
    return card


def _show_loaded_message(root: Any, loaded: LoadResult) -> None:
    if loaded.status in {"recovered", "fresh"} and loaded.message:
        try:
            root.after(350, lambda: show_info(loaded.message, "数据恢复"))
        except Exception:
            pass


def create_app(
    data_dir: Path | None = None,
    *,
    instance: SingleInstance | None = None,
) -> tuple[ctk.CTk, TodoApp]:
    """Create the Tk root and application manager without entering mainloop."""
    directory = Path(data_dir) if data_dir is not None else data_directory()
    store = StateStore(directory)
    loaded = store.load()
    state = loaded.state
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.withdraw()
    root.title(C.APP_NAME)
    screen = ScreenManager(root)
    if not state.cards:
        _make_first_card(state, root, screen)
    app = TodoApp(root, store, state, screen, instance)
    app.start()
    _show_loaded_message(root, loaded)
    return root, app


def main() -> int:
    directory = data_directory()
    try:
        setup_logging(directory)
    except Exception:
        logging.basicConfig(level=logging.INFO)
    instance = SingleInstance(C.MUTEX_NAME)
    if instance.already_running:
        signal_wake(directory)
        instance.release()
        return 0
    root: ctk.CTk | None = None
    app: TodoApp | None = None
    try:
        root, app = create_app(directory, instance=instance)
        root.mainloop()
        return 0
    except Exception as exc:
        log.exception("Fatal startup error")
        try:
            show_error(f"悬浮待办启动失败：\n{exc}\n\n详情见数据目录中的 app.log。")
        except Exception:
            pass
        return 1
    finally:
        if app is not None:
            try:
                app.shutdown()
            except Exception:
                log.exception("Shutdown failed")
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
        instance.release()


if __name__ == "__main__":
    raise SystemExit(main())
