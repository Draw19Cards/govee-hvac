"""Config flow for Govee HVAC."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import CONF_MODEL, DOMAIN, MODEL_NAMES, SUPPORTED_MODELS, model_from_local_name

MANUAL_ENTRY = "manual"


class GoveeHvacConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._address: str | None = None
        self._name: str | None = None
        self._model: str | None = None
        # address -> (model, local name) for devices offered in the picker
        self._discovered: dict[str, tuple[str, str]] = {}

    # ── Automatic Bluetooth discovery ────────────────────────────────────────

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        model = model_from_local_name(discovery_info.name)
        if model is None:
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self._model = model
        self._name = discovery_info.name or model
        self.context["title_placeholders"] = {"name": MODEL_NAMES[model]}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._model is not None
        if user_input is not None:
            return self._create_entry(self._address, self._model, self._name)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": MODEL_NAMES[self._model]},
        )

    # ── User-initiated: pick from devices HA's Bluetooth has seen ────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address == MANUAL_ENTRY:
                return await self.async_step_manual()
            model, name = self._discovered[address]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self._create_entry(address, model, name)

        configured = self._async_current_ids(include_ignore=False)
        # connectable=False also includes devices only seen by passive
        # scanners / proxies; history covers devices that advertise rarely.
        for info in async_discovered_service_info(self.hass, connectable=False):
            model = model_from_local_name(info.name)
            if model and info.address not in configured:
                self._discovered[info.address] = (model, info.name or model)

        if not self._discovered:
            return await self.async_step_manual()

        options = {
            address: f"{MODEL_NAMES[model]} ({name}, {address})"
            for address, (model, name) in self._discovered.items()
        }
        options[MANUAL_ENTRY] = "Enter address manually…"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(options)}),
        )

    # ── Fallback: manual address entry ───────────────────────────────────────

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            model = user_input[CONF_MODEL]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self._create_entry(address, model, model)
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Required(CONF_MODEL, default=SUPPORTED_MODELS[0]): vol.In(
                        {m: MODEL_NAMES[m] for m in SUPPORTED_MODELS}
                    ),
                }
            ),
        )

    def _create_entry(self, address: str | None, model: str, name: str | None) -> ConfigFlowResult:
        return self.async_create_entry(
            title=MODEL_NAMES[model],
            data={CONF_ADDRESS: address, CONF_MODEL: model, "name": name or model},
        )
