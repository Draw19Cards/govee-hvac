"""Binary sensors for Govee HVAC devices."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MODEL_H7149
from .coordinator import GoveeCoordinator
from .entity import GoveeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GoveeCoordinator = hass.data[DOMAIN][entry.entry_id]
    # Only the H7149 exposes a pollable fault register; the H7151's tank state
    # is push-only (see CLAUDE.md), so it gets no tank entity.
    if coordinator.model == MODEL_H7149:
        async_add_entities([H7149WaterTank(coordinator, f"{entry.entry_id}_water_tank")])


class H7149WaterTank(GoveeEntity, BinarySensorEntity):
    """On (problem) when the tank is removed or out of water (AA 17 bit 0x20)."""

    _attr_name = "Water tank"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:water-alert"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        return data.water_problem if data else None

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        data = self.coordinator.data
        if not data or data.fault_bits is None:
            return None
        return {"fault_bits": f"0x{data.fault_bits:02x}"}
