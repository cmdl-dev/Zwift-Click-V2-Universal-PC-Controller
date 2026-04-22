from __future__ import annotations

from bikebridge.devices.base import BaseDevice, ButtonEvent

ZWIFT_RIDE_SERVICE = "0000fc82-0000-1000-8000-00805f9b34fb"
ZWIFT_CUSTOM_SERVICE = "00000001-19ca-4651-86e5-fa29dcdd09d1"
ASYNC_CHAR = "00000002-19ca-4651-86e5-fa29dcdd09d1"
SYNC_RX_CHAR = "00000003-19ca-4651-86e5-fa29dcdd09d1"
SYNC_TX_CHAR = "00000004-19ca-4651-86e5-fa29dcdd09d1"

RIDE_ON = bytearray(b"RideOn")

RIDE_NOTIFICATION_TYPE = 0x23
EMPTY_MESSAGE_TYPE = 0x15
BATTERY_LEVEL_TYPE = 25


class RideButton:
    LEFT      = ("left",       0x00001, "D-Pad Left")
    UP        = ("up",         0x00002, "D-Pad Up")
    RIGHT     = ("right",      0x00004, "D-Pad Right")
    DOWN      = ("down",       0x00008, "D-Pad Down")
    A         = ("a",          0x00010, "A Button")
    B         = ("b",          0x00020, "B Button")
    Y         = ("y",          0x00040, "Y Button")
    Z         = ("z",          0x00080, "Z Button")
    SHIFT_UP_L  = ("shift_up_l",  0x00100, "Shift Up Left")
    SHIFT_DN_L  = ("shift_dn_l",  0x00200, "Shift Down Left")
    POWERUP_L   = ("powerup_l",   0x00400, "PowerUp Left")
    ONOFF_L     = ("onoff_l",     0x00800, "On/Off Left")
    SHIFT_UP_R  = ("shift_up_r",  0x01000, "Shift Up Right")
    SHIFT_DN_R  = ("shift_dn_r",  0x02000, "Shift Down Right")
    POWERUP_R   = ("powerup_r",   0x04000, "PowerUp Right")
    ONOFF_R     = ("onoff_r",     0x08000, "On/Off Right")

    ALL = [
        LEFT, UP, RIGHT, DOWN,
        A, B, Y, Z,
        SHIFT_UP_L, SHIFT_DN_L, POWERUP_L, ONOFF_L,
        SHIFT_UP_R, SHIFT_DN_R, POWERUP_R, ONOFF_R,
    ]


def _parse_button_map(data: bytes) -> int:
    pos = 0
    while pos < len(data):
        if data[pos] == 0x08:
            pos += 1
            result = 0
            shift = 0
            while pos < len(data):
                byte = data[pos]
                result |= (byte & 0x7F) << shift
                pos += 1
                shift += 7
                if byte & 0x80 == 0:
                    break
            return result
        pos += 1
    return 0


class ZwiftRide(BaseDevice):
    DEVICE_NAME = "Zwift Ride"
    DEVICE_LABEL = "Zwift Ride"

    def __init__(self, address: str):
        super().__init__(address)
        self._last_buttons: int = 0

    @classmethod
    def matches(cls, device_name: str) -> bool:
        return "Zwift Ride" in device_name

    @classmethod
    def default_button_map(cls) -> dict[str, tuple[str, str]]:
        return {
            "shift_up_r":  ("Shift Up Right",  "k"),
            "shift_dn_r":  ("Shift Down Right", "i"),
            "shift_up_l":  ("Shift Up Left",   "k"),
            "shift_dn_l":  ("Shift Down Left", "i"),
            "up":          ("D-Pad Up",        "up"),
            "down":        ("D-Pad Down",      "down"),
            "left":        ("D-Pad Left",      "left"),
            "right":       ("D-Pad Right",     "right"),
            "a":           ("A Button",        "enter"),
            "b":           ("B Button",        "escape"),
            "y":           ("Y Button",        "u"),
            "z":           ("Z Button",        "space"),
            "powerup_l":   ("PowerUp Left",    "space"),
            "powerup_r":   ("PowerUp Right",   "space"),
            "onoff_l":     ("On/Off Left",     "u"),
            "onoff_r":     ("On/Off Right",    "u"),
        }

    def _get_characteristics(self) -> tuple[str, str, str | None]:
        return ASYNC_CHAR, SYNC_RX_CHAR, SYNC_TX_CHAR

    async def _handshake(self) -> None:
        if self.client:
            await self.client.write_gatt_char(SYNC_RX_CHAR, RIDE_ON, response=False)

    def _handle_notification(self, sender: int, data: bytearray) -> None:
        if len(data) < 2:
            return

        msg_type = data[0]
        message = data[1:]

        if msg_type == EMPTY_MESSAGE_TYPE:
            return

        if msg_type == BATTERY_LEVEL_TYPE and len(message) >= 2:
            self._emit_battery(message[1])
            return

        if msg_type != RIDE_NOTIFICATION_TYPE:
            return

        button_map = _parse_button_map(message)
        new_presses = button_map & ~self._last_buttons
        new_releases = self._last_buttons & ~button_map
        self._last_buttons = button_map

        for btn_id, mask, btn_name in RideButton.ALL:
            if new_presses & mask:
                self._emit_button(ButtonEvent(btn_id, btn_name, pressed=True))
            elif new_releases & mask:
                self._emit_button(ButtonEvent(btn_id, btn_name, pressed=False))

    async def keep_alive(self) -> None:
        import asyncio
        while self.client and self.client.is_connected:
            await asyncio.sleep(1)
