"""Govee HVAC integration: local BLE control of GoveeLife climate devices."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_MODEL, DOMAIN, MODEL_H7149, MODEL_H7151
from .coordinator import GoveeCoordinator

_LOGGER = logging.getLogger(__name__)

# Platforms each model exposes.
MODEL_PLATFORMS: dict[str, list[Platform]] = {
    MODEL_H7149: [
        Platform.BINARY_SENSOR,
        Platform.HUMIDIFIER,
        Platform.LIGHT,
        Platform.NUMBER,
        Platform.SENSOR,
    ],
    MODEL_H7151: [Platform.HUMIDIFIER, Platform.SENSOR],
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    model: str = entry.data.get(CONF_MODEL, MODEL_H7151)
    coordinator = GoveeCoordinator(
        hass,
        _LOGGER,
        entry.data[CONF_ADDRESS],
        entry.data.get("name", model),
        model,
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, MODEL_PLATFORMS[model])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    model: str = entry.data.get(CONF_MODEL, MODEL_H7151)
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, MODEL_PLATFORMS[model]
    )
    if unload_ok:
        coordinator: GoveeCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_disconnect()
    return unload_ok
