import asyncio
import time
import pyautogui
from bleak import BleakClient, BleakScanner

DEVICE_NAME_FILTER = "Zwift Ride"

# Zwift Ride uses a different BLE service than Click
ZWIFT_RIDE_SERVICE_UUID = "0000fc82-0000-1000-8000-00805f9b34fb"
ZWIFT_CUSTOM_SERVICE_UUID = "00000001-19ca-4651-86e5-fa29dcdd09d1"

ASYNC_CHAR = "00000002-19ca-4651-86e5-fa29dcdd09d1"
SYNC_RX_CHAR = "00000003-19ca-4651-86e5-fa29dcdd09d1"
SYNC_TX_CHAR = "00000004-19ca-4651-86e5-fa29dcdd09d1"

RIDE_ON = bytearray(b"RideOn")

# Ride notification message type
RIDE_NOTIFICATION_TYPE = 0x23
EMPTY_MESSAGE_TYPE = 0x15
BATTERY_LEVEL_TYPE = 25

# Zwift Ride button bitmasks
BUTTON_LEFT   = 0x00001
BUTTON_UP     = 0x00002
BUTTON_RIGHT  = 0x00004
BUTTON_DOWN   = 0x00008
BUTTON_A      = 0x00010
BUTTON_B      = 0x00020
BUTTON_Y      = 0x00040
BUTTON_Z      = 0x00080
SHIFT_UP_L    = 0x00100
SHIFT_DN_L    = 0x00200
SHIFT_UP_R    = 0x01000
SHIFT_DN_R    = 0x02000
POWERUP_L     = 0x00400
POWERUP_R     = 0x04000
ONOFF_L       = 0x00800
ONOFF_R       = 0x08000

# Map buttons to keyboard keys
# Adjust these keys for your trainer app (MyWhoosh, Zwift, etc.)
BUTTON_MAP = {
    SHIFT_UP_R:  ("Shift Up (R)",   "k"),      # gear up
    SHIFT_DN_R:  ("Shift Down (R)", "i"),      # gear down
    SHIFT_UP_L:  ("Shift Up (L)",   "k"),      # gear up
    SHIFT_DN_L:  ("Shift Down (L)", "i"),      # gear down
    BUTTON_UP:   ("D-Pad Up",       "up"),
    BUTTON_DOWN: ("D-Pad Down",     "down"),
    BUTTON_LEFT: ("D-Pad Left",     "left"),
    BUTTON_RIGHT:("D-Pad Right",    "right"),
    BUTTON_A:    ("A Button",       "enter"),
    BUTTON_B:    ("B Button",       "escape"),
    BUTTON_Y:    ("Y Button",       "u"),      # HUD toggle
    BUTTON_Z:    ("Z Button",       "space"),  # ride on / action
    POWERUP_L:   ("PowerUp Left",   "space"),
    POWERUP_R:   ("PowerUp Right",  "space"),
    ONOFF_L:     ("On/Off Left",    "u"),
    ONOFF_R:     ("On/Off Right",   "u"),
}

DEBOUNCE_DELAY = 0.15
last_click_time = 0
last_buttons = 0

def parse_ride_buttons(data):
    """Parse button bitmask from Zwift Ride controller notification.

    The notification format is a protobuf message. The button map is
    typically a varint in field 1. We do a simple extraction: read
    varint(s) after the message type byte.
    """
    if len(data) < 2:
        return 0

    # Try to decode a varint starting at position 0
    # Protobuf: field 1, wire type 0 (varint) => tag byte = 0x08
    pos = 0
    button_map = 0

    # Look for tag 0x08 (field 1, varint)
    while pos < len(data):
        if data[pos] == 0x08:
            pos += 1
            # Decode varint
            shift = 0
            while pos < len(data):
                byte = data[pos]
                button_map |= (byte & 0x7F) << shift
                pos += 1
                shift += 7
                if byte & 0x80 == 0:
                    break
            return button_map
        pos += 1

    return 0


def notification_handler(sender, data):
    global last_click_time, last_buttons

    if len(data) < 2:
        return

    msg_type = data[0]
    message = data[1:]

    if msg_type == EMPTY_MESSAGE_TYPE:
        return

    if msg_type == BATTERY_LEVEL_TYPE and len(message) >= 2:
        print(f"Battery: {message[1]}%")
        return

    if msg_type != RIDE_NOTIFICATION_TYPE:
        return

    button_map = parse_ride_buttons(message)

    if button_map == last_buttons:
        return

    current_time = time.time()
    new_presses = button_map & ~last_buttons
    last_buttons = button_map

    if new_presses == 0:
        return

    if (current_time - last_click_time) < DEBOUNCE_DELAY:
        return

    for mask, (name, key) in BUTTON_MAP.items():
        if new_presses & mask:
            print(f">>> [ {name} ] -> Key: {key.upper()}")
            try:
                pyautogui.press(key)
            except Exception as e:
                print(f"Error pressing key: {e}")

    last_click_time = current_time


async def run():
    print("Searching for Zwift Ride...")
    print("(Make sure blue light is blinking)")
    print()

    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: d.name and DEVICE_NAME_FILTER in d.name,
        timeout=15
    )

    if not device:
        print("Zwift Ride not found!")
        return

    print(f"Found: {device.name} [{device.address}]")

    try:
        async with BleakClient(device.address) as client:
            print(f"Connected: {client.is_connected}")

            # Find the right service
            service = None
            for s in client.services:
                if s.uuid == ZWIFT_RIDE_SERVICE_UUID or s.uuid == ZWIFT_CUSTOM_SERVICE_UUID:
                    service = s
                    break

            if not service:
                print(f"Custom service not found! Available services:")
                for s in client.services:
                    print(f"  {s.uuid}")
                return

            print(f"Using service: {service.uuid}")

            # Subscribe to notifications on async characteristic
            await client.start_notify(ASYNC_CHAR, notification_handler)

            # Subscribe to indications on sync TX
            try:
                await client.start_notify(SYNC_TX_CHAR, notification_handler)
            except Exception:
                pass

            # Send RideOn handshake
            print("Sending RideOn handshake...")
            await client.write_gatt_char(SYNC_RX_CHAR, RIDE_ON, response=False)

            print()
            print("--- Zwift Ride Connected ---")
            print("Shift levers: I (down) / K (up)")
            print("D-Pad: arrow keys")
            print("A=Enter, B=Escape, Y=HUD, Z=Action")
            print()
            print("Press Ctrl+C to exit")
            print()

            while True:
                if not client.is_connected:
                    print("Disconnected!")
                    break
                await asyncio.sleep(1)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nExiting.")
