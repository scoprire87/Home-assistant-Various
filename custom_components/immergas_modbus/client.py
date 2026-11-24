"""Client Modbus TCP minimale per il convertitore Elfin EW11 (sola lettura).

Parla Modbus TCP standard (MBAP + PDU), senza dipendenze esterne. Pensato per un
gateway RS485->WiFi (EW11) configurato in modalita' "Modbus TCP <-> RTU". Legge solo
(FC 0x03 holding, FC 0x04 input): nessuna funzione di scrittura e' implementata di
proposito, l'integrazione e' in sola lettura.
"""
from __future__ import annotations

import asyncio
import logging
import struct

_LOGGER = logging.getLogger(__name__)

FC_READ_HOLDING = 0x03
FC_READ_INPUT = 0x04

MODBUS_EXCEPTIONS = {
    1: "funzione non supportata",
    2: "indirizzo non valido",
    3: "valore non valido",
    4: "errore del dispositivo",
    6: "dispositivo occupato",
}


class ImmergasError(Exception):
    """Errore di comunicazione con il gateway/caldaia."""


class ImmergasModbusException(ImmergasError):
    """La caldaia ha risposto con un'eccezione Modbus."""

    def __init__(self, code: int) -> None:
        super().__init__(f"eccezione Modbus {code}: {MODBUS_EXCEPTIONS.get(code, 'sconosciuta')}")
        self.code = code


def build_request(tid: int, unit: int, pdu: bytes) -> bytes:
    """Incapsula una PDU Modbus in un frame TCP (MBAP header)."""
    # transaction id, protocol id (0), length (unit + pdu), unit id
    return struct.pack(">HHHB", tid & 0xFFFF, 0, len(pdu) + 1, unit & 0xFF) + pdu


def parse_read_response(data: bytes, tid: int, unit: int, fc: int, count: int) -> list[int]:
    """Decodifica un frame di risposta a una lettura registri. Alza ImmergasError/ModbusException."""
    if len(data) < 8:
        raise ImmergasError("risposta troppo corta")
    r_tid, proto, length, r_unit = struct.unpack(">HHHB", data[:7])
    if proto != 0:
        raise ImmergasError(f"protocollo MBAP inatteso ({proto})")
    if r_tid != (tid & 0xFFFF):
        raise ImmergasError(f"transaction id inatteso ({r_tid} invece di {tid})")
    if r_unit != (unit & 0xFF):
        raise ImmergasError(f"unit id inatteso ({r_unit} invece di {unit})")
    pdu = data[7 : 7 + max(length - 1, 0)]
    if len(pdu) < 2:
        raise ImmergasError("PDU di risposta incompleta")
    r_fc = pdu[0]
    if r_fc & 0x80:
        raise ImmergasModbusException(pdu[1])
    if r_fc != fc:
        raise ImmergasError(f"function code inatteso ({r_fc} invece di {fc})")
    byte_count = pdu[1]
    if byte_count != 2 * count or len(pdu) < 2 + byte_count:
        raise ImmergasError(f"lunghezza dati errata ({byte_count} byte per {count} registri)")
    return list(struct.unpack(">" + "H" * count, pdu[2 : 2 + byte_count]))


class ImmergasClient:
    """Connessione TCP persistente al gateway, una richiesta alla volta."""

    def __init__(self, host: str, port: int, slave: int, timeout: float = 10) -> None:
        self.host = host
        self.port = int(port)
        self.slave = int(slave)
        self.timeout = timeout
        self._lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._tid = 0

    async def _connect(self) -> None:
        if self._writer is not None and not self._writer.is_closing():
            return
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), self.timeout
        )

    async def close(self) -> None:
        writer, self._reader, self._writer = self._writer, None, None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    async def _read_frame(self) -> bytes:
        assert self._reader is not None
        header = await self._reader.readexactly(6)
        length = struct.unpack(">HHH", header)[2]
        rest = await self._reader.readexactly(length)
        return header + rest

    async def _read(self, fc: int, address: int, count: int) -> list[int]:
        pdu = struct.pack(">BHH", fc, address, count)
        async with self._lock:
            last: Exception | None = None
            for attempt in range(3):
                self._tid = (self._tid + 1) & 0xFFFF
                try:
                    await self._connect()
                    assert self._writer is not None
                    self._writer.write(build_request(self._tid, self.slave, pdu))
                    await self._writer.drain()
                    data = await asyncio.wait_for(self._read_frame(), self.timeout)
                    return parse_read_response(data, self._tid, self.slave, fc, count)
                except ImmergasModbusException:
                    raise
                except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, ImmergasError) as err:
                    last = err
                    _LOGGER.debug("Tentativo %s fallito: %s", attempt + 1, err)
                    await self.close()
                    await asyncio.sleep(1 + attempt)
            raise ImmergasError(f"comunicazione fallita: {last!r}") from last

    async def read_holding(self, address: int, count: int) -> list[int]:
        return await self._read(FC_READ_HOLDING, address, count)

    async def read_input(self, address: int, count: int) -> list[int]:
        return await self._read(FC_READ_INPUT, address, count)
