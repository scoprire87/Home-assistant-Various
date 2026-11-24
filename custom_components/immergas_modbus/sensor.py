"""Sensori (sola lettura)."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import ImmergasEntity
from .registers import SENSORS, ImmergasSensor


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(ImmergasRegisterSensor(entry, d) for d in SENSORS)


class ImmergasRegisterSensor(ImmergasEntity, SensorEntity):
    def __init__(self, entry, desc: ImmergasSensor) -> None:
        super().__init__(entry, desc.key)
        self.desc = desc
        self._attr_name = desc.name
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_device_class = desc.device_class
        self._attr_state_class = desc.state_class
        self._attr_suggested_display_precision = desc.precision
        self._attr_icon = desc.icon
        self._attr_entity_category = desc.category
        self._attr_entity_registry_enabled_default = desc.enabled

    @property
    def native_value(self):
        return self.desc.value(self.coordinator.data or {})
