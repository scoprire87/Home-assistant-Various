"""Costanti dell'integrazione Immergas Modbus (Magis Combo V2, bus BMS T-/T+)."""
from __future__ import annotations

DOMAIN = "immergas_modbus"
MANUFACTURER = "Immergas"
MODEL = "Magis Combo V2 (bus BMS T-/T+)"

# --- connessione (config entry data) ---
CONF_SLAVE = "slave"
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_PORT = 502          # Elfin EW11 in Modbus TCP server
DEFAULT_SLAVE = 11          # unita' interna PdC sul bus BMS, salvo diverso nei menu
DEFAULT_SCAN_INTERVAL = 30  # secondi

# Blocchi di lettura (FC 0x03 holding). Tenuti stretti attorno ai registri noti:
# un registro inesistente in un blocco puo' far fallire l'intera lettura, quindi
# ogni blocco si legge da solo e un fallimento singolo non azzera gli altri.
# Mappa dalla comunita' (reverse engineering, NON documentazione Immergas): da validare.
REG_BLOCKS: list[tuple[int, int]] = [
    (2000, 1),   # modo operativo
    (2095, 1),   # setpoint sanitario
    (2100, 1),   # codice guasto
    (3000, 3),   # mandata impianto, ritorno PdC, temperatura esterna
    (3016, 1),   # temperatura accumulo sanitario
    (3029, 1),   # ritorno unita' interna
    (3056, 1),   # liquido circuito chiller
]
