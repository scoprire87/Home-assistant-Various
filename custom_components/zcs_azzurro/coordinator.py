"""Coordinator: lettura periodica dei registri e scrittura dei parametri batteria."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ZcsClient, ZcsError
from .const import (
    BAT_QTY,
    BAT_START,
    DOD_MAX,
    DOD_MIN,
    DOMAIN,
    REG_DOD,
    REG_WORK_MODE,
    RT_BLOCKS,
    SLOW_REFRESH_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class ZcsCoordinator(DataUpdateCoordinator[dict[int, int]]):
    """Mantiene un dizionario indirizzo -> valore grezzo (u16)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ZcsClient, interval: int) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, config_entry=entry, update_interval=timedelta(seconds=interval)
        )
        self.client = client
        self._regs: dict[int, int] = {}
        self._slow_at = 0.0

    async def _async_update_data(self) -> dict[int, int]:
        try:
            for start, qty in RT_BLOCKS:
                values = await self.client.read_holding(start, qty)
                self._regs.update({start + i: v for i, v in enumerate(values)})
            if time.monotonic() - self._slow_at > SLOW_REFRESH_SECONDS:
                await self._refresh_slow()
        except ZcsError as err:
            raise UpdateFailed(str(err)) from err
        return dict(self._regs)

    async def _refresh_slow(self) -> None:
        values = await self.client.read_input(BAT_START, BAT_QTY)
        self._regs.update({BAT_START + i: v for i, v in enumerate(values)})
        try:
            self._regs[REG_WORK_MODE] = (await self.client.read_holding(REG_WORK_MODE, 1))[0]
        except ZcsError as err:
            _LOGGER.debug("Modalità di lavoro non leggibile: %s", err)
        self._slow_at = time.monotonic()

    async def async_write_battery_param(self, address: int, value: int) -> dict:
        """Scrive un parametro del blocco batteria come l'app Azzurro Operators.

        Rilegge il blocco 4272-4287, cambia solo `address`, riscrive tutto con FC 0x13,
        rilegge e verifica. Ritorna un dizionario con l'esito.
        """
        if not BAT_START <= address < BAT_START + BAT_QTY:
            raise HomeAssistantError(f"registro {address} fuori dal blocco batteria")
        try:
            before = await self.client.read_input(BAT_START, BAT_QTY)
            regs = {BAT_START + i: v for i, v in enumerate(before)}
            # controlli di plausibilita' prima di riscrivere tutto il blocco
            if not (DOD_MIN <= regs[REG_DOD] <= DOD_MAX) or regs[4273] == 0 or regs[4275] == 0:
                raise HomeAssistantError(f"valori batteria letti non plausibili {before}: scrittura annullata")
            if regs[address] == value:
                return {"ok": True, "scritto": False, "valore": value, "blocco": before}
            new_block = list(before)
            new_block[address - BAT_START] = int(value)
            await self.client.write_zcs_block(BAT_START, new_block)
            after = await self.client.read_input(BAT_START, BAT_QTY)
        except ZcsError as err:
            raise HomeAssistantError(f"scrittura non riuscita: {err}") from err

        self._regs.update({BAT_START + i: v for i, v in enumerate(after)})
        self.async_set_updated_data(dict(self._regs))
        others = [BAT_START + i for i, (a, b) in enumerate(zip(new_block, after)) if a != b and BAT_START + i != address]
        ok = after[address - BAT_START] == value and not others
        result = {"ok": ok, "scritto": True, "valore": after[address - BAT_START], "altri_cambiati": others,
                  "blocco_prima": before, "blocco_dopo": after}
        if not ok:
            raise HomeAssistantError(f"verifica scrittura fallita: {result}")
        return result
