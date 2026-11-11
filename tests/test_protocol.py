"""Offline protocol tests: packet bytes are the ones verified on real hardware."""
from custom_components.govee_hvac import h7149, h7151, transport
from custom_components.govee_hvac.const import model_from_local_name


def _head(pkt: bytes, n: int) -> str:
    return pkt[:n].hex(" ")


def test_frames_are_20_bytes_with_xor_checksum():
    pkt = transport.make_plain(0x33, 0x01, b"\x01")
    assert len(pkt) == 20
    assert transport.xor_checksum(pkt[:19]) == pkt[19]


def test_safe_crypt_round_trip():
    key = b"0123456789abcdef"
    pkt = h7151.make_humidity(55)
    assert transport.decrypt(transport.encrypt(pkt, key), key) == pkt


def test_h7151_commands():
    assert h7151.make_humidity(55).hex() == "3a05030000157c00000000000000000000000055"
    assert h7151.make_humidity(99)[5:7] == (8500).to_bytes(2, "big")  # clamped to 85%


# (packet, expected checksum) pairs below were sent to and accepted by an H7149.
def test_h7149_power_and_mist():
    assert _head(h7149.make_power(True), 3) == "33 01 01"
    assert h7149.make_power(True)[-1] == 0x33
    assert _head(h7149.make_mist_level(3), 4) == "33 05 01 03"
    assert h7149.make_mist_level(3)[-1] == 0x34
    assert _head(h7149.make_mist_level(12), 4) == "33 05 01 09"  # clamped


def test_h7149_auto_preserves_app_form_and_flag():
    assert _head(h7149.make_auto(50), 5) == "33 05 03 32 00"
    assert h7149.make_auto(50)[-1] == 0x07
    assert _head(h7149.make_auto(60, b"\x02\xbc"), 5) == "33 05 03 02 bc"
    assert h7149.make_auto(60, b"\x02\xbc")[-1] == 0x8B
    assert _head(h7149.make_auto(45, b"\x02\xbc"), 5) == "33 05 03 02 ad"


def test_h7149_night_light():
    assert _head(h7149.make_light_on(True), 5) == "3a 1b 01 01 01"
    assert h7149.make_light_on(True)[-1] == 0x20
    assert _head(h7149.make_light_brightness(100), 5) == "3a 1b 01 02 64"
    assert h7149.make_light_brightness(100)[-1] == 0x46


def test_h7149_decoders():
    assert h7149.decode_auto_target(b"\x02\xbc") == 60
    assert h7149.decode_auto_target(b"\x32\x00") == 50
    assert h7149.decode_thermo(bytes.fromhex("aa10810aa105")) == (69.6, 58.1)


def test_model_detection():
    assert model_from_local_name("GVH714970E1") == "H7149"
    assert model_from_local_name("ihoment_H7151_D215") == "H7151"
    assert model_from_local_name("GVH5075_ABCD") is None


def test_stale_disconnect_callback_does_not_wipe_live_session():
    class FakeClient:
        is_connected = True

    conn = transport.GoveeBleConnection()
    stale, live = FakeClient(), FakeClient()
    conn._client, conn._session_key = live, b"k"
    conn._on_disconnect(stale)
    assert conn.connected
    conn._on_disconnect(live)
    assert not conn.connected
