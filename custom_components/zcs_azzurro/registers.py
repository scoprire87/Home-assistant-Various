"""Mappa registri ZCS Azzurro HYD-ES (dall'app ufficiale Azzurro Operators 1.0.506)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import EntityCategory

INVERTER_STATES = {
    0: "Attesa",
    1: "Verifica rete",
    2: "Normale",
    3: "EPS (backup)",
    4: "Guasto",
    5: "Guasto permanente",
}
WORK_MODES = {
    0: "Autoconsumo",
    1: "Tariffa a fasce orarie",
    2: "Carica/scarica programmata",
    3: "Passiva",
}
BATTERY_TYPES = {0: "Azzurro ZSX", 1: "Pylon", 2: "Soltaro", 3: "AlphaESS", 4: "Weco", 256: "Predefinita"}


def u16(regs: dict[int, int], a: int) -> int | None:
    return regs.get(a)


def i16(regs: dict[int, int], a: int) -> int | None:
    v = regs.get(a)
    if v is None:
        return None
    return v - 0x10000 if v & 0x8000 else v


def u32(regs: dict[int, int], a: int) -> int | None:
    hi, lo = regs.get(a), regs.get(a + 1)
    if hi is None or lo is None:
        return None
    return (hi << 16) | lo


@dataclass(frozen=True, kw_only=True)
class ZcsSensor:
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
    options: list[str] | None = None


def _scaled(fn, addr, scale):
    def get(regs):
        v = fn(regs, addr)
        return None if v is None else round(v * scale, 3)
    return get


def _power_split(addr: int, positive: bool):
    """Divide una potenza con segno in due sensori >= 0 (utile per la dashboard Energia)."""
    def get(regs):
        v = i16(regs, addr)
        if v is None:
            return None
        w = v * 10
        return max(w, 0) if positive else max(-w, 0)
    return get


def _enum(addr, table):
    def get(regs):
        v = regs.get(addr)
        return None if v is None else table.get(v, f"Sconosciuto ({v})")
    return get


def _alarm_bits(regs):
    v = regs.get(555)
    if v is None:
        return None
    return "Nessuno" if v == 0 else ", ".join(f"bit {b}" for b in range(16) if v >> b & 1)


P = SensorDeviceClass.POWER
E = SensorDeviceClass.ENERGY
V = SensorDeviceClass.VOLTAGE
A = SensorDeviceClass.CURRENT
M = SensorStateClass.MEASUREMENT
TI = SensorStateClass.TOTAL_INCREASING
W = UnitOfPower.WATT
KWH = UnitOfEnergy.KILO_WATT_HOUR
VOLT = UnitOfElectricPotential.VOLT
AMP = UnitOfElectricCurrent.AMPERE
DIAG = EntityCategory.DIAGNOSTIC

SENSORS: list[ZcsSensor] = [
    # --- stato ---
    ZcsSensor(key="stato", name="Stato inverter", value=_enum(512, INVERTER_STATES),
              device_class=SensorDeviceClass.ENUM, options=list(INVERTER_STATES.values()), icon="mdi:solar-power"),
    ZcsSensor(key="allarme", name="Allarme inverter", value=_alarm_bits, icon="mdi:alert", category=DIAG),
    ZcsSensor(key="allarme_codice", name="Codice allarme", value=lambda r: r.get(555), category=DIAG, enabled=False),
    # --- potenze ---
    ZcsSensor(key="potenza_fv", name="Potenza FV", value=_scaled(u16, 533, 10), unit=W, device_class=P, state_class=M),
    ZcsSensor(key="potenza_fv1", name="Potenza FV stringa 1", value=_scaled(u16, 594, 10), unit=W, device_class=P, state_class=M),
    ZcsSensor(key="potenza_fv2", name="Potenza FV stringa 2", value=_scaled(u16, 597, 10), unit=W, device_class=P, state_class=M),
    ZcsSensor(key="potenza_carico", name="Potenza consumo casa", value=_scaled(u16, 531, 10), unit=W, device_class=P, state_class=M),
    ZcsSensor(key="potenza_rete", name="Potenza rete", value=_scaled(i16, 530, 10), unit=W, device_class=P, state_class=M,
              icon="mdi:transmission-tower"),
    ZcsSensor(key="potenza_prelievo", name="Potenza prelevata dalla rete", value=_power_split(530, False), unit=W, device_class=P,
              state_class=M, icon="mdi:transmission-tower-import"),
    ZcsSensor(key="potenza_immissione", name="Potenza immessa in rete", value=_power_split(530, True), unit=W, device_class=P,
              state_class=M, icon="mdi:transmission-tower-export"),
    ZcsSensor(key="potenza_batteria", name="Potenza batteria", value=_scaled(i16, 525, 10), unit=W, device_class=P, state_class=M,
              icon="mdi:battery-charging"),
    ZcsSensor(key="potenza_carica", name="Potenza carica batteria", value=_power_split(525, True), unit=W, device_class=P,
              state_class=M, icon="mdi:battery-arrow-up"),
    ZcsSensor(key="potenza_scarica", name="Potenza scarica batteria", value=_power_split(525, False), unit=W, device_class=P,
              state_class=M, icon="mdi:battery-arrow-down"),
    ZcsSensor(key="potenza_eps", name="Potenza EPS", value=_scaled(u16, 535, 10), unit=W, device_class=P, state_class=M, enabled=False),
    # --- batteria ---
    ZcsSensor(key="soc", name="Batteria SoC", value=lambda r: r.get(528), unit=PERCENTAGE, device_class=SensorDeviceClass.BATTERY,
              state_class=M),
    ZcsSensor(key="soh", name="Batteria stato di salute", value=lambda r: r.get(567), unit=PERCENTAGE, state_class=M,
              icon="mdi:battery-heart-variant"),
    ZcsSensor(key="tensione_batteria", name="Batteria tensione", value=_scaled(u16, 526, 0.1), unit=VOLT, device_class=V, state_class=M),
    ZcsSensor(key="corrente_batteria", name="Batteria corrente", value=_scaled(i16, 527, 0.01), unit=AMP, device_class=A, state_class=M),
    ZcsSensor(key="temperatura_batteria", name="Batteria temperatura", value=lambda r: i16(r, 529),
              unit=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE, state_class=M),
    ZcsSensor(key="cicli_batteria", name="Batteria cicli", value=lambda r: r.get(556), state_class=TI, icon="mdi:battery-sync"),
    # --- rete / inverter ---
    ZcsSensor(key="tensione_rete", name="Rete tensione", value=_scaled(u16, 518, 0.1), unit=VOLT, device_class=V, state_class=M),
    ZcsSensor(key="corrente_rete", name="Rete corrente", value=_scaled(u16, 519, 0.01), unit=AMP, device_class=A, state_class=M),
    ZcsSensor(key="frequenza_rete", name="Rete frequenza", value=_scaled(u16, 524, 0.01), unit=UnitOfFrequency.HERTZ,
              device_class=SensorDeviceClass.FREQUENCY, state_class=M),
    ZcsSensor(key="tensione_eps", name="EPS tensione", value=_scaled(u16, 534, 0.1), unit=VOLT, device_class=V, state_class=M, enabled=False),
    ZcsSensor(key="temperatura_inverter", name="Inverter temperatura", value=lambda r: i16(r, 568), unit=UnitOfTemperature.CELSIUS,
              device_class=SensorDeviceClass.TEMPERATURE, state_class=M, category=DIAG),
    ZcsSensor(key="temperatura_dc", name="Inverter temperatura DC", value=lambda r: i16(r, 569), unit=UnitOfTemperature.CELSIUS,
              device_class=SensorDeviceClass.TEMPERATURE, state_class=M, category=DIAG),
    ZcsSensor(key="tensione_bus", name="Tensione bus", value=_scaled(u16, 557, 0.1), unit=VOLT, device_class=V, state_class=M,
              category=DIAG, enabled=False),
    # --- stringhe FV ---
    ZcsSensor(key="tensione_fv1", name="FV stringa 1 tensione", value=_scaled(u16, 592, 0.1), unit=VOLT, device_class=V, state_class=M),
    ZcsSensor(key="corrente_fv1", name="FV stringa 1 corrente", value=_scaled(u16, 593, 0.01), unit=AMP, device_class=A, state_class=M),
    ZcsSensor(key="tensione_fv2", name="FV stringa 2 tensione", value=_scaled(u16, 595, 0.1), unit=VOLT, device_class=V, state_class=M),
    ZcsSensor(key="corrente_fv2", name="FV stringa 2 corrente", value=_scaled(u16, 596, 0.01), unit=AMP, device_class=A, state_class=M),
    ZcsSensor(key="isolamento_fv1", name="Isolamento FV1+ verso terra", value=lambda r: r.get(582), unit="kΩ", category=DIAG, enabled=False),
    ZcsSensor(key="isolamento_fv2", name="Isolamento FV2+ verso terra", value=lambda r: r.get(583), unit="kΩ", category=DIAG, enabled=False),
    ZcsSensor(key="isolamento_fv_neg", name="Isolamento FV- verso terra", value=lambda r: r.get(584), unit="kΩ", category=DIAG, enabled=False),
    # --- energia giornaliera (risoluzione 0,01 kWh: consigliata per la dashboard Energia) ---
    ZcsSensor(key="fv_oggi", name="Produzione FV oggi", value=_scaled(u16, 536, 0.01), unit=KWH, device_class=E, state_class=TI, precision=2),
    ZcsSensor(key="immessa_oggi", name="Energia immessa oggi", value=_scaled(u16, 537, 0.01), unit=KWH, device_class=E, state_class=TI, precision=2),
    ZcsSensor(key="prelevata_oggi", name="Energia prelevata oggi", value=_scaled(u16, 538, 0.01), unit=KWH, device_class=E, state_class=TI, precision=2),
    ZcsSensor(key="consumo_oggi", name="Consumo casa oggi", value=_scaled(u16, 539, 0.01), unit=KWH, device_class=E, state_class=TI, precision=2),
    ZcsSensor(key="carica_oggi", name="Batteria energia caricata oggi", value=_scaled(u16, 548, 0.01), unit=KWH, device_class=E,
              state_class=TI, precision=2),
    ZcsSensor(key="scarica_oggi", name="Batteria energia scaricata oggi", value=_scaled(u16, 549, 0.01), unit=KWH, device_class=E,
              state_class=TI, precision=2),
    # --- energia totale (risoluzione 1 kWh) ---
    ZcsSensor(key="fv_totale", name="Produzione FV totale", value=lambda r: u32(r, 540), unit=KWH, device_class=E, state_class=TI),
    ZcsSensor(key="immessa_totale", name="Energia immessa totale", value=lambda r: u32(r, 542), unit=KWH, device_class=E, state_class=TI),
    ZcsSensor(key="prelevata_totale", name="Energia prelevata totale", value=lambda r: u32(r, 544), unit=KWH, device_class=E, state_class=TI),
    ZcsSensor(key="consumo_totale", name="Consumo casa totale", value=lambda r: u32(r, 546), unit=KWH, device_class=E, state_class=TI),
    ZcsSensor(key="carica_totale", name="Batteria energia caricata totale", value=lambda r: u32(r, 550), unit=KWH, device_class=E,
              state_class=TI),
    ZcsSensor(key="scarica_totale", name="Batteria energia scaricata totale", value=lambda r: u32(r, 552), unit=KWH, device_class=E,
              state_class=TI),
    # --- parametri batteria (blocco 0x10B0, sola lettura qui; DoD e buffer sono entita' number) ---
    ZcsSensor(key="tipo_batteria", name="Batteria tipo", value=_enum(4272, BATTERY_TYPES), category=DIAG),
    ZcsSensor(key="capacita_batteria", name="Batteria capacità", value=lambda r: r.get(4273), unit="Ah", category=DIAG),
    ZcsSensor(key="tensione_max_carica", name="Batteria tensione max carica", value=_scaled(u16, 4275, 0.1), unit=VOLT,
              device_class=V, category=DIAG),
    ZcsSensor(key="corrente_max_carica", name="Batteria corrente max carica", value=_scaled(u16, 4276, 0.01), unit=AMP,
              device_class=A, category=DIAG),
    ZcsSensor(key="tensione_min_scarica", name="Batteria tensione min scarica", value=_scaled(u16, 4278, 0.1), unit=VOLT,
              device_class=V, category=DIAG),
    ZcsSensor(key="corrente_max_scarica", name="Batteria corrente max scarica", value=_scaled(u16, 4279, 0.01), unit=AMP,
              device_class=A, category=DIAG),
    ZcsSensor(key="modalita_lavoro", name="Modalità di lavoro", value=_enum(4608, WORK_MODES), device_class=SensorDeviceClass.ENUM,
              options=list(WORK_MODES.values()), category=DIAG),
]
