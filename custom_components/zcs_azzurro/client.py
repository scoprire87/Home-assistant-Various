"""Client asincrono Solarman V5 + Modbus RTU per inverter ZCS Azzurro ibridi.

Supporta:
  - FC 0x03 lettura holding register
  - FC 0x04 lettura input register
  - FC 0x13 scrittura multipla proprietaria ZCS ("CustomV2WriteMultipleRegisters",
    usata dall'app Azzurro Operators per i parametri batteria): slave, 0x13,
    indirizzo, quantita', dati, CRC -- senza byte count.
Nessuna dipendenza esterna.
"""
from __future__ import annotations

import asyncio
import logging
import random
import struct

_LOGGER = logging.getLogger(__name__)

FC_READ_HOLDING = 0x03
FC_READ_INPUT = 0x04
FC_ZCS_WRITE = 0x13

MODBUS_EXCEPTIONS = {
    1: "funzione non supportata",
    2: "indirizzo non valido",
    3: "valore non valido",
    4: "errore del dispositivo",
    5: "richiesta accettata, elaborazione in corso",
    6: "dispositivo occupato",
}


class ZcsError(Exception):
    """Errore di comunicazione con il datalogger/inverter."""


class ZcsModbusException(ZcsError):
    """L'inverter ha risposto con un'eccezione Modbus."""

    def __init__(self, code: int) -> None:
        super().__init__(f"eccezione Modbus {code}: {MODBUS_EXCEPTIONS.get(code, 'sconosciuta')}")
        self.code = code


def crc16_modbus(data: bytes) -> bytes:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


class ZcsClient:
    """Connessione persistente al datalogger, una richiesta alla volta."""

    def __init__(self, host: str, port: int, serial: int, slave: int = 1, timeout: float = 10) -> None:
        self.host = host
        self.port = int(port)
        self.serial = int(serial)
        self.slave = int(slave)
        self.timeout = timeout
        self._lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._seq = random.randint(1, 254)

    # ------------------------------------------------------------------ socket
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

    # ------------------------------------------------------------------ V5
    def _v5_frame(self, modbus: bytes) -> bytes:
        self._seq = (self._seq + 1) & 0xFF or 1
        payload = bytes([0x02]) + b"\x00\x00" + b"\x00" * 12 + modbus
        header = (
            bytes([0xA5])
            + struct.pack("<H", len(payload))
            + struct.pack("<H", 0x4510)
            + bytes([self._seq, 0x00])
            + struct.pack("<I", self.serial)
        )
        body = header + payload
        return body + bytes([sum(body[1:]) & 0xFF, 0x15])

    async def _read_v5_response(self) -> bytes:
        assert self._reader is not None
        while True:
            start = await self._reader.readexactly(1)
            if start != b"\xA5":
                continue
            header = await self._reader.readexactly(10)
            length = struct.unpack("<H", header[0:2])[0]
            control = struct.unpack("<H", header[2:4])[0]
            seq = header[4]
            rest = await self._reader.readexactly(length + 2)
            if control != 0x1510:
                continue  # heartbeat/altri frame del logger
            if seq != self._seq:
                _LOGGER.debug("Scartata risposta V5 con sequenza %s (attesa %s)", seq, self._seq)
                continue
            payload = rest[:length]
            if len(payload) < 14:
                raise ZcsError("risposta V5 troppo corta")
            modbus = payload[14:]
            if len(modbus) < 5:
                raise ZcsError("il datalogger non ha ricevuto risposta dall'inverter")
            if crc16_modbus(modbus[:-2]) != modbus[-2:]:
                raise ZcsError("CRC Modbus errato nella risposta")
            return modbus

    async def _request(self, pdu_without_crc: bytes) -> bytes:
        frame_mb = pdu_without_crc + crc16_modbus(pdu_without_crc)
        async with self._lock:
            last: Exception | None = None
            for attempt in range(3):
                try:
                    await self._connect()
                    assert self._writer is not None
                    self._writer.write(self._v5_frame(frame_mb))
                    await self._writer.drain()
                    resp = await asyncio.wait_for(self._read_v5_response(), self.timeout)
                    if resp[0] != self.slave or (resp[1] & 0x7F) != pdu_without_crc[1]:
                        raise ZcsError(f"risposta Modbus inattesa: {resp.hex(' ')}")
                    if resp[1] & 0x80:
                        raise ZcsModbusException(resp[2])
                    return resp
                except ZcsModbusException:
                    raise
                except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, ZcsError) as err:
                    last = err
                    _LOGGER.debug("Tentativo %s fallito: %s", attempt + 1, err)
                    await self.close()
                    await asyncio.sleep(1 + attempt * 2)
            raise ZcsError(f"comunicazione fallita: {last}") from last

    # ------------------------------------------------------------------ Modbus
    async def _read(self, fc: int, address: int, count: int) -> list[int]:
        resp = await self._request(struct.pack(">BBHH", self.slave, fc, address, count))
        byte_count = resp[2]
        if byte_count != 2 * count or len(resp) < 3 + byte_count + 2:
            raise ZcsError(f"lunghezza risposta errata ({byte_count} byte per {count} registri)")
        return list(struct.unpack(">" + "H" * count, resp[3 : 3 + byte_count]))

    async def read_holding(self, address: int, count: int) -> list[int]:
        return await self._read(FC_READ_HOLDING, address, count)

    async def read_input(self, address: int, count: int) -> list[int]:
        return await self._read(FC_READ_INPUT, address, count)

    async def write_zcs_block(self, address: int, values: list[int]) -> bytes:
        data = b"".join(struct.pack(">H", v & 0xFFFF) for v in values)
        return await self._request(
            struct.pack(">BBHH", self.slave, FC_ZCS_WRITE, address, len(values)) + data
        )
