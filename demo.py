"""Demo CLI showing how to use the bikebridge library.

Usage:
    python demo.py              # scan, auto-detect, connect, and map keys
    python demo.py --scan-only  # just list nearby BLE devices
"""

import asyncio
import sys
from collections import defaultdict

from bikebridge import Scanner, KeyMapper, Controller
from bikebridge.devices import DeviceRegistry, ButtonEvent


async def scan_only():
    scanner = Scanner()
    print("Scanning for BLE devices (10s)...\n")
    devices = await scanner.scan_all(timeout=10)
    for d in devices:
        driver = DeviceRegistry.identify(d)
        tag = f"  <- {driver.DEVICE_LABEL}" if driver else ""
        print(f"  {d.name:30s}  {d.address}  RSSI: {d.rssi}{tag}")
    print(f"\n{len(devices)} device(s) found.")


async def connect_and_run():
    scanner = Scanner()
    print("Scanning for supported controllers (15s)...\n")

    devices = await scanner.scan_all(timeout=15)

    # Group discovered devices by driver type so paired units
    # (e.g. Zwift Ride left + right) are treated as one controller
    groups: dict[str, list[tuple]] = defaultdict(list)
    for d in devices:
        driver = DeviceRegistry.identify(d)
        if driver:
            groups[driver.DEVICE_LABEL].append((d, driver))

    if not groups:
        print("No supported controllers found.")
        print("Make sure your device is in pairing mode (blue blinking light).")
        return

    group_list = list(groups.items())

    print("Found supported controller(s):")
    for i, (label, members) in enumerate(group_list):
        addrs = ", ".join(m[0].address for m in members)
        count = f" ({len(members)} radios)" if len(members) > 1 else ""
        print(f"  [{i+1}] {label}{count} - {addrs}")
    print()

    if len(group_list) == 1:
        choice = 0
    else:
        raw = input(f"Select controller [1-{len(group_list)}]: ").strip()
        choice = int(raw) - 1

    label, members = group_list[choice]
    driver_cls = members[0][1]

    # Create a device instance for each BLE radio in the group
    device_instances = [driver_cls(d.address) for d, _ in members]

    # Load saved keymap or use device defaults
    config_path = KeyMapper.default_config_path()
    mapper = KeyMapper.load(config_path)

    if not mapper.mapping:
        print("No saved keymap found, using device defaults.")
        for btn_id, (btn_label, key) in driver_cls.default_button_map().items():
            mapper.set(btn_id, key, btn_label)
        mapper.save(config_path)
        print(f"Default keymap saved to {config_path}")

    print()
    print("Current key mapping:")
    for btn_id, action in mapper.mapping.items():
        print(f"  {action.label or btn_id:25s} -> {action.key}")
    print()

    def on_event(event: ButtonEvent, key: str | None):
        if key:
            print(f">>> [ {event.button_name} ] -> Key: {key.upper()}")
        else:
            print(f">>> [ {event.button_name} ] (unmapped)")

    def on_battery(level: int):
        print(f"Battery: {level}%")

    def on_connect(connected: bool):
        if connected:
            print("Connected!")
        else:
            print("Disconnected.")

    for dev in device_instances:
        dev.on_connect(on_connect)
        dev.on_battery(on_battery)

    controller = Controller(device_instances, mapper)
    controller.on_event(on_event)

    radio_word = "radio" if len(device_instances) == 1 else "radios"
    print(f"Connecting to {label} ({len(device_instances)} {radio_word})...")
    await controller.start()


async def main():
    if "--scan-only" in sys.argv:
        await scan_only()
    else:
        await connect_and_run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting.")
