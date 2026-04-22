from __future__ import annotations

import asyncio
from bikebridge.devices.base import BaseDevice, ButtonEvent

NOTIFY_CHAR = "00000002-19ca-4651-86e5-fa29dcdd09d1"
WRITE_CHAR = "00000003-19ca-4651-86e5-fa29dcdd09d1"

ACTIVATION_SEQUENCE = [
    bytearray.fromhex("526964654f6e0203"),
    bytearray.fromhex("000800"),
    bytearray.fromhex("000810"),
]

IDLE_HEX = "2308FFFFFFFF0F"

BUTTON_HEX_MAP = {
    "2308FFDFFFFF0F": ("plus",  "Plus"),
    "2308FFFDFFFF0F": ("minus", "Minus"),
    "2308FEFFFFFF0F": ("left",  "Left"),
    "2308FDFFFFFF0F": ("up",    "Up"),
    "2308FBFFFFFF0F": ("right", "Right"),
    "2308F7FFFFFF0F": ("down",  "Down"),
}


class ZwiftClickV2(BaseDevice):
    DEVICE_NAME = "Zwift Click"
    DEVICE_LABEL = "Zwift Click v2"

    def __init__(self, address: str):
        super().__init__(address)

    @classmethod
    def matches(cls, device_name: str) -> bool:
        return "Zwift Click" in device_name

    @classmethod
    def default_button_map(cls) -> dict[str, tuple[str, str]]:
        return {
            "plus":  ("Plus (+)",  "k"),
            "minus": ("Minus (-)", "i"),
            "left":  ("Left",      "left"),
            "up":    ("Up",        "u"),
            "right": ("Right",     "right"),
            "down":  ("Down",      "down"),
        }

    def _get_characteristics(self) -> tuple[str, str, str | None]:
        return NOTIFY_CHAR, WRITE_CHAR, None

    async def _handshake(self) -> None:
        if not self.client:
            return
        for payload in ACTIVATION_SEQUENCE:
            await self.client.write_gatt_char(WRITE_CHAR, payload, response=False)
            await asyncio.sleep(0.1)

    def _handle_notification(self, sender: int, data: bytearray) -> None:
        hex_data = data.hex().upper()

        if hex_data == IDLE_HEX or len(hex_data) > 20:
            return

        if hex_data in BUTTON_HEX_MAP:
            btn_id, btn_name = BUTTON_HEX_MAP[hex_data]
            self._emit_button(ButtonEvent(btn_id, btn_name, pressed=True))

    async def keep_alive(self) -> None:
        while self.client and self.client.is_connected:
            await self.client.write_gatt_char(
                WRITE_CHAR, bytearray.fromhex("000810"), response=False
            )
            await asyncio.sleep(5)
