"""Entita' base."""
from __future__ import annotations

from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ZcsCoordinator


class ZcsEntity(CoordinatorEntity[ZcsCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, entry, key: str) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = entry.runtime_data.device


class ZcsDodEntity(Entity):
    """Entita' legate al gestore DoD (non al polling)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry, key: str) -> None:
        self._entry = entry
        self.dod = entry.runtime_data.dod
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = entry.runtime_data.device

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self.dod.signal, self.async_write_ha_state)
        )
