"""Constants and the model registry for Govee HVAC.

Adding a model:
  1. Write a protocol module `<model>.py` (command builders, a state
     dataclass, and `async read_state(conn)`); see h7149.py / h7151.py.
  2. Register it here: MODEL_<X>, MODEL_NAMES, MODEL_ENCRYPTED.
  3. coordinator.STATE_READERS: map the model to its read_state.
  4. __init__.MODEL_PLATFORMS: the platforms it exposes, then add its
     entities to those platform files (humidifier.py, sensor.py, ...).
  5. manifest.json `bluetooth`: a local_name matcher for its advertisement.
  6. Tests in tests/: builder bytes verified on hardware, plus entity setup.
"""

DOMAIN = "govee_hvac"

CONF_MODEL = "model"

MODEL_H7149 = "H7149"
MODEL_H7151 = "H7151"

# Model -> human-readable device name.
MODEL_NAMES: dict[str, str] = {
    MODEL_H7149: "GoveeLife H7149 Humidifier",
    MODEL_H7151: "GoveeLife H7151 Dehumidifier",
}

# Model -> whether the BLE link is AES/RC4-encrypted after a key exchange.
MODEL_ENCRYPTED: dict[str, bool] = {
    MODEL_H7149: False,
    MODEL_H7151: True,
}
SUPPORTED_MODELS = tuple(MODEL_NAMES)


def model_from_local_name(local_name: str | None) -> str | None:
    """Extract a supported model from a BLE local name (e.g. 'ihoment_H7151_1A2B')."""
    if not local_name:
        return None
    upper = local_name.upper()
    for model in SUPPORTED_MODELS:
        if model in upper:
            return model
    return None
