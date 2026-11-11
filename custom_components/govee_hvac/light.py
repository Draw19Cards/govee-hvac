"""Night light entity for Govee HVAC devices."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import h7149
from .const import DOMAIN, MODEL_H7149
from .coordinator import GoveeCoordinator
from .entity import GoveeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GoveeCoordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.model == MODEL_H7149:
        async_add_entities([H7149NightLight(coordinator, f"{entry.entry_id}_night_light")])


class H7149NightLight(GoveeEntity, LightEntity):
    """RGB night light: on/off, brightness (device 0-100 <-> HA 0-255), color."""

    _attr_name = "Night light"
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        return data.light_on if data else None

    @property
    def brightness(self) -> int | None:
        data = self.coordinator.data
        if not data or data.light_brightness is None:
            return None
        return round(data.light_brightness * 255 / 100)

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        data = self.coordinator.data
        return data.light_rgb if data else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_RGB_COLOR in kwargs:
            await self.coordinator.async_command(h7149.make_light_color(*kwargs[ATTR_RGB_COLOR]))
        if ATTR_BRIGHTNESS in kwargs:
            pct = max(1, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255))
            await self.coordinator.async_command(h7149.make_light_brightness(pct))
        if not (self.coordinator.data and self.coordinator.data.light_on):
            await self.coordinator.async_command(h7149.make_light_on(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(h7149.make_light_on(False))
