"""Sensor entities for Govee HVAC devices."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MODEL_H7149, MODEL_H7151
from .coordinator import GoveeCoordinator
from .entity import GoveeEntity


@dataclass(frozen=True, kw_only=True)
class GoveeSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Any], float | None]


TEMPERATURE = GoveeSensorDescription(
    key="temperature",
    device_class=SensorDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    state_class=SensorStateClass.MEASUREMENT,
    name="Temperature",
    value_fn=lambda data: data.current_temp_c,
)
HUMIDITY = GoveeSensorDescription(
    key="humidity",
    device_class=SensorDeviceClass.HUMIDITY,
    native_unit_of_measurement=PERCENTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    name="Humidity",
    value_fn=lambda data: data.current_humidity,
)

# The H7149 reports temperature in °F; HA converts to the user's unit.
TEMPERATURE_F = GoveeSensorDescription(
    key="temperature",
    device_class=SensorDeviceClass.TEMPERATURE,
    native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
    state_class=SensorStateClass.MEASUREMENT,
    name="Temperature",
    value_fn=lambda data: data.current_temp_f,
)

# Model -> sensors it exposes.
MODEL_SENSORS: dict[str, tuple[GoveeSensorDescription, ...]] = {
    MODEL_H7149: (TEMPERATURE_F, HUMIDITY),
    MODEL_H7151: (TEMPERATURE, HUMIDITY),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GoveeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GoveeSensor(coordinator, entry.entry_id, desc)
        for desc in MODEL_SENSORS.get(coordinator.model, ())
    )


class GoveeSensor(GoveeEntity, SensorEntity):
    entity_description: GoveeSensorDescription

    def __init__(
        self,
        coordinator: GoveeCoordinator,
        entry_id: str,
        description: GoveeSensorDescription,
    ) -> None:
        super().__init__(coordinator, f"{entry_id}_{description.key}")
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        return self.entity_description.value_fn(data) if data else None
