from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class ButtonAction:
    """Represents what happens when a button is pressed."""
    key: str
    label: str = ""

    def __str__(self) -> str:
        return f"{self.label} -> {self.key}" if self.label else self.key


class KeyMapper:
    """Maps device button IDs to keyboard actions.

    Supports loading/saving mappings to JSON so users can customize
    their button layout.
    """

    def __init__(self, mapping: dict[str, ButtonAction] | None = None):
        self._mapping: dict[str, ButtonAction] = mapping or {}
        self._on_change: list[Callable[[], None]] = []

    @property
    def mapping(self) -> dict[str, ButtonAction]:
        return dict(self._mapping)

    def set(self, button_id: str, key: str, label: str = "") -> None:
        self._mapping[button_id] = ButtonAction(key=key, label=label)
        self._notify()

    def remove(self, button_id: str) -> None:
        self._mapping.pop(button_id, None)
        self._notify()

    def get(self, button_id: str) -> ButtonAction | None:
        return self._mapping.get(button_id)

    def get_key(self, button_id: str) -> str | None:
        action = self._mapping.get(button_id)
        return action.key if action else None

    def on_change(self, callback: Callable[[], None]) -> None:
        self._on_change.append(callback)

    def _notify(self) -> None:
        for cb in self._on_change:
            cb()

    def save(self, path: str | Path) -> None:
        data = {
            btn_id: {"key": action.key, "label": action.label}
            for btn_id, action in self._mapping.items()
        }
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> KeyMapper:
        p = Path(path)
        if not p.exists():
            return cls()
        data = json.loads(p.read_text(encoding="utf-8"))
        mapping = {
            btn_id: ButtonAction(key=entry["key"], label=entry.get("label", ""))
            for btn_id, entry in data.items()
        }
        return cls(mapping)

    @classmethod
    def default_config_path(cls) -> Path:
        config_dir = Path(os.environ.get("APPDATA", Path.home())) / "bikebridge"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "keymaps.json"
