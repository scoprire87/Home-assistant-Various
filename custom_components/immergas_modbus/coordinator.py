"""Coordinator: lettura periodica dei registri (sola lettura)."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ImmergasClient, ImmergasError
from .const import DOMAIN, REG_BLOCKS

_LOGGER = logging.getLogger(__name__)

MAX_TOLERATED_FAILURES = 4  # cicli interamente falliti prima di segnare 'non disponibile'


class ImmergasCoordinator(DataUpdateCoordinator[dict[int, int]]):
    """Mantiene un dizionario indirizzo -> valore grezzo (u16)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ImmergasClient, interval: int) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, config_entry=entry, update_interval=timedelta(seconds=interval)
        )
        self.client = client
        self._regs: dict[int, int] = {}
        self._failures = 0

    async def _async_update_data(self) -> dict[int, int]:
        got_any = False
        last: Exception | None = None
        for start, qty in REG_BLOCKS:
            try:
                values = await self.client.read_holding(start, qty)
            except ImmergasError as err:
                # Un blocco puo' contenere un registro inesistente su questo esemplare:
                # si salta quel blocco senza perdere gli altri.
                last = err
                _LOGGER.debug("Blocco %s+%s non letto: %s", start, qty, err)
                continue
            self._regs.update({start + i: v for i, v in enumerate(values)})
            got_any = True

        if not got_any:
            self._failures += 1
            if self._regs and self._failures <= MAX_TOLERATED_FAILURES:
                _LOGGER.debug("Nessun blocco letto (%s/%s), uso gli ultimi valori",
                              self._failures, MAX_TOLERATED_FAILURES)
                return dict(self._regs)
            raise UpdateFailed(str(last) if last else "nessun registro leggibile")

        self._failures = 0
        return dict(self._regs)
