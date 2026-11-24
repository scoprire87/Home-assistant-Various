"""Mappa registri Immergas Magis Combo V2 — bus BMS (morsetti T-/T+).

⚠ Fonte: progetti della comunità (reverse engineering), NON documentazione ufficiale
Immergas. Indirizzi, scale e significati vanno verificati sul proprio esemplare prima di
farci affidamento. Tutti i registri qui sono letti come holding (FC 0x03) e sono di sola
lettura. Riferimenti:
  - https://github.com/jotuera/immergas-magis-pro-combo-tt-bms  (bus T-/T+ BMS)
  - https://community.home-assistant.io/t/how-to-connect-to-immergas-magis-combo-v2-magis-pro-v2-heat-pump-via-modbus-into-ha/926577
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory


def u16(regs: dict[int, int], a: int) -> int | None:
    return regs.get(a)


def i16(regs: dict[int, int], a: int) -> int | None:
    v = regs.get(a)
    if v is None:
        return None
    return v - 0x10000 if v & 0x8000 else v


@dataclass(frozen=True, kw_only=True)
class ImmergasSensor:
    key: str
    name: str
    value: Callable[[dict[int, int]], float | int | str | None]
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    precision: int | None = None
    icon: str | None = None
    category: EntityCategory | None = None
    enabled: bool = True


def _temp(addr: int):
    """Temperatura: int16 con segno, scala ×0.1 °C."""
    def get(regs):
        v = i16(regs, addr)
        return None if v is None else round(v * 0.1, 1)
    return get


TEMP = SensorDeviceClass.TEMPERATURE
M = SensorStateClass.MEASUREMENT
C = UnitOfTemperature.CELSIUS
DIAG = EntityCategory.DIAGNOSTIC

SENSORS: list[ImmergasSensor] = [
    # --- temperature (×0.1 °C) ---
    ImmergasSensor(key="mandata_impianto", name="Mandata impianto", value=_temp(3000),
                   unit=C, device_class=TEMP, state_class=M, icon="mdi:thermometer"),
    ImmergasSensor(key="ritorno_pdc", name="Ritorno pompa di calore", value=_temp(3001),
                   unit=C, device_class=TEMP, state_class=M, icon="mdi:thermometer"),
    ImmergasSensor(key="temperatura_esterna", name="Temperatura esterna", value=_temp(3002),
                   unit=C, device_class=TEMP, state_class=M, icon="mdi:sun-thermometer"),
    ImmergasSensor(key="accumulo_sanitario", name="Accumulo sanitario", value=_temp(3016),
                   unit=C, device_class=TEMP, state_class=M, icon="mdi:water-thermometer"),
    ImmergasSensor(key="ritorno_unita_interna", name="Ritorno unità interna", value=_temp(3029),
                   unit=C, device_class=TEMP, state_class=M, icon="mdi:thermometer", enabled=False),
    ImmergasSensor(key="liquido_chiller", name="Liquido circuito chiller", value=_temp(3056),
                   unit=C, device_class=TEMP, state_class=M, category=DIAG, enabled=False),
    # --- setpoint sanitario (×0.1 °C), letto come sensore: nessuna scrittura ---
    ImmergasSensor(key="setpoint_sanitario", name="Setpoint sanitario", value=_temp(2095),
                   unit=C, device_class=TEMP, icon="mdi:water-boiler"),
    # --- stato / diagnostica (valori grezzi: significati da confermare) ---
    ImmergasSensor(key="modo_operativo", name="Modo operativo (grezzo)", value=lambda r: u16(r, 2000),
                   icon="mdi:state-machine", category=DIAG),
    ImmergasSensor(key="codice_guasto", name="Codice guasto", value=lambda r: u16(r, 2100),
                   icon="mdi:alert", category=DIAG),
]
