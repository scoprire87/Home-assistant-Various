# ZCS Azzurro (ibrido) per Home Assistant

Integrazione per gli inverter ibridi **ZCS Azzurro HYD-ES** (famiglia Sofar), collegati tramite il
datalogger Wi-Fi (protocollo Solarman V5, porta 8899).

## Funzioni

- **Circa 50 sensori** dalla mappa registri ufficiale dell'app *Azzurro Operators*: potenze (FV, casa,
  rete, batteria, con versioni separate prelievo/immissione e carica/scarica per la dashboard Energia),
  SoC, SOH, tensione, temperatura e cicli batteria, stato e allarmi inverter, energia giornaliera
  (risoluzione 0,01 kWh) e totale.
- **Parametri batteria modificabili**: profondità di scarica in rete, in EPS e buffer di sicurezza.
  La scrittura avviene come nell'app ufficiale (funzione Modbus proprietaria ZCS `0x13` sull'intero
  blocco 0x10B0–0x10BF, con rilettura e verifica).
- **DoD automatico** calcolato ogni giorno prima del tramonto per il giorno dopo:
  - **IA**: chiede la decisione a un'intelligenza artificiale a scelta (AI Task di Home Assistant,
    HA Text AI, agente di conversazione o qualsiasi API compatibile OpenAI come DeepSeek, OpenAI, Groq).
    Se l'IA non risponde usa le soglie.
  - **Soglie**: interpolazione stagione × meteo fra tre valori regolabili
    (predefiniti: pioggia inverno 50 %, sole inverno / pioggia estate 75 %, sole estate 90 %).
  - **Manuale**: nessuna azione automatica.
  - Meteo da Open-Meteo (ore di sole, nuvolosità, pioggia), interruttore *solo simulazione*,
    notifica con l'esito.

## Installazione (HACS)

1. HACS → menu ⋮ → *Repository personalizzati* → aggiungi l'URL di questo repository, tipo *Integrazione*.
2. Installa **ZCS Azzurro (ibrido)** e riavvia Home Assistant.
3. *Impostazioni → Dispositivi e servizi → Aggiungi integrazione → ZCS Azzurro*: inserisci IP, porta
   (8899) e numero di serie del datalogger.
4. Nelle **Opzioni** dell'integrazione scegli il servizio di notifica e il fornitore di IA.

## Entità principali

| Entità | Descrizione |
|---|---|
| `select.zcs_azzurro_dod_modalita` | IA / Soglie / Manuale |
| `switch.zcs_azzurro_dod_solo_simulazione` | se attivo, calcola e notifica ma non scrive |
| `number.zcs_azzurro_dod_soglia_*` | le tre soglie |
| `number.zcs_azzurro_profondita_di_scarica_in_rete` | DoD attuale dell'inverter (scrivibile) |
| `sensor.zcs_azzurro_dod_ultima_decisione` | ultimo valore deciso, con fonte e motivazione |
| `button.zcs_azzurro_dod_calcola_*` | calcolo immediato, con o senza applicazione |

Servizio `zcs_azzurro.valuta_dod` (`applica`, `notifica`) che restituisce la decisione completa.

## Avvertenze

Progetto non ufficiale, non affiliato a ZCS. La scrittura dei parametri batteria replica il
comportamento dell'app ufficiale; usala a tuo rischio. Al primo avvio il DoD automatico parte in
modalità *solo simulazione*.
