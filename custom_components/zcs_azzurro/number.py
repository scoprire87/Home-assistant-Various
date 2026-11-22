"""Entita' number: parametri batteria scrivibili + soglie del DoD automatico."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DEFAULT_T_HIGH,
    DEFAULT_T_LOW,
    DEFAULT_T_MID,
    DOD_MAX,
    DOD_MIN,
    REG_DOD,
    REG_DOD_EPS,
    REG_SAFETY_BUFFER,
)
from .entity import ZcsDodEntity, ZcsEntity

INVERTER_NUMBERS = [
    # key, nome, registro, min, max, icona
    ("dod_rete", "Profondità di scarica in rete", REG_DOD, DOD_MIN, DOD_MAX, "mdi:battery-arrow-down"),
    ("dod_eps", "Profondità di scarica in EPS", REG_DOD_EPS, DOD_MIN, DOD_MAX, "mdi:battery-alert"),
    ("buffer_sicurezza", "Buffer di scarica di sicurezza", REG_SAFETY_BUFFER, 0, 100, "mdi:shield-half-full"),
]

THRESHOLDS = [
    # key, nome, attributo manager, default
    ("soglia_bassa", "DoD soglia pioggia inverno", "t_low", DEFAULT_T_LOW),
    ("soglia_media", "DoD soglia sole inverno / pioggia estate", "t_mid", DEFAULT_T_MID),
    ("soglia_alta", "DoD soglia sole estate", "t_high", DEFAULT_T_HIGH),
]


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    entities: list[NumberEntity] = [ZcsBatteryNumber(entry, *n) for n in INVERTER_NUMBERS]
    entities += [ZcsThresholdNumber(entry, *t) for t in THRESHOLDS]
    async_add_entities(entities)


class ZcsBatteryNumber(ZcsEntity, NumberEntity):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, entry, key, name, register, vmin, vmax, icon) -> None:
        super().__init__(entry, key)
        self._register = register
        self._attr_name = name
        self._attr_native_min_value = vmin
        self._attr_native_max_value = vmax
        self._attr_icon = icon

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._register)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write_battery_param(self._register, int(value))


class ZcsThresholdNumber(ZcsDodEntity, RestoreNumber):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = DOD_MIN
    _attr_native_max_value = DOD_MAX
    _attr_native_step = 5
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:tune-variant"

    def __init__(self, entry, key, name, attr, default) -> None:
        super().__init__(entry, key)
        self._attr_name = name
        self._attr_key = attr
        self._default = default

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        value = last.native_value if last and last.native_value is not None else self._default
        setattr(self.dod, self._attr_key, int(value))

    @property
    def native_value(self):
        return getattr(self.dod, self._attr_key)

    async def async_set_native_value(self, value: float) -> None:
        setattr(self.dod, self._attr_key, int(value))
        self.async_write_ha_state()
