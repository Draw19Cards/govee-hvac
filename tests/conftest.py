"""Shared fixtures for Govee HVAC tests."""
from types import SimpleNamespace

import pytest

H7149_ADDR = "98:17:3C:B4:70:E0"
H7151_ADDR = "AA:BB:CC:DD:EE:01"


def service_info(name: str, address: str) -> SimpleNamespace:
    """Minimal stand-in for BluetoothServiceInfoBleak (the flow reads name/address)."""
    return SimpleNamespace(name=name, address=address)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let HA load custom_components/govee_hvac in every test."""
    yield
