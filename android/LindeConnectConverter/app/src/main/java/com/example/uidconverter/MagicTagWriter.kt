package com.example.uidconverter

import android.nfc.Tag
import android.nfc.tech.MifareClassic
import android.nfc.tech.NfcA

/**
 * Scrittura dell'UID su una "magic card" MIFARE Classic (13,56 MHz) con blocco 0 riscrivibile
 * (gen2 / CUID). Serve per creare un tag con un UID scelto, da registrare poi in connect:desk.
 *
 * Funziona solo se:
 *  - il telefono ha un chip NFC che supporta MIFARE Classic (molti NXP sì, molti altri no);
 *  - il tag appoggiato è una magic card gen2/CUID con UID a 4 byte;
 *  - la chiave del settore 0 è ancora quella di default (FF FF FF FF FF FF).
 */
sealed class WriteResult {
    data class Success(val uid: String) : WriteResult()
    data class Error(val message: String) : WriteResult()
}

fun writeUidToMagicTag(tag: Tag, uidHex: String): WriteResult {
    val clean = uidHex.replace(":", "").replace(" ", "").replace("-", "").uppercase()
    if (clean.length != 8 || clean.any { it !in "0123456789ABCDEF" }) {
        return WriteResult.Error("La scrittura dal telefono è possibile solo con UID a 4 byte (8 cifre esadecimali).")
    }
    val uid = ByteArray(4) { clean.substring(it * 2, it * 2 + 2).toInt(16).toByte() }

    // Verifica che il telefono/tag parli MIFARE Classic
    val techs = tag.techList.toList()
    if (MifareClassic::class.java.name !in techs) {
        val isNfcA = NfcA::class.java.name in techs
        return WriteResult.Error(
            if (isNfcA)
                "Tag 13,56 MHz riconosciuto ma non come MIFARE Classic: questo telefono non supporta MIFARE Classic, oppure non è una magic card MIFARE Classic. Serve un telefono con chip NXP o un Flipper/Proxmark."
            else
                "Tag non compatibile. Serve una magic card MIFARE Classic gen2/CUID a 13,56 MHz."
        )
    }

    val mc = MifareClassic.get(tag)
        ?: return WriteResult.Error("Questo telefono non supporta MIFARE Classic. Usa un Flipper Zero o un Proxmark.")

    return try {
        mc.connect()

        // Blocco 0: UID(4) + BCC(1) + SAK(1) + ATQA(2) + dati produttore(8).
        // Teniamo i dati produttore attuali e ricalcoliamo il BCC per l'UID nuovo.
        val block0 = ByteArray(16)
        val keyA = MifareClassic.KEY_DEFAULT
        if (!mc.authenticateSectorWithKeyA(0, keyA)) {
            return WriteResult.Error("Autenticazione fallita: non sembra una magic card con chiave di default.")
        }
        val current = runCatching { mc.readBlock(0) }.getOrNull()
        if (current != null && current.size == 16) System.arraycopy(current, 0, block0, 0, 16)

        System.arraycopy(uid, 0, block0, 0, 4)
        block0[4] = (uid[0].toInt() xor uid[1].toInt() xor uid[2].toInt() xor uid[3].toInt()).toByte() // BCC
        if (current == null || current.size != 16) {
            block0[5] = 0x08               // SAK tipico MIFARE Classic 1K
            block0[6] = 0x04; block0[7] = 0x00 // ATQA
        }

        mc.writeBlock(0, block0)
        WriteResult.Success(clean)
    } catch (e: Exception) {
        WriteResult.Error("Scrittura non riuscita: ${e.message ?: "errore sconosciuto"}. Serve una magic card gen2/CUID.")
    } finally {
        runCatching { mc.close() }
    }
}
