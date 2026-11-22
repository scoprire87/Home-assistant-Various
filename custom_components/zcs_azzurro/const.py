"""Costanti dell'integrazione ZCS Azzurro."""
from __future__ import annotations

DOMAIN = "zcs_azzurro"
MANUFACTURER = "ZCS / Sofar"

# --- connessione (config entry data) ---
CONF_SERIAL = "serial"          # seriale del datalogger Wi-Fi (Solarman V5)
CONF_SLAVE = "slave"
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_PORT = 8899
DEFAULT_SLAVE = 1
DEFAULT_SCAN_INTERVAL = 15      # secondi

# --- opzioni ---
CONF_NOTIFY = "notify_service"          # es. notify.mobile_app_mio_telefono
CONF_SUNSET_OFFSET = "sunset_offset"    # minuti prima del tramonto
DEFAULT_SUNSET_OFFSET = 15
CONF_AI_PROVIDER = "ai_provider"
CONF_AI_ENTITY = "ai_entity"            # ai_task.* / sensor.ha_text_ai_* / agente conversation
CONF_AI_BASE_URL = "ai_base_url"
CONF_AI_API_KEY = "ai_api_key"
CONF_AI_MODEL = "ai_model"

AI_NONE = "nessuna"
AI_TASK = "ai_task"
AI_HA_TEXT_AI = "ha_text_ai"
AI_CONVERSATION = "conversation"
AI_OPENAI = "openai_compatibile"
AI_PROVIDERS = [AI_NONE, AI_TASK, AI_HA_TEXT_AI, AI_CONVERSATION, AI_OPENAI]
DEFAULT_AI_BASE_URL = "https://api.deepseek.com"
DEFAULT_AI_MODEL = "deepseek-chat"

# --- modalita' DoD ---
MODE_AI = "IA"
MODE_THRESHOLDS = "Soglie"
MODE_MANUAL = "Manuale"
DOD_MODES = [MODE_AI, MODE_THRESHOLDS, MODE_MANUAL]

# soglie predefinite (pioggia inverno / sole inverno = pioggia estate / sole estate)
DEFAULT_T_LOW = 50
DEFAULT_T_MID = 75
DEFAULT_T_HIGH = 90

# --- registri ---
# Tempo reale (Modbus FC 0x03, holding) 0x0200-0x0255
RT_BLOCKS = [(512, 45), (557, 41)]
# Parametri batteria (lettura FC 0x04, scrittura FC 0x13 proprietaria ZCS) 0x10B0-0x10BF
BAT_START = 4272
BAT_QTY = 16
REG_DOD = 4281          # profondita' di scarica in rete
REG_DOD_EPS = 4282      # profondita' di scarica in EPS
REG_SAFETY_BUFFER = 4287
DOD_MIN, DOD_MAX = 20, 90   # limiti dell'app Azzurro Operators
# Modalita' di lavoro (FC 0x03)
REG_WORK_MODE = 4608
SLOW_REFRESH_SECONDS = 300

SIGNAL_DOD_UPDATE = f"{DOMAIN}_dod_update_{{}}"
