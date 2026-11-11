"""Number entities for Govee HVAC devices."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
        async_add_entities([H7149MistLevel(coordinator, f"{entry.entry_id}_mist_level")])


class H7149MistLevel(GoveeEntity, NumberEntity):
    """Manual mist level 1-9. Setting it switches the humidifier to manual."""

    _attr_name = "Mist level"
    _attr_icon = "mdi:weather-fog"
    _attr_native_min_value = h7149.MIN_MIST_LEVEL
    _attr_native_max_value = h7149.MAX_MIST_LEVEL
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        return data.mist_level if data else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_command(h7149.make_mist_level(int(value)))
