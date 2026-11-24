"""Integrazione Immergas Modbus (Magis Combo V2, bus BMS) — sola lettura."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .client import ImmergasClient
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)
from .coordinator import ImmergasCoordinator

PLATFORMS = [Platform.SENSOR]


@dataclass
class ImmergasData:
    coordinator: ImmergasCoordinator
    device: DeviceInfo


type ImmergasConfigEntry = ConfigEntry[ImmergasData]


async def async_setup_entry(hass: HomeAssistant, entry: ImmergasConfigEntry) -> bool:
    client = ImmergasClient(
        entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data.get(CONF_SLAVE, DEFAULT_SLAVE)
    )
    coordinator = ImmergasCoordinator(
        hass, entry, client, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    await coordinator.async_config_entry_first_refresh()

    device = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=MANUFACTURER,
        model=MODEL,
        name="Immergas Magis Combo",
    )
    entry.runtime_data = ImmergasData(coordinator, device)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ImmergasConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.coordinator.client.close()
    return ok
