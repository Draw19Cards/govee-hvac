<img src="icon.png" alt="Govee HVAC" width="96" align="right">

# Govee HVAC — Home Assistant Integration

Local Bluetooth control of GoveeLife climate devices. No cloud, no Govee account — works entirely over BLE.

<!-- ha-marketplace:exclude-start -->
[![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=Draw19Cards&repository=govee-hvac&category=integration)
<!-- ha-marketplace:exclude-end -->
[![Open your Home Assistant instance and start setting up Govee HVAC.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=govee_hvac)

## Supported devices

Only these two devices are supported:

| Model | Device |
|---|---|
| H7149 | GoveeLife Smart Humidifier |
| H7151 | GoveeLife Smart Dehumidifier |

Other Govee models aren't supported, and the integration won't offer to set them up, even when they look similar. Each model has its own command set (the H7151 is encrypted, the H7149 isn't), so every model has to be reverse-engineered and verified on real hardware.

### Adding a device

Pull requests adding support for more Govee climate devices are welcome. A new model is a protocol module (see [`h7149.py`](custom_components/govee_hvac/h7149.py) and [`h7151.py`](custom_components/govee_hvac/h7151.py)) plus a few registry entries. The checklist is in the `Adding a model` note at the top of [`const.py`](custom_components/govee_hvac/const.py). Please include tests in `tests/` and say which commands you verified on a real device.

## H7149 Humidifier

### Entities

| Entity | Type | Description |
|---|---|---|
| GoveeLife H7149 Humidifier | Humidifier | Power, mode (`auto` / `manual`), auto target humidity (40–80%) |
| Mist level | Number | Manual mist level 1–9 (switches to manual mode) |
| Night light | Light | On/off, brightness and RGB color |
| Water tank | Binary sensor (problem) | On when the tank is removed or out of water |
| Temperature | Sensor | Current temperature (reported by the device in °F; shown in your unit) |
| Humidity | Sensor | Current relative humidity |

Changing the target humidity keeps the auto-mode options set in the Govee app (such as "keep misting at a low level after reaching target"). The app's **Custom** schedule mode is shown when active but can't be selected from Home Assistant.

## H7151 Dehumidifier

### Features

- **All 5 modes**: Low, Medium, High, Auto (target humidity), Dryer
- **Real-time sensors**: current temperature (°C) and relative humidity
- **Target humidity control**: 35–85% in Auto mode

### Entities

| Entity | Type | Description |
|---|---|---|
| GoveeLife H7151 Dehumidifier | Humidifier | Main control (power, mode, target humidity) |
| Temperature | Sensor | Current room temperature in °C |
| Humidity | Sensor | Current relative humidity |

### Modes

| Mode | Behavior |
|---|---|
| `low` | Continuous, low fan speed |
| `medium` | Continuous, medium fan speed |
| `high` | Continuous, high fan speed |
| `auto` | Runs until target humidity reached, then pauses |
| `dryer` | High-output mode for drying clothes |

In `auto` mode, set the target humidity (35–85%) using the **Set Humidity** action or the humidifier card slider.

## Requirements

- Home Assistant 2024.1 or later (2026.3+ to show the integration's icon)
- A Bluetooth adapter or [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html) in range of the device
- The device powered on and within BLE range

<!-- ha-marketplace:exclude-start -->
## Installation

Add this repository in the Marketplace, or install it through HACS.

### Marketplace (Home Assistant 2026.11+)

Click the **Marketplace** button above, or:

1. Go to **Settings → Marketplace** → three-dot menu → **Custom repositories**
2. Paste `https://github.com/Draw19Cards/govee-hvac` and select type **Integration**
3. Search for **Govee HVAC** and click **Download**
4. Restart Home Assistant

On Home Assistant 2026.10 or older, use HACS the same way (**HACS → Integrations → Custom repositories**).

### Manual

Copy `custom_components/govee_hvac/` into your HA `config/custom_components/` directory, then restart Home Assistant.
<!-- ha-marketplace:exclude-end -->

### Upgrading from `govee_h7151` (v2.x)

v3.0 renamed the integration from `govee_h7151` to `govee_hvac`. Home Assistant treats it as a new integration:

1. Remove the old **Govee H7151 Dehumidifier** integration entry from **Settings → Devices & services**
2. Delete `config/custom_components/govee_h7151/` (or uninstall it from Marketplace/HACS)
3. Install Govee HVAC as above, restart, and add the device again

Entity IDs may change; update any automations or dashboards that referenced them.

## Configuration

The integration discovers supported devices automatically via Bluetooth. When a device is powered on:

1. A notification appears in **Settings → Devices & services**
2. Click **Configure** and confirm the device

You can also click the **Add integration** button above (or **Settings → Devices & services → Add Integration → Govee HVAC**). It lists every supported Govee device that Home Assistant's Bluetooth — local adapters and ESPHome proxies — has seen; pick yours. Entering a BLE address by hand is only a fallback, for a device HA hasn't picked up yet.

## Notes

- HA and the Govee app cannot control a device simultaneously — BLE is single-client, and this integration holds a persistent connection. Keep the Govee phone app away from the device for best reliability.
- The integration holds one BLE connection and reuses it across polls (every 30 seconds), reconnecting only if the link drops or stops answering. The device's single connection slot leaks in HA's Bluetooth stack if connections are repeatedly opened and closed, so connect-per-poll is not viable.
- A brief BLE hiccup doesn't flip entities to Unavailable: the last good state is kept for up to 3 consecutive failed polls (~90 s) while the link is rebuilt. Each failure is logged as a warning with the reason.
- For troubleshooting, enable debug logging:

  ```yaml
  logger:
    logs:
      custom_components.govee_hvac: debug
  ```

- H7151: mode state is queried explicitly each poll via the mode register. Water-tank status is **not** exposed: the device only signals it via a one-shot push notification, with no pollable register. (The H7149 does have a pollable fault register, so it gets a Water tank sensor.)

## Protocol

See [WRITEUP.md](WRITEUP.md) for a detailed writeup of the H7151 BLE protocol. The H7149's (unencrypted) command map is documented at the top of [`h7149.py`](custom_components/govee_hvac/h7149.py).

## License

Released into the public domain under [The Unlicense](LICENSE). Not affiliated with or endorsed by Govee.
