package com.example.uidconverter

import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.util.zip.Inflater
import java.util.zip.ZipInputStream

/**
 * Lettore minimale dei dump PostgreSQL in formato "custom" (pg_dump -Fc), come i backup di
 * Linde connect:desk (*.dmp, anche dentro uno .zip). Estrae solo i dati delle tabelle (COPY).
 */
class PgDumpReader(private val buf: ByteArray) {

    class Table(val columns: List<String>, val rows: List<List<String?>>) {
        fun rowsAsMaps(): List<Map<String, String?>> = rows.map { r -> columns.zip(r).toMap() }
    }

    private var pos = 0
    private var intSize = 4
    private var offSize = 8
    private var vmaj = 0
    private var vmin = 0
    private var compressed = false

    private class TocEntry(val dumpId: Int, val desc: String, val namespace: String?, val tag: String, val copyStmt: String?)

    private val toc = mutableListOf<TocEntry>()

    private fun version(maj: Int, min: Int) = vmaj > maj || (vmaj == maj && vmin >= min)

    private fun byte(): Int {
        if (pos >= buf.size) throw IllegalArgumentException("file troncato")
        return buf[pos++].toInt() and 0xFF
    }

    private fun readInt(): Int {
        val sign = byte()
        var v = 0L
        for (i in 0 until intSize) v = v or (byte().toLong() shl (8 * i))
        val r = v.toInt()
        return if (sign != 0) -r else r
    }

    private fun readStr(): String? {
        val len = readInt()
        if (len < 0) return null
        if (pos + len > buf.size) throw IllegalArgumentException("file troncato")
        val s = String(buf, pos, len, Charsets.UTF_8)
        pos += len
        return s
    }

    private fun skipOffset() { pos += 1 + offSize }

    init {
        if (buf.size < 5 || String(buf, 0, 5, Charsets.US_ASCII) != "PGDMP") {
            throw IllegalArgumentException("non è un backup PostgreSQL (.dmp)")
        }
        pos = 5
        vmaj = byte(); vmin = byte(); byte()
        intSize = byte(); offSize = byte()
        val format = byte()
        if (format != 1) throw IllegalArgumentException("formato di backup non supportato ($format)")
        compressed = if (version(1, 15)) byte() != 0 else readInt() != 0
        repeat(7) { readInt() }          // data/ora del backup
        readStr()                         // nome database
        readStr(); readStr()              // versioni server / pg_dump
        readToc()
    }

    private fun readToc() {
        val count = readInt()
        repeat(count) {
            val dumpId = readInt()
            readInt()                                   // hadDumper
            readStr(); readStr()                        // tableoid, oid
            val tag = readStr().orEmpty()
            val desc = readStr().orEmpty()
            readInt()                                   // section
            readStr(); readStr()                        // defn, dropStmt
            val copyStmt = readStr()
            val namespace = readStr()
            readStr()                                   // tablespace
            if (version(1, 14)) readStr()               // tableam
            if (version(1, 16)) readInt()               // relkind
            readStr()                                   // owner
            readStr()                                   // withOids
            while (readStr() != null) { /* dipendenze */ }
            skipOffset()                                // posizione dati
            toc.add(TocEntry(dumpId, desc, namespace, tag, copyStmt))
        }
    }

    /** Legge i dati di più tabelle in un solo passaggio. Chiave: nome tabella (schema public). */
    fun readTables(names: Set<String>, schema: String = "public"): Map<String, Table> {
        val wanted = toc.filter { it.desc == "TABLE DATA" && it.tag in names && (it.namespace == null || it.namespace == schema) }
            .associateBy { it.dumpId }
        val result = mutableMapOf<String, Table>()
        while (pos < buf.size && result.size < wanted.size) {
            val blkType = byte()
            val id = readInt()
            val entry = wanted[id]
            val out = if (entry != null) ByteArrayOutputStream() else null
            while (true) {
                val len = readInt()
                if (len <= 0) break
                out?.write(buf, pos, len)
                pos += len
            }
            if (blkType != 1 || entry == null || out == null) continue
            val raw = out.toByteArray()
            val text = String(if (compressed) inflate(raw) else raw, Charsets.UTF_8)
            result[entry.tag] = parseCopy(entry.copyStmt.orEmpty(), text)
        }
        return result
    }

    private fun inflate(data: ByteArray): ByteArray {
        val inf = Inflater()
        inf.setInput(data)
        val out = ByteArrayOutputStream(data.size * 4)
        val tmp = ByteArray(64 * 1024)
        while (!inf.finished()) {
            val n = inf.inflate(tmp)
            if (n == 0 && (inf.needsInput() || inf.needsDictionary())) break
            out.write(tmp, 0, n)
        }
        inf.end()
        return out.toByteArray()
    }

    private fun parseCopy(copyStmt: String, text: String): Table {
        val cols = copyStmt.substringAfter('(', "").substringBefore(')', "")
            .split(',').map { it.trim().trim('"') }.filter { it.isNotEmpty() }
        val rows = text.split('\n')
            .filter { it.isNotEmpty() && it != "\\." }
            .map { line -> line.split('\t').map(::unescape) }
        return Table(cols, rows)
    }

    private fun unescape(f: String): String? {
        if (f == "\\N") return null
        if ('\\' !in f) return f
        val sb = StringBuilder()
        var i = 0
        while (i < f.length) {
            val c = f[i]
            if (c != '\\' || i + 1 >= f.length) { sb.append(c); i++; continue }
            val n = f[i + 1]
            when (n) {
                'n' -> sb.append('\n'); 't' -> sb.append('\t'); 'r' -> sb.append('\r')
                'b' -> sb.append('\b'); 'f' -> sb.append('\u000C'); 'v' -> sb.append('\u000B')
                in '0'..'7' -> {
                    var j = i + 1; var v = 0
                    while (j < f.length && j < i + 4 && f[j] in '0'..'7') { v = v * 8 + (f[j] - '0'); j++ }
                    sb.append(v.toChar()); i = j; continue
                }
                else -> sb.append(n)
            }
            i += 2
        }
        return sb.toString()
    }

    companion object {
        /** Accetta il .dmp oppure uno .zip che lo contiene. */
        fun fromStream(input: InputStream): PgDumpReader {
            val bytes = input.readBytes()
            if (bytes.size >= 4 && bytes[0] == 'P'.code.toByte() && bytes[1] == 'K'.code.toByte()) {
                ZipInputStream(bytes.inputStream()).use { zip ->
                    while (true) {
                        val e = zip.nextEntry ?: break
                        if (!e.isDirectory && e.name.endsWith(".dmp", ignoreCase = true)) {
                            return PgDumpReader(zip.readBytes())
                        }
                    }
                }
                throw IllegalArgumentException("nessun file .dmp nello zip")
            }
            return PgDumpReader(bytes)
        }
    }
}

/** Conducente letto dal backup connect:desk. */
data class Conducente(val nome: String, val uid: String, val linde: String)

/**
 * Estrae i conducenti attivi (non eliminati) con un codice RFID.
 * Il codice gettone Linde e' rfid_type in esadecimale (99 = 0x63) + rfid_code in esadecimale,
 * l'UID del tag sono gli stessi byte di rfid_code in ordine inverso.
 */
fun conducentiDaBackup(reader: PgDumpReader): List<Conducente> {
    val t = reader.readTables(setOf("drivers", "users"))
    val drivers = t["drivers"]?.rowsAsMaps() ?: throw IllegalArgumentException("tabella conducenti non trovata")
    val users = t["users"]?.rowsAsMaps().orEmpty().associateBy { it["user_id"] }
    return drivers.mapNotNull { d ->
        if (d["deleted"] == "t" || d["permanent_deleted"] == "t") return@mapNotNull null
        val code = d["rfid_code"]?.toLongOrNull() ?: return@mapNotNull null
        val type = d["rfid_type"]?.toIntOrNull() ?: 0x63
        var hex = java.lang.Long.toHexString(code).uppercase()
        while (hex.length < 8 || hex.length % 2 != 0) hex = "0$hex"
        val uid = hex.chunked(2).reversed().joinToString("")
        val linde = "%02X".format(type and 0xFF) + hex
        val u = users[d["user_id"]]
        val nome = listOfNotNull(u?.get("firstname"), u?.get("name"))
            .map { it.trim() }.filter { it.isNotEmpty() }.joinToString(" ")
            .ifEmpty { u?.get("login") ?: "Conducente ${d["driver_id"]}" }
        Conducente(nome, uid, linde)
    }.sortedBy { it.nome.lowercase() }
}
