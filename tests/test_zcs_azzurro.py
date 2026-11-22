"""Test integrazione zcs_azzurro con un datalogger Solarman V5 simulato."""
from __future__ import annotations

import asyncio
import struct
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zcs_azzurro.client import crc16_modbus
from custom_components.zcs_azzurro.const import DOMAIN
from custom_components.zcs_azzurro.dod import season_index, thresholds_dod, weather_index
from datetime import date

# Valori di esempio di un inverter HYD-ES reale
RT = {512: [2, 0, 0, 0, 0, 0, 2347, 50, 0, 0, 0, 0, 5004, 0, 526, 0, 26, 13, 65441, 88, 65530, 0, 2360, 0, 139, 1,
            1864, 1991, 0, 26176, 0, 6263, 0, 11154, 0, 27817, 2, 0, 0, 10433, 0, 8040, 2, 128, 535],
      557: [3829, 54, 17, 2349, 453, 0, 0, 0, 0, 0, 97, 33, 19, 1, 3, 8194, 0, 0, 0, 0, 0, 0, 364, 0, 26671, 12000,
            12000, 682, 1, 0, 0, 0, 0, 0, 0, 1775, 0, 0, 2220, 5, 0]}
BAT = [0, 300, 0, 561, 6500, 571, 480, 6500, 420, 50, 75, 4670, 5208, 3, 0, 10]


class FakeLogger:
    def __init__(self):
        self.holding = {}
        for start, vals in RT.items():
            self.holding.update({start + i: v for i, v in enumerate(vals)})
        self.holding[4608] = 0
        self.inp = {4272 + i: v for i, v in enumerate(BAT)}
        self.writes = []
        self.server = None

    async def start(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def handle(self, r, w):
        try:
            while True:
                h = await r.readexactly(11)
                ln = struct.unpack("<H", h[1:3])[0]
                seq, serial = h[5], struct.unpack("<I", h[7:11])[0]
                rest = await r.readexactly(ln + 2)
                assert sum((h + rest[:ln])[1:]) & 0xFF == rest[ln]
                mb = rest[15:ln]
                assert crc16_modbus(mb[:-2]) == mb[-2:]
                sl, fc, addr, qty = struct.unpack(">BBHH", mb[:6])
                if fc in (3, 4):
                    table = self.holding if fc == 3 else self.inp
                    if any(addr + i not in table for i in range(qty)):
                        resp = bytes([sl, fc | 0x80, 2])
                    else:
                        data = b"".join(struct.pack(">H", table[addr + i]) for i in range(qty))
                        resp = bytes([sl, fc, len(data)]) + data
                elif fc == 0x13:
                    vals = struct.unpack(">" + "H" * qty, mb[6:6 + 2 * qty])
                    self.writes.append((addr, list(vals)))
                    for i, v in enumerate(vals):
                        self.inp[addr + i] = v
                    resp = mb[:6]
                else:
                    resp = bytes([sl, fc | 0x80, 1])
                resp += crc16_modbus(resp)
                payload = bytes([0x02, 0x01]) + b"\x00" * 12 + resp
                hdr = bytes([0xA5]) + struct.pack("<H", len(payload)) + struct.pack("<H", 0x1510) + bytes([seq, 0]) + \
                    struct.pack("<I", serial)
                body = hdr + payload
                w.write(body + bytes([sum(body[1:]) & 0xFF, 0x15]))
                await w.drain()
        except asyncio.IncompleteReadError:
            pass


OPEN_METEO = {
    "daily": {
        "time": ["2026-11-22", "2026-11-23", "2026-11-24", "2026-11-25"],
        "shortwave_radiation_sum": [7.2, 6.94, 4.46, 2.7],
        "sunshine_duration": [202.0, 27491.0, 17121.0, 11197.0],
        "daylight_duration": [34042.0, 33928.0, 33817.0, 33708.0],
        "precipitation_sum": [7.5, 0.0, 0.4, 23.7],
        "precipitation_probability_max": [100, 3, 15, 96],
    },
    "hourly": {"time": [f"2026-11-23T{h:02d}:00" for h in range(24)], "cloud_cover": [60] * 24},
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations, socket_enabled):
    yield


def test_math():
    assert season_index(date(2026, 12, 21)) < 0.01
    assert season_index(date(2026, 6, 21)) > 0.99
    assert thresholds_dod(0, 0, 50, 75, 90) == 50
    assert thresholds_dod(0, 1, 50, 75, 90) == 75
    assert thresholds_dod(1, 0, 50, 75, 90) == 75
    assert thresholds_dod(1, 1, 50, 75, 90) == 90
    assert 75 <= thresholds_dod(0.5, 1, 50, 75, 90) <= 85


async def _setup(hass, fake, options):
    port = await fake.start()
    entry = MockConfigEntry(domain=DOMAIN, unique_id="1234567890", title="ZCS Azzurro",
                            data={"host": "127.0.0.1", "port": port, "serial": 1234567890, "slave": 1,
                                  "scan_interval": 15},
                            options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_sensors_and_write(hass):
    fake = FakeLogger()
    entry = await _setup(hass, fake, {})
    st = lambda e: hass.states.get(e).state  # noqa: E731
    assert st("sensor.zcs_azzurro_batteria_soc") == "26"
    assert float(st("sensor.zcs_azzurro_batteria_tensione")) == 52.6
    assert float(st("sensor.zcs_azzurro_potenza_rete")) == -950
    assert float(st("sensor.zcs_azzurro_potenza_prelevata_dalla_rete")) == 950
    assert float(st("sensor.zcs_azzurro_potenza_consumo_casa")) == 880
    assert st("sensor.zcs_azzurro_produzione_fv_totale") == "26176"
    assert float(st("sensor.zcs_azzurro_produzione_fv_oggi")) == 1.39
    assert st("sensor.zcs_azzurro_stato_inverter") == "Normale"
    assert st("number.zcs_azzurro_profondita_di_scarica_in_rete") == "50"
    assert st("number.zcs_azzurro_profondita_di_scarica_in_eps") == "75"
    assert st("select.zcs_azzurro_dod_modalita") == "IA"
    assert st("switch.zcs_azzurro_dod_solo_simulazione") == "on"

    await hass.services.async_call("number", "set_value",
                                   {"entity_id": "number.zcs_azzurro_profondita_di_scarica_in_rete", "value": 65},
                                   blocking=True)
    assert fake.writes == [(4272, [0, 300, 0, 561, 6500, 571, 480, 6500, 420, 65, 75, 4670, 5208, 3, 0, 10])]
    await hass.async_block_till_done()
    assert st("number.zcs_azzurro_profondita_di_scarica_in_rete") == "65"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_dod_ai_openai_and_fallback(hass, aioclient_mock):
    aioclient_mock.get("https://api.open-meteo.com/v1/forecast", json=OPEN_METEO)
    aioclient_mock.post("https://api.deepseek.com/chat/completions",
                        json={"choices": [{"message": {"content": '```json\n{"dod": 62, "motivazione": "test"}\n```'}}]})
    fake = FakeLogger()
    entry = await _setup(hass, fake, {"ai_provider": "openai_compatibile", "ai_base_url": "https://api.deepseek.com",
                                      "ai_api_key": "x", "ai_model": "deepseek-chat"})
    # IA: 62 -> arrotondato a 60, applicato
    r = await hass.services.async_call(DOMAIN, "valuta_dod", {"applica": True}, blocking=True, return_response=True)
    assert r["fonte"] == "IA" and r["dod"] == 60, r
    assert r["scrittura"].startswith("OK"), r
    assert fake.inp[4281] == 60
    s = hass.states.get("sensor.zcs_azzurro_dod_ultima_decisione")
    assert s.state == "60" and s.attributes["fonte"] == "IA"

    # Soglie
    await hass.services.async_call("select", "select_option",
                                   {"entity_id": "select.zcs_azzurro_dod_modalita", "option": "Soglie"}, blocking=True)
    r = await hass.services.async_call(DOMAIN, "valuta_dod", {}, blocking=True, return_response=True)
    assert r["fonte"] == "soglie" and 50 <= r["dod"] <= 75, r
    assert r["scrittura"] == "simulazione, non scritto"

    # IA che fallisce -> fallback soglie
    await hass.services.async_call("select", "select_option",
                                   {"entity_id": "select.zcs_azzurro_dod_modalita", "option": "IA"}, blocking=True)
    aioclient_mock.clear_requests()
    aioclient_mock.get("https://api.open-meteo.com/v1/forecast", json=OPEN_METEO)
    aioclient_mock.post("https://api.deepseek.com/chat/completions", status=500, json={"error": "boom"})
    r = await hass.services.async_call(DOMAIN, "valuta_dod", {}, blocking=True, return_response=True)
    assert r["fonte"] == "soglie" and "errore_ia" in r, r
    await hass.config_entries.async_unload(entry.entry_id)


async def test_config_flow(hass):
    fake = FakeLogger()
    port = await fake.start()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    with patch("custom_components.zcs_azzurro.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "127.0.0.1", "port": port, "serial": "1234567890", "slave": 1,
                                "scan_interval": 15})
    assert result["type"] == "create_entry", result
    assert result["data"]["serial"] == 1234567890


async def test_options_flow(hass):
    fake = FakeLogger()
    entry = await _setup(hass, fake, {})
    for provider, step_input in [
        ("openai_compatibile", {"ai_base_url": "https://api.deepseek.com", "ai_api_key": "k", "ai_model": "deepseek-chat"}),
        ("nessuna", None),
    ]:
        r = await hass.config_entries.options.async_init(entry.entry_id)
        assert r["type"] == "form" and r["step_id"] == "init"
        r = await hass.config_entries.options.async_configure(
            r["flow_id"], {"notify_service": "notify.mobile_app_mio_telefono", "sunset_offset": 15, "ai_provider": provider})
        if step_input is not None:
            assert r["type"] == "form" and r["step_id"] == provider, r
            r = await hass.config_entries.options.async_configure(r["flow_id"], step_input)
        assert r["type"] == "create_entry", r
        await hass.async_block_till_done()
        assert entry.options["ai_provider"] == provider
    # step entita' (ha_text_ai): verifica solo che il form si apra
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], {"sunset_offset": 15, "ai_provider": "ha_text_ai"})
    assert r["type"] == "form" and r["step_id"] == "ha_text_ai", r
    await hass.config_entries.async_unload(entry.entry_id)


async def test_tolerates_transient_failures(hass):
    from custom_components.zcs_azzurro.client import ZcsError
    fake = FakeLogger()
    entry = await _setup(hass, fake, {})
    coord = entry.runtime_data.coordinator
    with patch.object(coord.client, "read_holding", side_effect=ZcsError("timeout")):
        for _ in range(4):
            await coord.async_refresh()
            await hass.async_block_till_done()
            assert hass.states.get("sensor.zcs_azzurro_batteria_soc").state == "26"
        await coord.async_refresh()  # quinta lettura fallita consecutiva
        await hass.async_block_till_done()
        assert hass.states.get("sensor.zcs_azzurro_batteria_soc").state == "unavailable"
    await coord.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.zcs_azzurro_batteria_soc").state == "26"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_notify_entity_or_action(hass, aioclient_mock):
    from pytest_homeassistant_custom_component.common import async_mock_service
    aioclient_mock.get("https://api.open-meteo.com/v1/forecast", json=OPEN_METEO)
    send_msg = async_mock_service(hass, "notify", "send_message")
    legacy = async_mock_service(hass, "notify", "mobile_app_mio_telefono")
    hass.states.async_set("notify.mio_telefono", "unknown")
    fake = FakeLogger()
    # 1) entita' notify
    entry = await _setup(hass, fake, {"notify_service": "notify.mio_telefono"})
    await hass.services.async_call(DOMAIN, "valuta_dod", {"notifica": True}, blocking=True, return_response=True)
    assert len(send_msg) == 1 and send_msg[0].data["entity_id"] == "notify.mio_telefono"
    # 2) azione legacy
    hass.config_entries.async_update_entry(entry, options={"notify_service": "notify.mobile_app_mio_telefono"})
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "valuta_dod", {"notifica": True}, blocking=True, return_response=True)
    assert len(legacy) == 1 and "DoD" in legacy[0].data["title"]
    await hass.config_entries.async_unload(entry.entry_id)
