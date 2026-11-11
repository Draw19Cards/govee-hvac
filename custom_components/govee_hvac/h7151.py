"""GoveeLife H7151 Dehumidifier: command set and state decoding.

Rides on the shared encrypted transport in transport.py. See CLAUDE.md /
WRITEUP.md for the reverse-engineered command map.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .transport import GoveeBleConnection, make_plain

MODE_LOW = "low"
MODE_MEDIUM = "medium"
MODE_HIGH = "high"
MODE_AUTO = "auto"
MODE_DRYER = "dryer"
MODES = [MODE_LOW, MODE_MEDIUM, MODE_HIGH, MODE_AUTO, MODE_DRYER]

MIN_HUMIDITY = 35
MAX_HUMIDITY = 85


# ── Command builders ────────────────────────────────────────────────────────

def make_power(on: bool) -> bytes:
    return make_plain(0x33, 0x01, bytes([0x01 if on else 0x00]))


def make_fan(speed: int) -> bytes:
    return make_plain(0x3A, 0x05, bytes([0x01, speed]))


def make_humidity(pct: float) -> bytes:
    pct = max(float(MIN_HUMIDITY), min(float(MAX_HUMIDITY), pct))
    raw = int(round(pct * 100))
    return make_plain(0x3A, 0x05, bytes([0x03, 0x00, 0x00, (raw >> 8) & 0xFF, raw & 0xFF]))


def make_dryer() -> bytes:
    return make_plain(0x3A, 0x05, bytes([0x08, 0x01]))


# ── State ─────────────────────────────────────────────────────────────────────

@dataclass
class H7151State:
    power: bool
    mode: str
    fan_speed: int
    current_humidity: float
    current_temp_c: float
    target_humidity: float


def _decode_mode(mode_reg: int, fan_speed: int) -> str:
    if mode_reg == 0x03:
        return MODE_AUTO
    if mode_reg == 0x08:
        return MODE_DRYER
    return {1: MODE_LOW, 2: MODE_MEDIUM}.get(fan_speed, MODE_HIGH)


async def read_state(conn: GoveeBleConnection) -> H7151State:
    r1 = await conn.send(make_plain(0xAA, 0x01))
    if r1 is None:
        raise RuntimeError("No response to AA 01")
    power = bool(r1[2])
    th_raw = (r1[5] << 16) | (r1[6] << 8) | r1[7]
    current_temp_c = (th_raw // 1000) / 10.0
    current_humidity = (th_raw % 1000) / 10.0

    r_mode = await conn.send(make_plain(0xAA, 0x05, b"\x00"), match_len=3)
    mode_reg = r_mode[3] if r_mode is not None else 0x01

    r_fan = await conn.send(make_plain(0xAA, 0x05, b"\x01"), match_len=3)
    fan_speed = r_fan[3] if r_fan is not None else 0

    r_hum = await conn.send(make_plain(0xAA, 0x05, b"\x03"), match_len=3)
    target_humidity = 0.0
    if r_hum is not None:
        target_humidity = struct.unpack(">H", r_hum[5:7])[0] / 100.0

    return H7151State(
        power=power,
        mode=_decode_mode(mode_reg, fan_speed),
        fan_speed=fan_speed,
        current_humidity=current_humidity,
        current_temp_c=current_temp_c,
        target_humidity=target_humidity,
    )
