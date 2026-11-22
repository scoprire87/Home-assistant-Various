"""Integrazione ZCS Azzurro (inverter ibridi HYD-ES) con DoD automatico."""
from __future__ import annotations

from dataclasses import dataclass

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo

from .client import ZcsClient
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    CONF_SLAVE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DOMAIN,
    MANUFACTURER,
)
from .coordinator import ZcsCoordinator
from .dod import DodManager

PLATFORMS = [Platform.BUTTON, Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH]


@dataclass
class ZcsData:
    coordinator: ZcsCoordinator
    dod: DodManager
    device: DeviceInfo


type ZcsConfigEntry = ConfigEntry[ZcsData]


async def async_setup_entry(hass: HomeAssistant, entry: ZcsConfigEntry) -> bool:
    client = ZcsClient(
        entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data[CONF_SERIAL],
        entry.data.get(CONF_SLAVE, DEFAULT_SLAVE),
    )
    coordinator = ZcsCoordinator(
        hass, entry, client, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    await coordinator.async_config_entry_first_refresh()

    device = DeviceInfo(
        identifiers={(DOMAIN, str(entry.data[CONF_SERIAL]))},
        manufacturer=MANUFACTURER,
        model="Azzurro ibrido HYD-ES",
        name="ZCS Azzurro",
        configuration_url="https://www.zcsazzurro.com",
    )
    dod = DodManager(hass, entry, coordinator)
    entry.runtime_data = ZcsData(coordinator, dod, device)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    dod.async_start()
    entry.async_on_unload(dod.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    _async_register_services(hass)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ZcsConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ZcsConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.coordinator.client.close()
    return ok


def _get_entry(hass: HomeAssistant, call: ServiceCall) -> ZcsConfigEntry:
    entries = [e for e in hass.config_entries.async_loaded_entries(DOMAIN)]
    entry_id = call.data.get("config_entry_id")
    if entry_id:
        entries = [e for e in entries if e.entry_id == entry_id]
    if not entries:
        raise ServiceValidationError("Nessun inverter ZCS Azzurro configurato")
    return entries[0]


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, "valuta_dod"):
        return

    async def valuta_dod(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call)
        return await entry.runtime_data.dod.async_evaluate(
            apply=call.data["applica"], notify=call.data["notifica"]
        )

    hass.services.async_register(
        DOMAIN, "valuta_dod", valuta_dod,
        schema=vol.Schema({
            vol.Optional("config_entry_id"): cv.string,
            vol.Optional("applica", default=False): cv.boolean,
            vol.Optional("notifica", default=False): cv.boolean,
        }),
        supports_response=SupportsResponse.OPTIONAL,
    )
