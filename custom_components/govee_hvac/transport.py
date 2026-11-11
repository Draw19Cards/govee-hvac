"""Shared Govee BLE transport: encryption, framing, key exchange, connection.

Every supported Govee HVAC device speaks the same encrypted transport (from
Safe.java / Controller4Aes.java in the Govee APK); only the command set on top
differs per model. No Home Assistant dependencies so it can be reasoned about
(and tested) on its own.
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)

SEND_UUID = "00010203-0405-0607-0809-0a0b0c0d2b11"
RECV_UUID = "00010203-0405-0607-0809-0a0b0c0d2b10"
PRODUCT_KEY = b"MakingLifeSmarte"

# These devices allow only one BLE connection and drop it readily, so a single
# connect attempt often loses a race against another client (e.g. the Govee
# phone app). Retry a few times so a poll/command rides through a transient
# collision. Bounded overall by the coordinator's operation timeout.
CONNECT_ATTEMPTS = 3
# Upper bound on a cleanup disconnect, so a wedged link can't stall recovery.
DISCONNECT_TIMEOUT = 5


# ── Crypto ────────────────────────────────────────────────────────────────────

def _aes_ecb(key: bytes, block: bytes, *, decrypt: bool) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    worker = cipher.decryptor() if decrypt else cipher.encryptor()
    return worker.update(block) + worker.finalize()


def _rc4(key: bytes, data: bytes) -> bytes:
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) % 256
        s[i], s[j] = s[j], s[i]
    out, i, j = bytearray(), 0, 0
    for byte in data:
        i = (i + 1) & 255
        j = (j + s[i]) & 255
        s[i], s[j] = s[j], s[i]
        out.append(s[(s[i] + s[j]) & 255] ^ byte)
    return bytes(out)


def _safe_crypt(data: bytes, key: bytes, *, decrypt: bool) -> bytes:
    """AES/ECB on each 16-byte block; RC4 on the remainder."""
    out, i = bytearray(), 0
    while i + 16 <= len(data):
        out.extend(_aes_ecb(key, data[i:i + 16], decrypt=decrypt))
        i += 16
    if i < len(data):
        out.extend(_rc4(key, data[i:]))
    return bytes(out)


def encrypt(data: bytes, key: bytes) -> bytes:
    return _safe_crypt(data, key, decrypt=False)


def decrypt(data: bytes, key: bytes) -> bytes:
    return _safe_crypt(data, key, decrypt=True)


# ── Packet framing ──────────────────────────────────────────────────────────

def xor_checksum(data: bytes) -> int:
    r = 0
    for b in data:
        r ^= b
    return r


def make_plain(prefix: int, cmd: int, payload: bytes = b"") -> bytes:
    """Build a 20-byte plaintext packet: [prefix, cmd, payload..., checksum]."""
    body = bytearray([prefix, cmd])
    body.extend(payload[:17])
    body.extend(b"\x00" * (19 - len(body)))
    body.append(xor_checksum(body))
    return bytes(body)


# ── Key exchange ────────────────────────────────────────────────────────────

async def _key_exchange(client: BleakClient, queue: asyncio.Queue[bytes]) -> bytes:
    """E7 01 / E7 02 handshake; returns the 16-byte session key."""
    loop = asyncio.get_running_loop()

    tx1 = bytearray([0xE7, 0x01]) + os.urandom(17)
    tx1.append(xor_checksum(tx1))
    await client.write_gatt_char(SEND_UUID, encrypt(bytes(tx1), PRODUCT_KEY), response=False)

    session_key: bytes | None = None
    deadline = loop.time() + 6.0
    while loop.time() < deadline:
        try:
            enc = await asyncio.wait_for(queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        plain = decrypt(enc, PRODUCT_KEY)
        if plain[0] == 0xE7 and plain[1] == 0x01:
            session_key = bytes(plain[2:18])
            break
    if not session_key:
        raise RuntimeError("Key exchange failed: no session key received")

    tx2 = bytearray([0xE7, 0x02]) + os.urandom(17)
    tx2.append(xor_checksum(tx2))
    await client.write_gatt_char(SEND_UUID, encrypt(bytes(tx2), PRODUCT_KEY), response=False)

    deadline = loop.time() + 6.0
    while loop.time() < deadline:
        try:
            enc = await asyncio.wait_for(queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        plain = decrypt(enc, PRODUCT_KEY)
        if plain[0] == 0xE7 and plain[1] == 0x02:
            break

    await asyncio.sleep(0.3)
    while not queue.empty():
        queue.get_nowait()
    return session_key


# ── Connection ──────────────────────────────────────────────────────────────

class GoveeBleConnection:
    """Persistent-connection BLE client for a Govee HVAC device.

    Holds a single connection and reuses it across polls/commands. These devices
    have only one connection slot and HA's slot accounting leaks if the slot is
    repeatedly acquired and released (connect-per-poll), so we acquire it once
    and only reconnect when the link actually drops. Each (re)connection
    negotiates a fresh session key.
    """

    def __init__(
        self,
        ble_device_callback: Callable[[], BLEDevice | None] | None = None,
        *,
        encrypted: bool = True,
    ) -> None:
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._client: BleakClient | None = None
        self._session_key: bytes | None = None
        # Newer models (H7151) encrypt every packet after a key exchange; older
        # ones (H7149) speak the same framing in plaintext.
        self._encrypted = encrypted
        # Lets establish_connection re-resolve the best path (local adapter vs.
        # an ESPHome proxy) between retries instead of reusing a stale one.
        self._ble_device_callback = ble_device_callback

    def _on_disconnect(self, client: BleakClient) -> None:
        # Only react to the *current* client. A late callback from an older
        # (replaced or orphaned) client must not wipe a live session — doing so
        # forces a reconnect while the real link is still up, orphaning it and
        # filling the device's single connection slot.
        if client is not self._client:
            _LOGGER.debug("Ignoring disconnect callback from a stale client")
            return
        _LOGGER.debug("Device disconnected")
        self._client = None
        self._session_key = None

    @property
    def connected(self) -> bool:
        return (
            self._client is not None
            and self._client.is_connected
            and self._session_key is not None
        )

    def drain(self) -> None:
        """Discard any queued notifications (stale responses, pushes)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def ensure(self, ble_device: BLEDevice) -> None:
        """Connect and key-exchange if not already connected."""
        if self.connected:
            return
        # Tear down any half-dead previous client before opening a new one, so
        # we never hold two links to a single-slot device.
        await self.reset()
        self.drain()
        _LOGGER.debug("Connecting to %s via %s", ble_device.address, _path(ble_device))
        client = await establish_connection(
            BleakClient,
            ble_device,
            ble_device.address,
            disconnected_callback=self._on_disconnect,
            max_attempts=CONNECT_ATTEMPTS,
            ble_device_callback=(
                (lambda: self._ble_device_callback() or ble_device)
                if self._ble_device_callback
                else None
            ),
        )
        try:
            await client.start_notify(
                RECV_UUID, lambda _, d: self._queue.put_nowait(bytes(d))
            )
            await asyncio.sleep(0.1)
            # Plaintext models use an empty key as the "keyed" marker.
            session_key = (
                await _key_exchange(client, self._queue) if self._encrypted else b""
            )
        except BaseException:
            # The link is up but unusable (key exchange failed or we were
            # cancelled by the operation timeout). Release it, otherwise this
            # orphaned client keeps the device's only connection slot and every
            # later connect fails until the stack eventually reaps it.
            await _safe_disconnect(client)
            raise
        self._client, self._session_key = client, session_key
        _LOGGER.debug("Connected and keyed to %s", ble_device.address)

    async def reset(self) -> None:
        """Drop the current connection (if any) so the next op reconnects fresh.

        Called after any failed exchange: a link that reports connected but has
        stopped answering would otherwise be reused, and fail, forever.
        """
        client, self._client, self._session_key = self._client, None, None
        if client is not None:
            await _safe_disconnect(client)

    async def send(self, plain: bytes, match_len: int = 2) -> bytes | None:
        """Write a packet and return the matching response, or None on timeout.

        The response is matched on its first ``match_len`` bytes. Commands that
        share a prefix+cmd but differ by subcommand (e.g. AA 05 xx) should use
        match_len=3 to avoid consuming a stale sibling response.
        """
        if self._client is None or self._session_key is None:
            raise RuntimeError("Not connected")
        client, key = self._client, self._session_key
        wire = encrypt(plain, key) if key else plain
        await client.write_gatt_char(SEND_UUID, wire, response=False)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 3.0
        while loop.time() < deadline:
            remaining = deadline - loop.time()
            try:
                enc = await asyncio.wait_for(self._queue.get(), timeout=max(0.1, remaining))
            except asyncio.TimeoutError:
                break
            resp = decrypt(enc, key) if key else enc
            if resp[:match_len] == plain[:match_len]:
                return resp
        return None

    async def stop(self) -> None:
        """Disconnect and release the connection (called on unload)."""
        await self.reset()


def _path(ble_device: BLEDevice) -> str:
    """Best-effort name of the adapter/proxy a BLEDevice resolves through."""
    details = ble_device.details
    if isinstance(details, dict):
        return str(details.get("source") or details.get("path") or "unknown")
    return "unknown"


async def _safe_disconnect(client: BleakClient) -> None:
    """Disconnect, bounded and never raising (best-effort cleanup)."""
    try:
        async with asyncio.timeout(DISCONNECT_TIMEOUT):
            await client.disconnect()
    except Exception as err:  # pragma: no cover - best effort cleanup
        _LOGGER.debug("disconnect error (ignored): %r", err)
