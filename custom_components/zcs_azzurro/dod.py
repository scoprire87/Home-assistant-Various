"""Logica di decisione del DoD (profondita' di scarica in rete) per il giorno dopo.

Modalita':
  - IA:      chiede al provider IA configurato; se non risponde usa le soglie (fallback)
  - Soglie:  interpolazione bilineare stagione x meteo tra 3 soglie
  - Manuale: nessuna azione automatica

Soglie (default 50/75/90):
    pioggia inverno -> T_LOW, sole inverno = pioggia estate -> T_MID, sole estate -> T_HIGH
    DoD = T_LOW*(1-s)(1-m) + T_MID*(1-s)*m + T_MID*s*(1-m) + T_HIGH*s*m
    s = indice stagione (0 solstizio d'inverno, 1 solstizio d'estate, curva coseno)
    m = indice meteo di domani (0 pioggia/coperto, 1 sereno), da Open-Meteo
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_sunset
from homeassistant.util import dt as dt_util

from .const import (
    AI_CONVERSATION,
    AI_HA_TEXT_AI,
    AI_NONE,
    AI_OPENAI,
    AI_TASK,
    CONF_AI_API_KEY,
    CONF_AI_BASE_URL,
    CONF_AI_ENTITY,
    CONF_AI_MODEL,
    CONF_AI_PROVIDER,
    CONF_NOTIFY,
    CONF_SUNSET_OFFSET,
    DEFAULT_AI_BASE_URL,
    DEFAULT_AI_MODEL,
    DEFAULT_SUNSET_OFFSET,
    DEFAULT_T_HIGH,
    DEFAULT_T_LOW,
    DEFAULT_T_MID,
    DOD_MAX,
    DOD_MIN,
    MODE_AI,
    MODE_MANUAL,
    MODE_THRESHOLDS,
    REG_DOD,
    SIGNAL_DOD_UPDATE,
)
from .coordinator import ZcsCoordinator

_LOGGER = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def season_index(day: date) -> float:
    """0 al solstizio d'inverno (21/12), 1 al solstizio d'estate (21/6)."""
    doy = day.timetuple().tm_yday
    return round((1 + math.cos(2 * math.pi * (doy - 172) / 365.25)) / 2, 3)


def weather_index(forecast: dict[str, Any]) -> float:
    """0 = pioggia/coperto, 1 = sereno, per domani (con un po' di peso ai giorni dopo)."""
    sun = forecast["rapporto_sole"]  # [domani, +2, +3] ore sole / ore luce
    m = 0.6 * sun[0] + 0.2 * (1 - forecast["nuvolosita_domani"] / 100) + 0.2 * (sum(sun) / len(sun))
    if forecast["pioggia_mm"][0] > 5:
        m *= 0.6
    return round(min(max(m, 0.0), 1.0), 3)


def thresholds_dod(s: float, m: float, low: int, mid: int, high: int) -> int:
    d = low * (1 - s) * (1 - m) + mid * (1 - s) * m + mid * s * (1 - m) + high * s * m
    return int(min(max(round(d / 5) * 5, low), high))


def parse_ai_json(text: str) -> dict[str, Any] | None:
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        data = json.loads(text[i : j + 1])
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("dod"), (int, float)):
        return None
    return data


SYSTEM_PROMPT = (
    "Sei un esperto di impianti fotovoltaici con accumulo. Decidi la profondita' di scarica in rete "
    "(DoD) della batteria per la notte e il giorno successivo di un impianto residenziale con inverter "
    "ZCS Azzurro. DoD = percentuale di capacita' utilizzabile (DoD 70% => la batteria si ferma al 30% di SoC). "
    "Criteri: periodo piovoso o poca radiazione (inverno) -> DoD basso, per preservare la batteria e tenere "
    "riserva perche' il sole non la ricarichera'; giornata di sole con buona radiazione (soprattutto estate) "
    "-> DoD alto, perche' il sole ricarichera' la batteria. Considera SoC attuale e tendenza dei giorni "
    "successivi. Il valore DEVE essere un intero multiplo di 5 tra i limiti indicati. Rispondi "
    "ESCLUSIVAMENTE con un oggetto JSON valido, senza testo prima o dopo e senza blocchi di codice: "
    '{"dod": <intero>, "motivazione": "<max 200 caratteri, in italiano>"}'
)


class DodManager:
    """Decide e applica il DoD; stato condiviso con le entita' (select, number, switch, sensor)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, coordinator: ZcsCoordinator) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.mode: str = MODE_AI
        self.simulate: bool = False
        self.t_low, self.t_mid, self.t_high = DEFAULT_T_LOW, DEFAULT_T_MID, DEFAULT_T_HIGH
        self.last: dict[str, Any] | None = None
        self._unsub = None

    @property
    def options(self) -> dict[str, Any]:
        return dict(self.entry.options)

    @property
    def signal(self) -> str:
        return SIGNAL_DOD_UPDATE.format(self.entry.entry_id)

    @callback
    def async_start(self) -> None:
        offset = int(self.options.get(CONF_SUNSET_OFFSET, DEFAULT_SUNSET_OFFSET))
        self._unsub = async_track_sunset(self.hass, self._on_sunset, timedelta(minutes=-offset))

    @callback
    def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    async def _on_sunset(self) -> None:
        if self.mode == MODE_MANUAL:
            return
        try:
            await self.async_evaluate(apply=not self.simulate, notify=True)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Errore nella decisione automatica del DoD")

    # ------------------------------------------------------------------ meteo
    async def _fetch_forecast(self) -> dict[str, Any]:
        params = {
            "latitude": round(self.hass.config.latitude, 4),
            "longitude": round(self.hass.config.longitude, 4),
            "daily": "shortwave_radiation_sum,sunshine_duration,daylight_duration,"
            "precipitation_sum,precipitation_probability_max",
            "hourly": "cloud_cover",
            "timezone": str(self.hass.config.time_zone),
            "forecast_days": 4,
        }
        session = async_get_clientsession(self.hass)
        async with session.get(OPEN_METEO_URL, params=params, timeout=30) as resp:
            resp.raise_for_status()
            data = await resp.json()
        d = data["daily"]
        tomorrow = d["time"][1]
        clouds = [
            c
            for t, c in zip(data["hourly"]["time"], data["hourly"]["cloud_cover"])
            if t.startswith(tomorrow) and 9 <= int(t[11:13]) <= 16 and c is not None
        ]
        return {
            "giorni": d["time"][1:4],
            "radiazione_kwh_m2": [round((x or 0) / 3.6, 2) for x in d["shortwave_radiation_sum"][1:4]],
            "ore_sole": [round((x or 0) / 3600, 1) for x in d["sunshine_duration"][1:4]],
            "ore_luce": [round((x or 0) / 3600, 1) for x in d["daylight_duration"][1:4]],
            "rapporto_sole": [
                round((s or 0) / dl, 2) if dl else 0
                for s, dl in zip(d["sunshine_duration"][1:4], d["daylight_duration"][1:4])
            ],
            "pioggia_mm": [x or 0 for x in d["precipitation_sum"][1:4]],
            "prob_pioggia": d["precipitation_probability_max"][1:4],
            "nuvolosita_domani": round(sum(clouds) / len(clouds)) if clouds else 50,
        }

    # ------------------------------------------------------------------ IA
    def _build_question(self, ctx: dict[str, Any]) -> str:
        f = ctx["meteo"]
        regs = self.coordinator.data or {}
        return (
            f"Data: {ctx['oggi']}. Decidi il DoD per domani {f['giorni'][0]}.\n"
            f"LIMITI: minimo {self.t_low}%, massimo {self.t_high}%. DoD attuale: {ctx['dod_attuale']}%.\n"
            f"BATTERIA: SoC {regs.get(528)}%, stato di salute {regs.get(567)}%.\n"
            f"OGGI: produzione FV {round((regs.get(536) or 0) * 0.01, 2)} kWh, "
            f"consumo casa {round((regs.get(539) or 0) * 0.01, 2)} kWh.\n"
            f"PREVISIONE (domani, +2, +3 giorni): radiazione {f['radiazione_kwh_m2']} kWh/m2 "
            f"(~6 estate serena, ~2.3 inverno sereno); ore di sole {f['ore_sole']} su ore di luce {f['ore_luce']}; "
            f"pioggia {f['pioggia_mm']} mm; probabilita' pioggia {f['prob_pioggia']} %; "
            f"nuvolosita' media domani 9-17: {f['nuvolosita_domani']}%.\n"
            f"Indice stagione {ctx['indice_stagione']} (0 inverno, 1 estate), indice meteo {ctx['indice_meteo']} "
            f"(0 pioggia, 1 sereno). Riferimento a soglie (pioggia inverno {self.t_low}, sole inverno/pioggia "
            f"estate {self.t_mid}, sole estate {self.t_high}): {ctx['dod_soglie']}%."
        )

    async def _ask_ai(self, question: str) -> tuple[str | None, str]:
        """Ritorna (testo risposta, descrizione provider)."""
        opts = self.options
        provider = opts.get(CONF_AI_PROVIDER, AI_NONE)
        entity = opts.get(CONF_AI_ENTITY)
        if provider == AI_NONE:
            return None, "nessuna IA configurata"
        if provider == AI_TASK:
            resp = await self.hass.services.async_call(
                "ai_task", "generate_data",
                {"task_name": "zcs_dod", "entity_id": entity, "instructions": f"{SYSTEM_PROMPT}\n\n{question}"},
                blocking=True, return_response=True,
            )
            data = (resp or {}).get("data")
            return (json.dumps(data) if isinstance(data, dict) else data), f"AI Task {entity}"
        if provider == AI_HA_TEXT_AI:
            resp = await self.hass.services.async_call(
                "ha_text_ai", "ask_question",
                {"instance": entity, "question": question, "system_prompt": SYSTEM_PROMPT,
                 "context_messages": 1, "temperature": 0.2, "max_tokens": 500},
                blocking=True, return_response=True,
            )
            if not (resp or {}).get("success", False):
                raise RuntimeError((resp or {}).get("error", "risposta non valida"))
            return resp.get("response_text"), f"HA Text AI {entity}"
        if provider == AI_CONVERSATION:
            resp = await self.hass.services.async_call(
                "conversation", "process",
                {"text": f"{SYSTEM_PROMPT}\n\n{question}", "agent_id": entity},
                blocking=True, return_response=True,
            )
            speech = (((resp or {}).get("response") or {}).get("speech") or {}).get("plain") or {}
            return speech.get("speech"), f"Conversation {entity}"
        if provider == AI_OPENAI:
            base = (opts.get(CONF_AI_BASE_URL) or DEFAULT_AI_BASE_URL).rstrip("/")
            model = opts.get(CONF_AI_MODEL) or DEFAULT_AI_MODEL
            session = async_get_clientsession(self.hass)
            async with session.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {opts.get(CONF_AI_API_KEY, '')}"},
                json={"model": model, "temperature": 0.2, "max_tokens": 500,
                      "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                   {"role": "user", "content": question}]},
                timeout=90,
            ) as resp:
                body = await resp.json(content_type=None)
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}: {str(body)[:200]}")
            return body["choices"][0]["message"]["content"], f"{model} ({base})"
        return None, f"provider sconosciuto {provider}"

    # ------------------------------------------------------------------ decisione
    async def async_evaluate(self, apply: bool, notify: bool = True) -> dict[str, Any]:
        regs = self.coordinator.data or {}
        now = dt_util.now()
        ctx: dict[str, Any] = {
            "oggi": now.strftime("%d/%m/%Y"),
            "modalita": self.mode,
            "dod_attuale": regs.get(REG_DOD),
            "soc": regs.get(528),
        }
        try:
            forecast = await self._fetch_forecast()
        except Exception as err:  # noqa: BLE001
            forecast = None
            ctx["errore_meteo"] = str(err)
        tomorrow = (now + timedelta(days=1)).date()
        s = season_index(tomorrow)
        m = weather_index(forecast) if forecast else 0.5
        ctx.update(meteo=forecast, indice_stagione=s, indice_meteo=m,
                   dod_soglie=thresholds_dod(s, m, self.t_low, self.t_mid, self.t_high))

        dod, source, reason = ctx["dod_soglie"], "soglie", (
            f"Soglie interpolate: stagione {s}, meteo {m}" + ("" if forecast else " (meteo non disponibile)")
        )
        if self.mode == MODE_AI and forecast:
            try:
                text, provider = await self._ask_ai(self._build_question(ctx))
                ctx["ia"] = provider
                parsed = parse_ai_json(text or "")
                if parsed:
                    dod = int(min(max(round(float(parsed["dod"]) / 5) * 5, self.t_low), self.t_high))
                    source, reason = "IA", str(parsed.get("motivazione", ""))[:230]
                else:
                    ctx["errore_ia"] = f"risposta non interpretabile: {(text or '')[:150]}"
                    reason = f"IA non disponibile ({provider}), usate le soglie. " + reason
            except Exception as err:  # noqa: BLE001
                ctx["errore_ia"] = str(err)[:200]
                reason = "IA non disponibile, usate le soglie. " + reason

        dod = int(min(max(dod, DOD_MIN), DOD_MAX))
        result: dict[str, Any] = {"dod": dod, "fonte": source, "motivazione": reason,
                                  "ora": now.isoformat(timespec="seconds"), **ctx}
        if not apply:
            result["scrittura"] = "simulazione, non scritto" if self.simulate else "non richiesta"
        elif dod == ctx["dod_attuale"]:
            result["scrittura"] = "non necessaria (valore invariato)"
        else:
            try:
                await self.coordinator.async_write_battery_param(REG_DOD, dod)
                result["scrittura"] = f"OK, inverter ora a {dod}%"
            except Exception as err:  # noqa: BLE001
                result["scrittura"] = f"FALLITA: {err}"
        self.last = result
        async_dispatcher_send(self.hass, self.signal)
        if notify:
            await self._notify(result)
        return result

    async def _notify(self, r: dict[str, Any]) -> None:
        f = r.get("meteo") or {}
        msg = (
            f"{'SIMULAZIONE - ' if self.simulate else ''}DoD per domani: {r['dod']}% "
            f"(prima {r.get('dod_attuale')}%, fonte {r['fonte']}).\n"
            f"Scrittura: {r.get('scrittura')}.\n"
            f"SoC {r.get('soc')}%, sole domani {f.get('ore_sole', ['?'])[0]} h, "
            f"radiazione {f.get('radiazione_kwh_m2', ['?'])[0]} kWh/m2.\n{r['motivazione']}"
        )
        await self.hass.services.async_call(
            "persistent_notification", "create",
            {"notification_id": f"zcs_dod_{self.entry.entry_id}", "title": "ZCS - DoD batteria", "message": msg},
        )
        target = (self.options.get(CONF_NOTIFY) or "").strip()
        if target:
            domain, _, service = target.partition(".")
            if not service:
                domain, service = "notify", domain
            try:
                await self.hass.services.async_call(
                    domain, service, {"title": f"🔋 DoD {r['dod']}%", "message": msg}, blocking=True
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Notifica %s non inviata: %s", target, err)
