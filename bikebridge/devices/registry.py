from __future__ import annotations

from bikebridge.devices.base import BaseDevice
from bikebridge.devices.zwift_ride import ZwiftRide
from bikebridge.devices.zwift_click_v2 import ZwiftClickV2
from bikebridge.scanner import DiscoveredDevice


class DeviceRegistry:
    """Registry of known device drivers. Matches discovered BLE devices to drivers."""

    _drivers: list[type[BaseDevice]] = [
        ZwiftRide,
        ZwiftClickV2,
    ]

    @classmethod
    def register(cls, driver: type[BaseDevice]) -> None:
        cls._drivers.append(driver)

    @classmethod
    def identify(cls, device: DiscoveredDevice) -> type[BaseDevice] | None:
        for driver in cls._drivers:
            if driver.matches(device.name):
                return driver
        return None

    @classmethod
    def create(cls, device: DiscoveredDevice) -> BaseDevice | None:
        driver = cls.identify(device)
        if driver is None:
            return None
        return driver(device.address)

    @classmethod
    def all_drivers(cls) -> list[type[BaseDevice]]:
        return list(cls._drivers)
