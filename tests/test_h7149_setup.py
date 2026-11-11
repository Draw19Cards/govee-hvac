"""Set up an H7149 entry in a real HA instance and check every entity."""
from unittest.mock import patch

from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.govee_hvac.const import CONF_MODEL, DOMAIN
from custom_components.govee_hvac.h7149 import H7149State

from .conftest import H7149_ADDR

COORD = "custom_components.govee_hvac.coordinator.GoveeCoordinator"
STATE = H7149State(
    power=True,
    mode="auto",
    mist_level=9,
    target_humidity=60,
    auto_raw=b"\x02\xbc",
    current_temp_f=69.0,
    current_humidity=58.9,
    water_problem=True,
    fault_bits=0x20,
    light_on=True,
    light_brightness=67,
    light_rgb=(0, 253, 9),
)


async def test_h7149_entities_and_set_humidity(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=H7149_ADDR,
        title="GoveeLife H7149 Humidifier",
        data={CONF_ADDRESS: H7149_ADDR, CONF_MODEL: "H7149", "name": "GVH714970E1"},
    )
    entry.add_to_hass(hass)
    with patch(f"{COORD}._async_update_data", return_value=STATE), patch(
        "homeassistant.loader.Integration.dependencies", []
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    hum = hass.states.get("humidifier.goveelife_h7149_humidifier")
    assert hum.state == "on"
    assert hum.attributes["humidity"] == 60
    assert hum.attributes["current_humidity"] == 58.9
    assert hum.attributes["mode"] == "auto"
    assert hum.attributes["available_modes"] == ["auto", "manual"]
    assert (hum.attributes["min_humidity"], hum.attributes["max_humidity"]) == (40, 80)

    assert hass.states.get("number.goveelife_h7149_humidifier_mist_level").state == "9"
    light = hass.states.get("light.goveelife_h7149_humidifier_night_light")
    assert light.state == "on"
    assert light.attributes["brightness"] == round(67 * 255 / 100)
    assert light.attributes["color_mode"] == "rgb"
    assert tuple(light.attributes["rgb_color"]) == (0, 253, 9)
    tank = hass.states.get("binary_sensor.goveelife_h7149_humidifier_water_tank")
    assert tank.state == "on" and tank.attributes["fault_bits"] == "0x20"
    assert hass.states.get("sensor.goveelife_h7149_humidifier_humidity").state == "58.9"
    temp = hass.states.get("sensor.goveelife_h7149_humidifier_temperature")
    assert abs(float(temp.state) - 20.56) < 0.01  # 69.0 °F shown in the test's metric unit

    # set_humidity goes out as the hardware-verified auto command and keeps the
    # app's form (0x02 prefix) and low-level flag (0x80).
    with patch(f"{COORD}.async_command") as cmd:
        await hass.services.async_call(
            "humidifier",
            "set_humidity",
            {"entity_id": hum.entity_id, "humidity": 45},
            blocking=True,
        )
    assert cmd.call_args.args[0][:5] == bytes([0x33, 0x05, 0x03, 0x02, 0x80 | 45])

    # Setting a color sends the solid-color command (light already on -> no on cmd).
    with patch(f"{COORD}.async_command") as cmd:
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": light.entity_id, "rgb_color": [255, 0, 0]},
            blocking=True,
        )
    sent = [c.args[0][:9] for c in cmd.call_args_list]
    assert sent == [bytes.fromhex("3a1b050dff00000000")]

    assert await hass.config_entries.async_unload(entry.entry_id)
