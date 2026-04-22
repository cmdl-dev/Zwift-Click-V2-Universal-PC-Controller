from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

from bleak import BleakClient


@dataclass
class ButtonEvent:
    button_id: str
    button_name: str
    pressed: bool  # True = pressed, False = released


class BaseDevice(ABC):
    """Abstract base for all BLE controller devices."""

    DEVICE_NAME: str = ""
    DEVICE_LABEL: str = ""

    def __init__(self, address: str):
        self.address = address
        self.client: BleakClient | None = None
        self.connected = False
        self.battery_level: int | None = None
        self._on_button: list[Callable[[ButtonEvent], None]] = []
        self._on_connect: list[Callable[[bool], None]] = []
        self._on_battery: list[Callable[[int], None]] = []

    @classmethod
    @abstractmethod
    def matches(cls, device_name: str) -> bool:
        """Return True if this driver handles the given BLE device name."""

    @classmethod
    @abstractmethod
    def default_button_map(cls) -> dict[str, tuple[str, str]]:
        """Return {button_id: (button_label, default_key)}."""

    @abstractmethod
    async def _handshake(self) -> None:
        """Send any activation/init bytes after connecting."""

    @abstractmethod
    def _handle_notification(self, sender: int, data: bytearray) -> None:
        """Process raw BLE notification data into ButtonEvents."""

    @abstractmethod
    def _get_characteristics(self) -> tuple[str, str, str | None]:
        """Return (notify_char, write_char, optional_indication_char)."""

    def on_button(self, callback: Callable[[ButtonEvent], None]) -> None:
        self._on_button.append(callback)

    def on_connect(self, callback: Callable[[bool], None]) -> None:
        self._on_connect.append(callback)

    def on_battery(self, callback: Callable[[int], None]) -> None:
        self._on_battery.append(callback)

    def _emit_button(self, event: ButtonEvent) -> None:
        for cb in self._on_button:
            cb(event)

    def _emit_connect(self, connected: bool) -> None:
        self.connected = connected
        for cb in self._on_connect:
            cb(connected)

    def _emit_battery(self, level: int) -> None:
        self.battery_level = level
        for cb in self._on_battery:
            cb(level)

    async def connect(self) -> None:
        self.client = BleakClient(self.address, disconnected_callback=self._on_disconnect)
        await self.client.connect()
        self._emit_connect(True)

        notify_char, write_char, indication_char = self._get_characteristics()

        await self.client.start_notify(notify_char, self._handle_notification)

        if indication_char:
            try:
                await self.client.start_notify(indication_char, self._handle_notification)
            except Exception:
                pass

        await self._handshake()

    async def disconnect(self) -> None:
        if self.client and self.client.is_connected:
            await self.client.disconnect()
        self._emit_connect(False)

    def _on_disconnect(self, client: BleakClient) -> None:
        self._emit_connect(False)

    async def keep_alive(self) -> None:
        """Block while connected. Override to send periodic pings."""
        while self.client and self.client.is_connected:
            await asyncio.sleep(1)
