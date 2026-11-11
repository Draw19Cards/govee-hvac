"""Config flow tests: discovered-device picker, manual fallback, BT discovery."""
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.govee_hvac.const import CONF_MODEL, DOMAIN

from .conftest import H7149_ADDR, H7151_ADDR, service_info

DISCOVERED = "custom_components.govee_hvac.config_flow.async_discovered_service_info"


@pytest.fixture(autouse=True)
def no_setup():
    with patch("custom_components.govee_hvac.async_setup_entry", return_value=True):
        yield


async def _start_user_flow(hass, devices):
    with patch(DISCOVERED, return_value=devices):
        return await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )


def _options(result):
    return set(result["data_schema"].schema[CONF_ADDRESS].container)


async def test_picker_lists_discovered_and_creates_entry(hass):
    result = await _start_user_flow(
        hass,
        [
            service_info("GVH714970E1", H7149_ADDR),
            service_info("ihoment_H7151_D215", H7151_ADDR),
            service_info("SomeOtherThing", "11:22:33:44:55:66"),
        ],
    )
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    assert _options(result) == {H7149_ADDR, H7151_ADDR, "manual"}  # non-Govee filtered

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: H7149_ADDR}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "GoveeLife H7149 Humidifier"
    assert result["data"] == {
        CONF_ADDRESS: H7149_ADDR,
        CONF_MODEL: "H7149",
        "name": "GVH714970E1",
    }
    assert result["result"].unique_id == H7149_ADDR


async def test_picker_hides_configured_devices(hass):
    MockConfigEntry(domain=DOMAIN, unique_id=H7151_ADDR, data={}).add_to_hass(hass)
    result = await _start_user_flow(
        hass,
        [service_info("GVH714970E1", H7149_ADDR), service_info("H7151_X", H7151_ADDR)],
    )
    assert _options(result) == {H7149_ADDR, "manual"}


async def test_nothing_discovered_falls_back_to_manual(hass):
    result = await _start_user_flow(hass, [])
    assert result["step_id"] == "manual"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "aa:bb:cc:dd:ee:02 ", CONF_MODEL: "H7151"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ADDRESS] == "AA:BB:CC:DD:EE:02"
    assert result["data"][CONF_MODEL] == "H7151"


async def test_picker_manual_option_opens_manual_step(hass):
    result = await _start_user_flow(hass, [service_info("GVH714970E1", H7149_ADDR)])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "manual"}
    )
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "manual"


async def test_bluetooth_discovery_confirm(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=service_info("GVH714970E1", H7149_ADDR),
    )
    assert result["step_id"] == "bluetooth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MODEL] == "H7149"


async def test_bluetooth_discovery_unsupported_model(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=service_info("GVH5075_ABCD", "11:22:33:44:55:66"),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"
