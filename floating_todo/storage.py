"""Robust JSON persistence for the floating todo cards."""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from .constants import BACKUP_FILE_NAME, STATE_FILE_NAME
from .models import AppState, StateFormatError

log = logging.getLogger(__name__)

MAX_STATE_BYTES = 8 * 1024 * 1024


class StorageError(RuntimeError):
    """A storage problem that should be shown to the user."""


@dataclass
class LoadResult:
    state: AppState
    status: str  # new | ok | recovered | fresh
    message: str = ""


def _read_state(path: Path) -> AppState:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise StorageError(f"无法读取数据文件：{exc}") from exc
    if size > MAX_STATE_BYTES:
        raise StateFormatError("数据文件异常地大")
    try:
        raw_text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise StorageError(f"无法读取数据文件：{exc}") from exc
    try:
        raw = json.loads(raw_text)
    except (ValueError, TypeError) as exc:
        raise StateFormatError(f"JSON 格式错误：{exc}") from exc
    return AppState.from_dict(raw)


def _is_valid_state_file(path: Path) -> bool:
    try:
        _read_state(path)
    except (StorageError, StateFormatError):
        return False
    return True


class StateStore:
    """Reads/writes one state document with an atomic replace and backup."""

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / STATE_FILE_NAME
        self.backup_path = self.data_dir / BACKUP_FILE_NAME

    # ------------------------------------------------------------------ load
    def load(self) -> LoadResult:
        main_error: Exception | None = None
        if self.path.exists():
            try:
                return LoadResult(_read_state(self.path), "ok")
            except (StorageError, StateFormatError) as exc:
                main_error = exc
                log.warning("Could not read %s: %s", self.path, exc)
                self._preserve_corrupt(self.path)

        if self.backup_path.exists():
            try:
                state = _read_state(self.backup_path)
            except (StorageError, StateFormatError) as exc:
                log.warning("Could not read backup %s: %s", self.backup_path, exc)
                self._preserve_corrupt(self.backup_path)
            else:
                log.warning("Recovered state from backup: %s", self.backup_path)
                return LoadResult(
                    state,
                    "recovered",
                    "已从备份恢复数据，原文件已保留。",
                )

        if main_error is None:
            return LoadResult(AppState(), "new")
        log.error("State document is unreadable and no usable backup exists: %s", main_error)
        return LoadResult(
            AppState(),
            "fresh",
            "原数据文件无法读取，已创建新的清单；原文件已保留。",
        )

    def _preserve_corrupt(self, source: Path) -> Path | None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = self.data_dir / f"state.corrupt-{stamp}.json"
        counter = 1
        while target.exists():
            target = self.data_dir / f"state.corrupt-{stamp}-{counter}.json"
            counter += 1
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            return target
        except OSError as exc:
            log.warning("Could not preserve corrupt data file %s: %s", source, exc)
            return None

    # ------------------------------------------------------------------ save
    def save(self, state: AppState) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
        except (OSError, TypeError, ValueError) as exc:
            raise StorageError(f"无法准备保存数据：{exc}") from exc

        tmp_path = self.path.with_name(f"{self.path.name}.tmp-{os.getpid()}")
        try:
            if self.path.exists() and _is_valid_state_file(self.path):
                self._write_backup()
            with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.path)
        except OSError as exc:
            raise StorageError(f"保存失败：{exc}") from exc
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass

    def _write_backup(self) -> None:
        tmp_backup = self.backup_path.with_name(f"{self.backup_path.name}.tmp-{os.getpid()}")
        try:
            shutil.copy2(self.path, tmp_backup)
            os.replace(tmp_backup, self.backup_path)
        except OSError as exc:
            log.warning("Could not update backup: %s", exc)
            try:
                if tmp_backup.exists():
                    tmp_backup.unlink()
            except OSError:
                pass
