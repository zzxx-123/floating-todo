"""End-to-end GUI smoke test for the floating todo cards.

Run from the project root with a normal Python console::

    python tests/gui_smoke.py

The script creates its own throwaway data directory, exercises the real Tk /
CustomTkinter windows, saves screenshots in ``artifacts/`` and exits with a
non-zero status if an assertion fails.  It does not touch the normal
``%APPDATA%\\FloatingTodoCard`` data.
"""

from __future__ import annotations

import ctypes
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if sys.platform != "win32":
    print("SKIP: the floating card UI is Windows-only.")
    raise SystemExit(0)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

from PIL import ImageGrab  # noqa: E402

from floating_todo.app import create_app  # noqa: E402
from floating_todo.models import Card  # noqa: E402
from floating_todo.snapping import find_group  # noqa: E402
from floating_todo.storage import StateStore  # noqa: E402
from floating_todo.widgets import IconButton  # noqa: E402

DATA = PROJECT_ROOT / "artifacts" / "gui-smoke-data"
SHOTS = PROJECT_ROOT / "artifacts"
DATA.mkdir(parents=True, exist_ok=True)
SHOTS.mkdir(parents=True, exist_ok=True)
for leftover in DATA.glob("state*"):
    try:
        leftover.unlink()
    except OSError:
        pass


class SmokeFailure(AssertionError):
    pass


def check(condition: object, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


class FakeEvent:
    def __init__(self, state: int, x_root: int, y_root: int) -> None:
        self.state = state
        self.x_root = x_root
        self.y_root = y_root


root = None
app = None
failures: list[str] = []
step_index = 0
first_id = ""
second_id = ""
had_tip = False


def guarded(callback):
    def wrapper() -> None:
        global step_index
        try:
            callback()
        except Exception:
            failures.append(traceback.format_exc())
            print("\nFAILED during step", step_index)
            traceback.print_exc()
            stop(1)

    return wrapper


def finish(code: int = 0) -> None:
    global app, root
    if app is not None:
        try:
            app.quit()
        except Exception:
            failures.append(traceback.format_exc())
    if root is not None:
        try:
            root.after(50, root.quit)
        except Exception:
            try:
                root.quit()
            except Exception:
                pass


def stop(code: int = 1) -> None:
    finish(code)


def schedule(delay: int, callback) -> None:
    assert root is not None
    root.after(delay, guarded(callback))


# ------------------------------------------------------------------ steps
def step_initial() -> None:
    global first_id, had_tip
    check(len(app.windows) == 1, f"expected one first-run card, got {len(app.windows)}")
    first_id = next(iter(app.windows))
    win = app.windows[first_id]
    check(win.card.title == "今天", f"unexpected first card title: {win.card.title}")
    check(win.card.total_count == 0, "first-run card should be empty")
    check(win.width == int(round(372 * app.scale)), f"unexpected card width {win.width}")
    check(win._empty.winfo_ismapped(), "empty state is not visible")
    check(win.has_tip(), "onboarding tip is missing on first run")
    had_tip = True
    print(
        "FIRST_RUN",
        f"size={win.width}x{win.height}",
        f"pos=({win.x},{win.y})",
        f"scale={app.scale}",
        f"tip={win.has_tip()}",
    )
    ImageGrab.grab(all_screens=True).save(SHOTS / "gui-smoke-first-run.png")

    win._add_bar.entry.insert(0, "整理本周的产品需求")
    check(win._add_bar.submit() is True, "add task 1 failed")
    win._add_bar.entry.insert(0, "回复设计稿的评审意见")
    check(win._add_bar.submit() is True, "add task 2 failed")
    check(win.card.total_count == 2, f"expected 2 tasks, got {win.card.total_count}")
    schedule(400, step_after_add)


def step_after_add() -> None:
    win = app.windows[first_id]
    check(win.card.total_count == 2, "task list did not persist after add")
    check(len(win._tasks.rows) == 2, f"expected two rendered rows, got {len(win._tasks.rows)}")
    check(win._add_bar.entry.get() == "", "add input was not cleared")
    first_task = win.card.tasks[0]
    row = next(r for r in win._tasks.rows if r.task.id == first_task.id)
    row._check.invoke()
    check(win.card.completed_count == 1, "checking a task did not update the model")
    print("ADD_AND_CHECK", f"completed={win.card.completed_count}/{win.card.total_count}")
    schedule(350, step_after_toggle)


def step_after_toggle() -> None:
    win = app.windows[first_id]
    check(win.card.completed_count == 1, "completed count lost after rerender")
    target = next(task for task in win.card.tasks if not task.done)
    row = next(r for r in win._tasks.rows if r.task.id == target.id)
    row._start_edit()
    check(row._edit is not None, "inline task editor did not open")
    row._edit.delete(0, "end")
    row._edit.insert(0, "回复设计稿的最终评审意见")
    row._commit_edit()
    check(
        target.text == "回复设计稿的最终评审意见",
        f"inline edit not applied: {target.text!r}",
    )
    print("INLINE_EDIT", "ok")
    schedule(300, step_after_edit)


def step_after_edit() -> None:
    global second_id
    win = app.windows[first_id]
    check(win.has_tip(), "tip disappeared before it was dismissed")
    tip = win._tip
    check(tip is not None, "tip object is missing")
    close_button = None
    for child in tip.winfo_children():
        if isinstance(child, IconButton):
            close_button = child
            break
    check(close_button is not None, "tip close button was not found")
    close_button.invoke()
    check(not win.has_tip(), "tip was not hidden by its close button")
    check(app.state.onboarding_dismissed is True, "onboarding dismissal was not persisted to state")
    print("TIP_DISMISSED", "ok")

    app._new_card(first_id)
    check(len(app.windows) == 2, "new card was not created")
    check(len(app.state.cards) == 2, "new card missing from state")
    second_id = next(card.id for card in app.state.cards if card.id != first_id)
    second = app.windows[second_id]
    check(second.card.title == "新清单", f"unexpected new card title: {second.card.title}")
    schedule(350, step_after_new)


def step_after_new() -> None:
    win = app.windows[second_id]
    check(win._empty.winfo_ismapped(), "new card does not show its empty state")
    check(win.begin_rename() == "break", "begin_rename did not start editing")
    entry = win._header._rename_entry
    check(entry is not None, "rename entry is missing")
    entry.delete(0, "end")
    entry.insert(0, "周末计划")
    win._header._commit_rename()
    check(win.card.title == "周末计划", f"rename failed: {win.card.title!r}")

    app._show_menu(second_id, win._header._menu_btn)
    menu = app._menu
    check(menu is not None, "card menu did not open")
    menu._color_buttons["sky"].invoke()
    check(win.card.accent == "sky", f"menu color action failed: {win.card.accent}")
    check(app._menu is None, "menu was not cleared after an action")
    print("RENAME_AND_MENU", win.card.title, win.card.accent)
    schedule(300, step_after_color)


def step_after_color() -> None:
    win = app.windows[second_id]
    for text in ("去看新开的展览", "跑步 5 公里", "给家里打电话"):
        win._add_bar.entry.insert(0, text)
        check(win._add_bar.submit() is True, f"failed to add {text}")
    check(win.card.total_count == 3, "second card does not have 3 tasks")
    print("SECOND_CARD", f"tasks={win.card.total_count}", f"accent={win.card.accent}")
    schedule(350, step_collapse)


def step_collapse() -> None:
    win = app.windows[second_id]
    before = win.height
    win.toggle_collapse()
    check(win.card.collapsed is True, "collapse flag did not change")
    schedule(320, lambda: step_check_collapsed(win, before))


def step_check_collapsed(win, before: int) -> None:
    check(not win._body.winfo_ismapped(), "collapsed card is still showing its body")
    check(win.height < before, f"collapsed height did not shrink ({win.height} >= {before})")
    check(win.height < int(180 * app.scale), f"collapsed card is too tall: {win.height}")
    print("COLLAPSED", f"{before}px -> {win.height}px")
    win.toggle_collapse()
    check(win.card.collapsed is False, "expand flag did not change")
    schedule(320, step_after_expand)


def step_after_expand() -> None:
    win2 = app.windows[second_id]
    check(win2._body.winfo_ismapped(), "expanded card body is not visible")
    check(win2.height > int(180 * app.scale), "expanded card did not restore its height")

    win1 = app.windows[first_id]
    before_pinned = win1.card.pinned
    win1._header._pin_btn.invoke()
    check(win1.card.pinned != before_pinned, "pin button did not toggle")
    win1._header._pin_btn.invoke()
    check(win1.card.pinned == before_pinned, "pin button did not toggle back")
    print("EXPAND_AND_PIN", f"height={win2.height}", f"pinned={win1.card.pinned}")

    win1.move_to(1050, 780)
    win2.move_to(1800, 780)
    target_x = win2.x - win1.width - app.snap_gap
    dx = target_x - win1.x
    app._drag_start(first_id, FakeEvent(0, win1.x + 100, win1.y + 30))
    app._drag_motion(first_id, FakeEvent(0, win1.x + 100 + dx, win1.y + 30))
    app._drag_end(first_id, FakeEvent(0, 0, 0))
    gap = win2.x - (win1.x + win1.width)
    check(gap == app.snap_gap, f"magnetic snap failed: gap={gap} expected={app.snap_gap}")
    rects = {cid: window.bounds() for cid, window in app.windows.items()}
    group = find_group(first_id, rects, app.snap_gap, app.dock_tolerance)
    check(set(group) == {first_id, second_id}, f"cards did not join a group: {group}")
    print("SNAP", f"gap={gap}", f"group={len(group)}")

    before = (win1.x, win1.y, win2.x, win2.y)
    app._drag_start(first_id, FakeEvent(1, win1.x + 100, win1.y + 30))
    app._drag_motion(first_id, FakeEvent(1, win1.x + 160, win1.y + 60))
    app._drag_end(first_id, FakeEvent(1, 0, 0))
    delta1 = (win1.x - before[0], win1.y - before[1])
    delta2 = (win2.x - before[2], win2.y - before[3])
    check(delta1 == delta2, f"group drag moved cards differently: {delta1} vs {delta2}")
    check(delta1 != (0, 0), "group drag did not move anything")
    print("GROUP_DRAG", before, "->", (win1.x, win1.y, win2.x, win2.y))
    schedule(350, step_appearance)


def step_appearance() -> None:
    check(app.state.appearance == "solid", "first-run appearance is not solid")
    app.toggle_appearance()
    check(app.state.appearance == "glass", "appearance did not toggle to glass")
    check(
        all(window.appearance == "glass" for window in app.windows.values()),
        "glass appearance was not propagated to every card",
    )
    print("APPEARANCE", "glass")
    app.toggle_appearance()
    check(app.state.appearance == "solid", "appearance did not toggle back to solid")
    check(
        all(window.appearance == "solid" for window in app.windows.values()),
        "solid appearance was not propagated to every card",
    )
    print("APPEARANCE", "solid")
    schedule(250, step_preview)


def step_preview() -> None:
    win1 = app.windows[first_id]
    win2 = app.windows[second_id]
    # Arrange a clean pair at the top right of the primary work area.
    win1.move_to(1300, 360)
    win2.move_to(1873, 360)
    schedule(300, step_capture)


def step_capture() -> None:
    ImageGrab.grab(all_screens=True).save(SHOTS / "gui-smoke.png")
    print("SCREENSHOT", SHOTS / "gui-smoke.png")
    finish(0)


# ------------------------------------------------------------------ run
try:
    root, app = create_app(DATA)
    assert root is not None and app is not None
    root.after(800, guarded(step_initial))
    root.mainloop()
except Exception:
    failures.append(traceback.format_exc())
    traceback.print_exc()
finally:
    if app is not None:
        try:
            app.shutdown()
        except Exception:
            failures.append(traceback.format_exc())
    if root is not None:
        try:
            root.destroy()
        except Exception:
            pass

loaded = StateStore(DATA).load()
print("\nPERSISTED", loaded.status)
print(
    [
        (card.title, card.accent, card.x, card.y, card.collapsed, [(t.text, t.done) for t in card.tasks])
        for card in loaded.state.cards
    ]
)
print("ONBOARDING", loaded.state.onboarding_dismissed)
print("APPEARANCE", loaded.state.appearance)

if failures:
    print("\nGUI SMOKE TEST FAILED")
    for failure in failures:
        print(failure)
    raise SystemExit(1)

check(loaded.status == "ok", f"state was not reloaded cleanly: {loaded.status}")
check(len(loaded.state.cards) == 2, f"expected 2 persisted cards, got {len(loaded.state.cards)}")
check(loaded.state.onboarding_dismissed is True, "onboarding flag was not persisted")
check(loaded.state.appearance == "solid", "appearance was not restored to solid")
check(
    {card.accent for card in loaded.state.cards} == {"coral", "sky"},
    "card accents were not persisted",
)
check(
    sum(card.total_count for card in loaded.state.cards) == 5,
    "task totals were not persisted",
)
print("\nGUI SMOKE TEST PASSED")
raise SystemExit(0)
