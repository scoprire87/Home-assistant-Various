"""Interruttore 'solo simulazione' del DoD automatico."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import ZcsDodEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([ZcsSimulationSwitch(entry)])


class ZcsSimulationSwitch(ZcsDodEntity, SwitchEntity, RestoreEntity):
    _attr_name = "DoD solo simulazione"
    _attr_icon = "mdi:test-tube"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry) -> None:
        super().__init__(entry, "dod_simulazione")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        # al primo avvio parte in simulazione, per sicurezza
        self.dod.simulate = last.state == "on" if last else True

    @property
    def is_on(self) -> bool:
        return self.dod.simulate

    async def async_turn_on(self, **kwargs) -> None:
        self.dod.simulate = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self.dod.simulate = False
        self.async_write_ha_state()
