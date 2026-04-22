from __future__ import annotations

import asyncio
import time
from typing import Callable

import pyautogui

from bikebridge.devices.base import BaseDevice, ButtonEvent
from bikebridge.mapper import KeyMapper


class Controller:
    """Connects one or more devices to a key mapper and handles press-to-keystroke.

    Accepts a single device or a list of devices — for hardware like the
    Zwift Ride that exposes two BLE radios (left + right side).
    """

    def __init__(
        self,
        devices: BaseDevice | list[BaseDevice],
        mapper: KeyMapper,
        debounce: float = 0.15,
        send_keys: bool = True,
    ):
        self.devices = devices if isinstance(devices, list) else [devices]
        self.mapper = mapper
        self.debounce = debounce
        self.send_keys = send_keys

        self._last_press_time: float = 0
        self._on_event: list[Callable[[ButtonEvent, str | None], None]] = []

        for device in self.devices:
            device.on_button(self._handle_button)

    def on_event(self, callback: Callable[[ButtonEvent, str | None], None]) -> None:
        """Register callback: (button_event, mapped_key_or_None)."""
        self._on_event.append(callback)

    def _handle_button(self, event: ButtonEvent) -> None:
        if not event.pressed:
            return

        now = time.time()
        if (now - self._last_press_time) < self.debounce:
            return
        self._last_press_time = now

        key = self.mapper.get_key(event.button_id)

        if key and self.send_keys:
            try:
                pyautogui.press(key)
            except Exception:
                pass

        for cb in self._on_event:
            cb(event, key)

    async def start(self) -> None:
        await asyncio.gather(*(d.connect() for d in self.devices))
        await asyncio.gather(*(d.keep_alive() for d in self.devices))

    async def stop(self) -> None:
        await asyncio.gather(*(d.disconnect() for d in self.devices))
