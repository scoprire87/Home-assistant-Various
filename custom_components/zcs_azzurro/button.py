"""Pulsanti per lanciare subito la decisione del DoD."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import ZcsDodEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([
        ZcsDodButton(entry, "dod_valuta", "DoD calcola (senza applicare)", "mdi:calculator", apply=False),
        ZcsDodButton(entry, "dod_applica", "DoD calcola e applica ora", "mdi:battery-sync", apply=True),
    ])


class ZcsDodButton(ZcsDodEntity, ButtonEntity):
    def __init__(self, entry, key, name, icon, apply: bool) -> None:
        super().__init__(entry, key)
        self._attr_name = name
        self._attr_icon = icon
        self._apply = apply

    async def async_press(self) -> None:
        await self.dod.async_evaluate(apply=self._apply and not self.dod.simulate, notify=True)
