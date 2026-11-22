"""Sensori."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import ZcsDodEntity, ZcsEntity
from .registers import SENSORS, ZcsSensor


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    entities: list[SensorEntity] = [ZcsRegisterSensor(entry, d) for d in SENSORS]
    entities.append(ZcsDodDecisionSensor(entry))
    async_add_entities(entities)


class ZcsRegisterSensor(ZcsEntity, SensorEntity):
    def __init__(self, entry, desc: ZcsSensor) -> None:
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
        self._attr_options = desc.options

    @property
    def native_value(self):
        return self.desc.value(self.coordinator.data or {})


class ZcsDodDecisionSensor(ZcsDodEntity, SensorEntity):
    _attr_name = "DoD ultima decisione"
    _attr_icon = "mdi:robot"
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, entry) -> None:
        super().__init__(entry, "dod_decisione")

    @property
    def native_value(self):
        return self.dod.last["dod"] if self.dod.last else None

    @property
    def extra_state_attributes(self):
        r = self.dod.last
        if not r:
            return None
        return {
            "fonte": r.get("fonte"),
            "motivazione": r.get("motivazione"),
            "scrittura": r.get("scrittura"),
            "ora": r.get("ora"),
            "modalita": r.get("modalita"),
            "dod_precedente": r.get("dod_attuale"),
            "dod_soglie": r.get("dod_soglie"),
            "indice_stagione": r.get("indice_stagione"),
            "indice_meteo": r.get("indice_meteo"),
            "ia": r.get("ia"),
            "errore_ia": r.get("errore_ia"),
            "meteo": r.get("meteo"),
        }
