"""Timer-based BLE coordinator for Govee HVAC devices.

These devices advertise too infrequently for HA's passive scanner to deliver
reliable advertisement callbacks (verified on the H7151: the device is
reachable for connection and appears under an active scan, but HA receives no
usable advertisement stream). An advertisement-driven coordinator therefore
never polls. We instead poll on a fixed interval, resolving the BLEDevice from
HA's connectable history, over a persistent connection.

Robustness:
- establish_connection() (with retries) participates in habluetooth's slot
  accounting and rides through transient single-connection collisions.
- Every exchange is bounded by OP_TIMEOUT so a hung BLE call can never wedge
  the poll loop or hold the lock indefinitely.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import h7149, h7151
from .const import DOMAIN, MODEL_ENCRYPTED, MODEL_H7149, MODEL_H7151
from .transport import GoveeBleConnection

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 30
# Hard ceiling on a full (re)connect + exchange so a hung BLE call can never
# wedge the poll loop or hold the connection lock indefinitely. Kept below the
# poll interval so polls never pile up.
OP_TIMEOUT = 25
# Consecutive failed polls tolerated (serving the last good state) before the
# entities go Unavailable: 3 × 30s ≈ 90s of grace for transient BLE blips.
FAILURE_TOLERANCE = 3

# Model -> coroutine that reads the full device state over a connection.
STATE_READERS: dict[str, Callable[[GoveeBleConnection], Awaitable[Any]]] = {
    MODEL_H7149: h7149.read_state,
    MODEL_H7151: h7151.read_state,
}


class GoveeCoordinator(DataUpdateCoordinator[Any]):
    """Polls a Govee HVAC device over BLE on a fixed interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        address: str,
        name: str,
        model: str,
    ) -> None:
        super().__init__(
            hass,
            logger,
            name=DOMAIN,
            update_interval=timedelta(seconds=POLL_INTERVAL_SECONDS),
        )
        self.address = address
        self.device_name = name
        self.model = model
        self._read_state = STATE_READERS[model]
        self._conn = GoveeBleConnection(
            ble_device_callback=self._ble_device, encrypted=MODEL_ENCRYPTED[model]
        )
        self._lock = asyncio.Lock()
        self._consecutive_failures = 0

    def _ble_device(self):
        """Resolve a BLEDevice from HA's history, preferring a connectable one."""
        return bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        ) or bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=False
        )

    async def _async_update_data(self) -> Any:
        try:
            ble_device = self._ble_device()
            if ble_device is None:
                raise RuntimeError(
                    "not in HA's Bluetooth history — is it powered on and in "
                    "range of an adapter or proxy?"
                )
            async with self._lock:
                async with asyncio.timeout(OP_TIMEOUT):
                    await self._conn.ensure(ble_device)
                    self._conn.drain()
                    state = await self._read_state(self._conn)
        except Exception as err:
            return await self._handle_poll_failure(err)

        if self._consecutive_failures:
            _LOGGER.info(
                "%s recovered after %d failed poll(s)",
                self.device_name,
                self._consecutive_failures,
            )
        self._consecutive_failures = 0
        return state

    async def _handle_poll_failure(self, err: Exception) -> Any:
        """Reset the link; ride through brief blips before going unavailable.

        A single dropped response used to flip every entity to Unavailable for a
        full poll interval. Keep the last good state for a few consecutive
        failures (each one tears the link down so the next poll reconnects
        fresh), and only report unavailable if the device stays unreachable.
        """
        async with self._lock:
            await self._conn.reset()
        self._consecutive_failures += 1
        reason = _describe(err)
        if self.data is not None and self._consecutive_failures < FAILURE_TOLERANCE:
            _LOGGER.warning(
                "Poll %d/%d of %s failed (%s); keeping last state and reconnecting",
                self._consecutive_failures,
                FAILURE_TOLERANCE,
                self.device_name,
                reason,
            )
            return self.data
        raise UpdateFailed(
            f"{self.device_name} ({self.address}) unreachable after "
            f"{self._consecutive_failures} attempt(s): {reason}"
        ) from err

    async def async_disconnect(self) -> None:
        """Release the held BLE connection (called on unload)."""
        await self._conn.stop()

    async def async_command(self, plain: bytes) -> None:
        """Send a command, read back the state, and publish it immediately."""
        ble_device = self._ble_device()
        if ble_device is None:
            raise HomeAssistantError(f"{self.device_name} is not in range")
        async with self._lock:
            try:
                async with asyncio.timeout(OP_TIMEOUT):
                    await self._conn.ensure(ble_device)
                    self._conn.drain()
                    await self._conn.send(plain)
                    await asyncio.sleep(0.3)
                    state = await self._read_state(self._conn)
            except Exception as err:
                await self._conn.reset()
                raise HomeAssistantError(
                    f"Command to {self.device_name} failed: {_describe(err)}"
                ) from err
        self._consecutive_failures = 0
        # Publish the post-command state immediately for snappy UI feedback.
        self.async_set_updated_data(state)


def _describe(err: BaseException) -> str:
    """Readable error text; TimeoutError and friends have an empty str()."""
    if isinstance(err, TimeoutError):
        return f"timed out after {OP_TIMEOUT}s"
    return f"{type(err).__name__}: {err}" if str(err) else type(err).__name__
