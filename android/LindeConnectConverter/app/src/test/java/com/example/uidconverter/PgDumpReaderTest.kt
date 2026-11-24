package com.example.uidconverter

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

class PgDumpReaderTest {

    @Test
    fun conversioneUid() {
        assertEquals("63DDCCBBAA", convertUid("AA:BB:CC:DD"))
        assertEquals("AABBCCDD", lindeToUid("63DDCCBBAA"))
        assertEquals("UID non valido", convertUid("ABC"))
    }

    /** Esegui con: gradle test -Pbackup=/percorso/backup.zip (il backup non e' nel repository). */
    @Test
    fun leggeConducentiDaBackup() {
        val path = System.getProperty("backup").orEmpty()
        assumeTrue("nessun backup indicato", path.isNotEmpty() && File(path).exists())
        val conducenti = File(path).inputStream().use { conducentiDaBackup(PgDumpReader.fromStream(it)) }
        println("Conducenti letti: ${conducenti.size}")
        conducenti.forEach { println("  ${it.nome.take(1)}.  UID=${it.uid}  Linde=${it.linde}") }
        assertTrue(conducenti.isNotEmpty())
        conducenti.filter { it.linde.startsWith("63") }.forEach { assertEquals(it.linde, convertUid(it.uid)) }
    }
}
