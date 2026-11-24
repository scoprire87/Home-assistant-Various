# Linde Connect Converter

App Android (Jetpack Compose) che legge l'UID dei tag NFC e lo converte nel codice gettone Linde
(`63` + byte dell'UID in ordine inverso). I codici sono raggruppati per cliente e operatore.

Progetto ricostruito dall'APK `app-debug.apk` (v1.0) con in più:

- **Esporta DB** – salva tutti i clienti e i codici in un unico file `.json` (Download, Drive, ecc.).
- **Importa DB** – legge un file esportato e lo *unisce* ai dati esistenti: i clienti con lo stesso
  nome vengono uniti, i codici con un UID già presente vengono saltati, nulla viene cancellato.
  Accetta anche i singoli file `<cliente>.json` creati dalla versione 1.0.
- **Inserimento manuale** – nella scheda di un cliente si può scrivere l'UID (es. `AA:BB:CC:DD`)
  oppure il codice Linde (es. `63DDCCBBAA`); l'altro valore viene calcolato automaticamente.
- **Importa conducenti da backup connect:desk** – legge direttamente il backup `.zip` (o il `.dmp`
  al suo interno, dump PostgreSQL) e aggiunge a un cliente tutti i conducenti attivi con badge RFID:
  operatore = nome e cognome, codice Linde = `rfid_type` in esadecimale (99 → `63`) + `rfid_code`
  in esadecimale, UID = gli stessi byte in ordine inverso.
- **Scrivi su tag (📝)** – accanto a ogni voce salvata, scrive il suo UID su una **magic card
  MIFARE Classic gen2/CUID a 13,56 MHz**. Serve per creare un tag con un UID scelto (p.es. un
  tag "tecnico" condiviso) da registrare poi in connect:desk. Funziona solo con UID a 4 byte,
  solo con magic card gen2/CUID e solo su telefoni che supportano MIFARE Classic (chip NXP);
  sugli altri telefoni usa un Flipper Zero o un Proxmark.

## Formato del file esportato

```json
{
  "app": "linde-connect-converter",
  "versione": 1,
  "esportato": 1764000000000,
  "clienti": [
    { "nome": "Cliente", "tags": [ { "uid": "AABBCCDD", "operatore": "Mario", "linde": "63DDCCBBAA" } ] }
  ]
}
```

## Compilare

Apri la cartella in Android Studio e premi *Run*, oppure `gradle assembleDebug`
(richiede Android SDK 36). L'APK finisce in `app/build/outputs/apk/debug/`.

Test: `./gradlew testDebugUnitTest -Pbackup=/percorso/backup.zip` verifica anche la lettura di un
backup reale (i backup non vanno messi nel repository: contengono dati personali).

> Se la versione 1.0 è stata installata da un altro PC/Android Studio, la firma di debug è
> diversa: bisogna disinstallarla prima, e i dati salvati andrebbero persi. Compilando con lo
> stesso Android Studio che ha creato la 1.0 l'aggiornamento mantiene i dati.
