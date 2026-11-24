"""Entità base (sola lettura)."""
from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ImmergasCoordinator


class ImmergasEntity(CoordinatorEntity[ImmergasCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, entry, key: str) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = entry.runtime_data.device
