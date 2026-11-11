"""Config flow for Govee HVAC."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import CONF_MODEL, DOMAIN, MODEL_NAMES, SUPPORTED_MODELS, model_from_local_name


class GoveeHvacConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._address: str | None = None
        self._name: str | None = None
        self._model: str | None = None

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
            return self.async_create_entry(
                title=MODEL_NAMES[self._model],
                data={
                    CONF_ADDRESS: self._address,
                    CONF_MODEL: self._model,
                    "name": self._name,
                },
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": MODEL_NAMES[self._model]},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper()
            model = user_input[CONF_MODEL]
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=MODEL_NAMES[model],
                data={CONF_ADDRESS: address, CONF_MODEL: model, "name": model},
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Required(CONF_MODEL, default=SUPPORTED_MODELS[0]): vol.In(
                        {m: MODEL_NAMES[m] for m in SUPPORTED_MODELS}
                    ),
                }
            ),
        )
