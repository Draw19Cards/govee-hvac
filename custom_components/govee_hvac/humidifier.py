"""Humidifier entities for Govee HVAC devices."""
from __future__ import annotations

from homeassistant.components.humidifier import (
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import h7149, h7151
from .const import DOMAIN, MODEL_H7149, MODEL_H7151
from .coordinator import GoveeCoordinator
from .entity import GoveeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GoveeCoordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.model == MODEL_H7151:
        async_add_entities([H7151Dehumidifier(coordinator, entry.entry_id)])
    elif coordinator.model == MODEL_H7149:
        async_add_entities([H7149Humidifier(coordinator, entry.entry_id)])


class H7149Humidifier(GoveeEntity, HumidifierEntity):
    """Auto (target humidity) / manual (mist level) humidifier."""

    _attr_device_class = HumidifierDeviceClass.HUMIDIFIER
    _attr_supported_features = HumidifierEntityFeature.MODES
    _attr_available_modes = h7149.SETTABLE_MODES
    _attr_min_humidity = h7149.MIN_HUMIDITY
    _attr_max_humidity = h7149.MAX_HUMIDITY
    _attr_name = None  # use the device name as the entity name

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        return data.power if data else None

    @property
    def mode(self) -> str | None:
        data = self.coordinator.data
        return data.mode if data else None

    @property
    def target_humidity(self) -> int | None:
        data = self.coordinator.data
        return data.target_humidity if data else None

    @property
    def current_humidity(self) -> float | None:
        data = self.coordinator.data
        return data.current_humidity if data else None

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_command(h7149.make_power(True))

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_command(h7149.make_power(False))

    async def async_set_mode(self, mode: str) -> None:
        data = self.coordinator.data
        if mode == h7149.MODE_MANUAL:
            level = (data.mist_level if data else None) or 5
            await self.coordinator.async_command(h7149.make_mist_level(level))
        elif mode == h7149.MODE_AUTO:
            target = (data.target_humidity if data else None) or h7149.DEFAULT_TARGET
            raw = data.auto_raw if data else b""
            await self.coordinator.async_command(h7149.make_auto(target, raw))

    async def async_set_humidity(self, humidity: int) -> None:
        data = self.coordinator.data
        raw = data.auto_raw if data else b""
        await self.coordinator.async_command(h7149.make_auto(humidity, raw))


class H7151Dehumidifier(GoveeEntity, HumidifierEntity):
    _attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER
    _attr_supported_features = HumidifierEntityFeature.MODES
    _attr_available_modes = h7151.MODES
    _attr_min_humidity = h7151.MIN_HUMIDITY
    _attr_max_humidity = h7151.MAX_HUMIDITY
    _attr_name = None  # use the device name as the entity name

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        return data.power if data else None

    @property
    def mode(self) -> str | None:
        data = self.coordinator.data
        return data.mode if data else None

    @property
    def target_humidity(self) -> int | None:
        data = self.coordinator.data
        return int(data.target_humidity) if data else None

    @property
    def current_humidity(self) -> float | None:
        data = self.coordinator.data
        return data.current_humidity if data else None

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_command(h7151.make_power(True))

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_command(h7151.make_power(False))

    async def async_set_mode(self, mode: str) -> None:
        if mode == h7151.MODE_LOW:
            await self.coordinator.async_command(h7151.make_fan(1))
        elif mode == h7151.MODE_MEDIUM:
            await self.coordinator.async_command(h7151.make_fan(2))
        elif mode == h7151.MODE_HIGH:
            await self.coordinator.async_command(h7151.make_fan(3))
        elif mode == h7151.MODE_AUTO:
            data = self.coordinator.data
            target = (data.target_humidity if data else 0) or 50.0
            await self.coordinator.async_command(h7151.make_humidity(target))
        elif mode == h7151.MODE_DRYER:
            await self.coordinator.async_command(h7151.make_dryer())

    async def async_set_humidity(self, humidity: int) -> None:
        await self.coordinator.async_command(h7151.make_humidity(float(humidity)))
