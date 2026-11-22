"""Selettore della modalita' DoD."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOD_MODES, MODE_AI
from .entity import ZcsDodEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([ZcsDodModeSelect(entry)])


class ZcsDodModeSelect(ZcsDodEntity, SelectEntity, RestoreEntity):
    _attr_name = "DoD modalità"
    _attr_icon = "mdi:robot-outline"
    _attr_options = DOD_MODES

    def __init__(self, entry) -> None:
        super().__init__(entry, "dod_modalita")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        self.dod.mode = last.state if last and last.state in DOD_MODES else MODE_AI

    @property
    def current_option(self) -> str:
        return self.dod.mode

    async def async_select_option(self, option: str) -> None:
        self.dod.mode = option
        self.async_write_ha_state()
