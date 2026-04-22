from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData


@dataclass
class DiscoveredDevice:
    name: str
    address: str
    rssi: int
    raw_device: BLEDevice
    raw_adv: AdvertisementData

    def __str__(self) -> str:
        return f"{self.name} [{self.address}] RSSI: {self.rssi}"


class Scanner:
    """Scans for BLE devices. Can filter by name or return everything."""

    async def scan_all(self, timeout: float = 10.0) -> list[DiscoveredDevice]:
        devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
        results = []
        for _addr, (dev, adv) in devices.items():
            name = dev.name or adv.local_name or "(unknown)"
            results.append(DiscoveredDevice(
                name=name,
                address=dev.address,
                rssi=adv.rssi,
                raw_device=dev,
                raw_adv=adv,
            ))
        results.sort(key=lambda d: d.rssi, reverse=True)
        return results

    async def scan_for(
        self,
        name_filter: str,
        timeout: float = 15.0,
    ) -> DiscoveredDevice | None:
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: d.name is not None and name_filter in d.name,
            timeout=timeout,
        )
        if device is None:
            return None
        return DiscoveredDevice(
            name=device.name or name_filter,
            address=device.address,
            rssi=0,
            raw_device=device,
            raw_adv=None,  # type: ignore[arg-type]
        )

    async def scan_with_callback(
        self,
        callback: Callable[[DiscoveredDevice], None],
        timeout: float = 10.0,
    ) -> None:
        """Stream devices as they're found rather than waiting for full scan."""
        seen: set[str] = set()

        def _detection(device: BLEDevice, adv: AdvertisementData) -> None:
            if device.address in seen:
                return
            seen.add(device.address)
            name = device.name or adv.local_name or "(unknown)"
            callback(DiscoveredDevice(
                name=name,
                address=device.address,
                rssi=adv.rssi,
                raw_device=device,
                raw_adv=adv,
            ))

        scanner = BleakScanner(detection_callback=_detection)
        await scanner.start()
        await asyncio.sleep(timeout)
        await scanner.stop()
