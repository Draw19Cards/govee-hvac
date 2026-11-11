"""GoveeLife H7149 Smart Humidifier: command set and state decoding.

Plaintext (unencrypted) Govee framing on the shared 2b10/2b11 characteristics.
The H7149's own app module is an on-demand Play split we couldn't obtain; this
map was built from the shared base_h71xx constants plus live verification on a
real unit (2026-11-11): every write below was confirmed by read-back and on
the physical device.

Reads (AA ...):
  AA 01      [2] power (0/1)
  AA 05 00   [3] mode: 0x01 manual (gear), 0x02 custom, 0x03 auto
  AA 05 01   [3] manual mist level 1-9
  AA 05 03   auto settings; two observed forms:
               [3]=target|flag            (as written by 33 05 03 <t>)
               [3]=0x02 [4]=target|flag   (as set by the app)
             flag 0x80 = keep misting at low level once the target is reached
  AA 10      [2] 0x81 status, [3:6] 24-bit packed temp/humidity:
               value = temp_tenths * 1000 + humidity_tenths, temp in °F
  AA 17      fault bits; [3] 0x20 = water tank removed / out of water
  AA 1B 01   night light: [3] on (0/1), [4] brightness 0-100
  AA 1B 05   night light mode: [3] 0x0D solid color -> [4:7] R G B, [7:9] kelvin
             (0x13 = scene, 0x0A = DIY; not exposed)
Writes:
  33 01 <0|1>          power
  33 05 01 <1-9>       manual mode at mist level
  33 05 03 <auto...>   auto mode with target (same layout as the AA 05 03 read)
  3A 1B 01 01 <0|1>    night light on/off
  3A 1B 01 02 <0-100>  night light brightness
  3A 1B 05 0D R G B 00 00  night light solid color
"""
from __future__ import annotations

from dataclasses import dataclass

from .transport import GoveeBleConnection, make_plain

MODE_MANUAL = "manual"
MODE_CUSTOM = "custom"
MODE_AUTO = "auto"
# Custom mode is reported but not settable (its schedule format is unknown).
SETTABLE_MODES = [MODE_AUTO, MODE_MANUAL]

MIN_MIST_LEVEL = 1
MAX_MIST_LEVEL = 9
MIN_HUMIDITY = 40
MAX_HUMIDITY = 80  # 90 with the app's "Humidity Unlock"; kept at the default cap

_MODE_BY_REG = {0x01: MODE_MANUAL, 0x02: MODE_CUSTOM, 0x03: MODE_AUTO}
_LOW_LEVEL_FLAG = 0x80
DEFAULT_TARGET = 50


# ── Command builders ────────────────────────────────────────────────────────

def make_power(on: bool) -> bytes:
    return make_plain(0x33, 0x01, bytes([0x01 if on else 0x00]))


def make_mist_level(level: int) -> bytes:
    level = max(MIN_MIST_LEVEL, min(MAX_MIST_LEVEL, int(level)))
    return make_plain(0x33, 0x05, bytes([0x01, level]))


def make_auto(target: float, auto_raw: bytes = b"") -> bytes:
    """Enter auto mode at ``target``%, preserving the app's auto settings.

    ``auto_raw`` is the current AA 05 03 payload (bytes [3:5]); its form and
    low-level flag are kept so changing the target from HA doesn't silently
    reset options chosen in the Govee app.
    """
    target = max(MIN_HUMIDITY, min(MAX_HUMIDITY, int(round(target))))
    if len(auto_raw) >= 2 and 0 < auto_raw[0] < 0x10:
        payload = bytes([auto_raw[0], (auto_raw[1] & _LOW_LEVEL_FLAG) | target])
    else:
        flag = auto_raw[0] & _LOW_LEVEL_FLAG if auto_raw else 0
        payload = bytes([flag | target])
    return make_plain(0x33, 0x05, bytes([0x03]) + payload)


def make_light_on(on: bool) -> bytes:
    return make_plain(0x3A, 0x1B, bytes([0x01, 0x01, 0x01 if on else 0x00]))


def make_light_brightness(brightness: int) -> bytes:
    brightness = max(0, min(100, int(brightness)))
    return make_plain(0x3A, 0x1B, bytes([0x01, 0x02, brightness]))


_LIGHT_COLOR_MODE = 0x0D


def make_light_color(red: int, green: int, blue: int) -> bytes:
    rgb = [max(0, min(255, int(c))) for c in (red, green, blue)]
    return make_plain(0x3A, 0x1B, bytes([0x05, _LIGHT_COLOR_MODE, *rgb, 0x00, 0x00]))


# ── State ─────────────────────────────────────────────────────────────────────

@dataclass
class H7149State:
    power: bool
    mode: str | None
    mist_level: int | None
    target_humidity: int | None
    auto_raw: bytes
    current_temp_f: float | None
    current_humidity: float | None
    water_problem: bool | None
    fault_bits: int | None
    light_on: bool | None
    light_brightness: int | None
    light_rgb: tuple[int, int, int] | None = None  # None when a scene/DIY is active


def decode_light_rgb(resp: bytes) -> tuple[int, int, int] | None:
    if resp[3] != _LIGHT_COLOR_MODE:
        return None
    return (resp[4], resp[5], resp[6])


def decode_auto_target(auto_raw: bytes) -> int | None:
    if not auto_raw:
        return None
    if 0 < auto_raw[0] < 0x10 and len(auto_raw) >= 2:
        target = auto_raw[1] & 0x7F
    else:
        target = auto_raw[0] & 0x7F
    return target or None


def decode_thermo(resp: bytes) -> tuple[float | None, float | None]:
    raw = (resp[3] << 16) | (resp[4] << 8) | resp[5]
    if raw == 0:
        return None, None
    return (raw // 1000) / 10.0, (raw % 1000) / 10.0


async def read_state(conn: GoveeBleConnection) -> H7149State:
    r_power = await conn.send(make_plain(0xAA, 0x01))
    if r_power is None:
        raise RuntimeError("No response to AA 01")

    r_mode = await conn.send(make_plain(0xAA, 0x05, b"\x00"), match_len=3)
    r_gear = await conn.send(make_plain(0xAA, 0x05, b"\x01"), match_len=3)
    r_auto = await conn.send(make_plain(0xAA, 0x05, b"\x03"), match_len=3)
    r_thermo = await conn.send(make_plain(0xAA, 0x10))
    r_fault = await conn.send(make_plain(0xAA, 0x17))
    r_light = await conn.send(make_plain(0xAA, 0x1B, b"\x01"), match_len=3)
    r_light_mode = await conn.send(make_plain(0xAA, 0x1B, b"\x05"), match_len=3)

    auto_raw = bytes(r_auto[3:5]) if r_auto is not None else b""
    temp_f, humidity = decode_thermo(r_thermo) if r_thermo is not None else (None, None)
    fault_bits = r_fault[3] if r_fault is not None else None

    return H7149State(
        power=bool(r_power[2]),
        mode=_MODE_BY_REG.get(r_mode[3]) if r_mode is not None else None,
        mist_level=r_gear[3] or None if r_gear is not None else None,
        target_humidity=decode_auto_target(auto_raw),
        auto_raw=auto_raw,
        current_temp_f=temp_f,
        current_humidity=humidity,
        water_problem=bool(fault_bits & 0x20) if fault_bits is not None else None,
        fault_bits=fault_bits,
        light_on=bool(r_light[3]) if r_light is not None else None,
        light_brightness=r_light[4] if r_light is not None else None,
        light_rgb=decode_light_rgb(r_light_mode) if r_light_mode is not None else None,
    )
