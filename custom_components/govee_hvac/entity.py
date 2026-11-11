"""Shared entity base for Govee HVAC devices."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODEL_NAMES
from .coordinator import GoveeCoordinator


class GoveeEntity(CoordinatorEntity[GoveeCoordinator]):
    """Base entity: shared device info and availability."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GoveeCoordinator, unique_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = unique_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=MODEL_NAMES[coordinator.model],
            manufacturer="GoveeLife",
            model=coordinator.model,
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None
