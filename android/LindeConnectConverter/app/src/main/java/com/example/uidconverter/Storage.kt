package com.example.uidconverter

import android.content.Context
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.snapshots.SnapshotStateList
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.Locale

data class TagItem(val uid: String, val operatore: String, val linde: String)

data class Cliente(val nome: String, val tags: SnapshotStateList<TagItem> = mutableStateListOf())

// ---------------------------------------------------------------------------
// Conversione UID <-> codice gettone Linde
// Il codice Linde e' "63" seguito dai byte dell'UID in ordine inverso.
// ---------------------------------------------------------------------------

private fun cleanHex(s: String): String =
    s.replace(":", "").replace(" ", "").replace("-", "").uppercase(Locale.ROOT)

private fun isHex(s: String) = s.all { it in '0'..'9' || it in 'A'..'F' }

fun convertUid(uid: String): String {
    val clean = cleanHex(uid)
    if (clean.isEmpty() || clean.length % 2 != 0 || !isHex(clean)) return "UID non valido"
    return "63" + clean.chunked(2).reversed().joinToString("")
}

/** Ricava l'UID da un codice gettone Linde. Restituisce null se il codice non e' valido. */
fun lindeToUid(linde: String): String? {
    val clean = cleanHex(linde)
    if (clean.length < 4 || clean.length % 2 != 0 || !isHex(clean) || !clean.startsWith("63")) return null
    return clean.substring(2).chunked(2).reversed().joinToString("")
}

/** Normalizza un UID inserito a mano (toglie separatori, maiuscolo). Null se non valido. */
fun normalizeUid(uid: String): String? {
    val clean = cleanHex(uid)
    if (clean.isEmpty() || clean.length % 2 != 0 || !isHex(clean)) return null
    return clean
}

// ---------------------------------------------------------------------------
// JSON (stesso formato dei file gia' salvati dall'app: {"nome":..,"tags":[{uid,operatore,linde}]})
// ---------------------------------------------------------------------------

private fun Cliente.toJson(): JSONObject = JSONObject().apply {
    put("nome", nome)
    put("tags", JSONArray().apply {
        tags.forEach { t ->
            put(JSONObject().put("uid", t.uid).put("operatore", t.operatore).put("linde", t.linde))
        }
    })
}

private fun clienteFromJson(o: JSONObject): Cliente? {
    val nome = o.optString("nome").trim()
    if (nome.isEmpty()) return null
    val list = mutableStateListOf<TagItem>()
    val arr = o.optJSONArray("tags") ?: JSONArray()
    for (i in 0 until arr.length()) {
        val t = arr.optJSONObject(i) ?: continue
        val uid = t.optString("uid")
        if (uid.isEmpty()) continue
        val linde = t.optString("linde").ifEmpty { convertUid(uid) }
        list.add(TagItem(uid, t.optString("operatore"), linde))
    }
    return Cliente(nome, list)
}

// ---------------------------------------------------------------------------
// Salvataggio su file interni (un file .json per cliente)
// ---------------------------------------------------------------------------

private fun fileFor(context: Context, nome: String) =
    File(context.filesDir, nome.replace('/', '_') + ".json")

fun saveClient(context: Context, cliente: Cliente) {
    fileFor(context, cliente.nome).writeText(cliente.toJson().toString())
}

fun loadClients(context: Context): List<Cliente> {
    val files = context.filesDir.listFiles() ?: return emptyList()
    return files
        .filter { it.extension == "json" }
        .mapNotNull { f -> runCatching { clienteFromJson(JSONObject(f.readText())) }.getOrNull() }
        .sortedBy { it.nome.lowercase(Locale.ROOT) }
}

fun deleteClient(context: Context, cliente: Cliente) {
    val file = fileFor(context, cliente.nome)
    if (file.exists()) file.delete()
}

// ---------------------------------------------------------------------------
// Esportazione / importazione database
// ---------------------------------------------------------------------------

fun exportDatabase(clienti: List<Cliente>): String =
    JSONObject().apply {
        put("app", "linde-connect-converter")
        put("versione", 1)
        put("esportato", System.currentTimeMillis())
        put("clienti", JSONArray().apply { clienti.forEach { put(it.toJson()) } })
    }.toString(2)

/**
 * Legge un file di esportazione. Accetta:
 *  - il formato di esportazione completo {"clienti":[...]}
 *  - un array di clienti [...]
 *  - un singolo file cliente {"nome":..,"tags":[...]} (come quelli salvati dall'app)
 */
fun parseImport(text: String): List<Cliente> {
    val trimmed = text.trim()
    val arr: JSONArray = when {
        trimmed.startsWith("[") -> JSONArray(trimmed)
        else -> {
            val o = JSONObject(trimmed)
            o.optJSONArray("clienti") ?: JSONArray().put(o)
        }
    }
    return (0 until arr.length()).mapNotNull { i -> arr.optJSONObject(i)?.let(::clienteFromJson) }
}

data class ImportResult(val clientiNuovi: Int, val tagNuovi: Int)

/**
 * Unisce i clienti importati con quelli esistenti: i clienti con lo stesso nome vengono
 * uniti, i tag con un UID gia' presente vengono saltati. Nessun dato esistente viene cancellato.
 */
fun mergeImport(context: Context, esistenti: List<Cliente>, importati: List<Cliente>): Pair<List<Cliente>, ImportResult> {
    val result = esistenti.toMutableList()
    var clientiNuovi = 0
    var tagNuovi = 0
    for (imp in importati) {
        val target = result.firstOrNull { it.nome.equals(imp.nome, ignoreCase = true) }
        if (target == null) {
            result.add(imp)
            clientiNuovi++
            tagNuovi += imp.tags.size
            saveClient(context, imp)
        } else {
            var changed = false
            for (t in imp.tags) {
                if (target.tags.none { it.uid.equals(t.uid, ignoreCase = true) }) {
                    target.tags.add(t)
                    tagNuovi++
                    changed = true
                }
            }
            if (changed) saveClient(context, target)
        }
    }
    return result.sortedBy { it.nome.lowercase(Locale.ROOT) } to ImportResult(clientiNuovi, tagNuovi)
}
