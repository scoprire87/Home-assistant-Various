"""Test del client Modbus TCP Immergas (senza Home Assistant).

Carica solo client.py per file, così non importa il pacchetto (che dipende da HA).
"""
from __future__ import annotations

import asyncio
import importlib.util
import struct
from pathlib import Path

import pytest

CLIENT_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "immergas_modbus" / "client.py"
spec = importlib.util.spec_from_file_location("immergas_client", CLIENT_PATH)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


def _make_response(tid: int, unit: int, fc: int, values: list[int]) -> bytes:
    data = b"".join(struct.pack(">H", v) for v in values)
    pdu = bytes([fc, len(data)]) + data
    return struct.pack(">HHHB", tid, 0, len(pdu) + 1, unit) + pdu


def test_build_request():
    req = client.build_request(7, 11, struct.pack(">BHH", 3, 3000, 2))
    tid, proto, length, unit = struct.unpack(">HHHB", req[:7])
    assert (tid, proto, length, unit) == (7, 0, 6, 11)
    assert req[7:] == struct.pack(">BHH", 3, 3000, 2)


def test_parse_ok():
    frame = _make_response(5, 11, 0x03, [0x00FA, 0xFFEC])  # 250, -20 (×0.1 = 25.0, -2.0)
    vals = client.parse_read_response(frame, 5, 11, 0x03, 2)
    assert vals == [0x00FA, 0xFFEC]
    # decodifica con segno come fa registers.i16
    def i16(v):
        return v - 0x10000 if v & 0x8000 else v
    assert round(i16(vals[0]) * 0.1, 1) == 25.0
    assert round(i16(vals[1]) * 0.1, 1) == -2.0


def test_parse_modbus_exception():
    pdu = bytes([0x83, 0x02])  # FC|0x80, codice 2 = indirizzo non valido
    frame = struct.pack(">HHHB", 9, 0, len(pdu) + 1, 11) + pdu
    with pytest.raises(client.ImmergasModbusException) as exc:
        client.parse_read_response(frame, 9, 11, 0x03, 1)
    assert exc.value.code == 2


def test_parse_wrong_tid():
    frame = _make_response(1, 11, 0x03, [0])
    with pytest.raises(client.ImmergasError):
        client.parse_read_response(frame, 2, 11, 0x03, 1)


def test_parse_wrong_bytecount():
    frame = _make_response(3, 11, 0x03, [1])  # 1 registro
    with pytest.raises(client.ImmergasError):
        client.parse_read_response(frame, 3, 11, 0x03, 2)  # ne attendevo 2


def test_client_reads_from_fake_server():
    """Avvia un finto gateway TCP che risponde a una lettura e verifica il client."""
    async def run():
        received: list[bytes] = []

        async def handle(reader, writer):
            header = await reader.readexactly(6)
            length = struct.unpack(">HHH", header)[2]
            rest = await reader.readexactly(length)
            received.append(header + rest)
            tid = struct.unpack(">H", header[:2])[0]
            unit = rest[0]
            writer.write(_make_response(tid, unit, 0x03, [0x00FA, 0x00C8, 0xFFEC]))
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            c = client.ImmergasClient("127.0.0.1", port, 11, timeout=5)
            try:
                vals = await c.read_holding(3000, 3)
            finally:
                await c.close()
        assert vals == [0x00FA, 0x00C8, 0xFFEC]
        # il frame inviato chiedeva holding 3000 x3 allo slave 11
        sent = received[0]
        assert sent[6] == 11
        assert sent[7:] == struct.pack(">BHH", 3, 3000, 3)

    asyncio.run(run())
