package com.example.uidconverter

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.nfc.NfcAdapter
import android.nfc.Tag
import android.os.Build
import android.os.Bundle
import android.provider.OpenableColumns
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import com.example.uidconverter.ui.theme.UIDConverterTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Ultimo UID letto via NFC (esadecimale maiuscolo). */
var scannedUid: MutableState<String> = mutableStateOf("")

/** UID che il prossimo tag avvicinato deve ricevere (modalità scrittura); null = lettura normale. */
var pendingWriteUid: MutableState<String?> = mutableStateOf(null)

/** Messaggio della finestra di scrittura; null = finestra chiusa. */
var writeStatus: MutableState<String?> = mutableStateOf(null)

class MainActivity : ComponentActivity() {

    private var nfcAdapter: NfcAdapter? = null
    private var pendingIntent: PendingIntent? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        nfcAdapter = NfcAdapter.getDefaultAdapter(this)
        pendingIntent = PendingIntent.getActivity(
            this, 0,
            Intent(this, javaClass).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_MUTABLE
        )
        setContent {
            UIDConverterTheme {
                Surface(modifier = Modifier.fillMaxSize()) { App() }
            }
        }
        handleIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        nfcAdapter?.enableForegroundDispatch(this, pendingIntent, null, null)
    }

    override fun onPause() {
        super.onPause()
        nfcAdapter?.disableForegroundDispatch(this)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent) {
        val action = intent.action
        if (action == NfcAdapter.ACTION_TAG_DISCOVERED ||
            action == NfcAdapter.ACTION_TECH_DISCOVERED ||
            action == NfcAdapter.ACTION_NDEF_DISCOVERED
        ) {
            val tag: Tag? = if (Build.VERSION.SDK_INT >= 33) {
                intent.getParcelableExtra(NfcAdapter.EXTRA_TAG, Tag::class.java)
            } else {
                @Suppress("DEPRECATION")
                intent.getParcelableExtra(NfcAdapter.EXTRA_TAG)
            }
            tag ?: return
            val target = pendingWriteUid.value
            if (target != null) {
                writeStatus.value = "Scrittura in corso… tieni fermo il tag."
                Thread {
                    val res = writeUidToMagicTag(tag, target)
                    runOnUiThread {
                        pendingWriteUid.value = null
                        writeStatus.value = when (res) {
                            is WriteResult.Success -> "✅ Fatto! La magic card ora risponde con UID ${res.uid}. Ripeti su un altro tag per farne una copia."
                            is WriteResult.Error -> "❌ ${res.message}"
                        }
                    }
                }.start()
            } else {
                scannedUid.value = tag.id.joinToString("") { "%02X".format(it) }
            }
        }
    }
}

private fun toast(context: Context, msg: String) =
    Toast.makeText(context, msg, Toast.LENGTH_LONG).show()

@Composable
fun App() {
    val context = LocalContext.current
    var clienti by remember { mutableStateOf(loadClients(context)) }
    var clienteSelezionato by remember { mutableStateOf<Cliente?>(null) }
    var screen by remember { mutableStateOf("clienti") }

    // --- Esporta: crea un file .json scelto dall'utente (Download, Drive, ecc.) ---
    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/json")
    ) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        runCatching {
            context.contentResolver.openOutputStream(uri, "wt")!!.use {
                it.write(exportDatabase(clienti).toByteArray(Charsets.UTF_8))
            }
        }.onSuccess {
            toast(context, "Esportati ${clienti.size} clienti, ${clienti.sumOf { it.tags.size }} codici")
        }.onFailure { toast(context, "Errore esportazione: ${it.message}") }
    }

    // --- Importa: legge un file .json e lo unisce ai dati esistenti ---
    val importLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        runCatching {
            val text = context.contentResolver.openInputStream(uri)!!.use {
                it.readBytes().toString(Charsets.UTF_8)
            }
            val importati = parseImport(text)
            require(importati.isNotEmpty()) { "nessun cliente trovato nel file" }
            mergeImport(context, clienti, importati)
        }.onSuccess { (nuovaLista, res) ->
            clienti = nuovaLista
            toast(context, "Importati ${res.clientiNuovi} clienti nuovi e ${res.tagNuovi} codici nuovi")
        }.onFailure { toast(context, "File non valido: ${it.message}") }
    }

    // --- Importa conducenti da un backup connect:desk (.zip o .dmp) ---
    val scope = rememberCoroutineScope()
    var caricamento by remember { mutableStateOf(false) }
    var backupLetto by remember { mutableStateOf<Pair<String, List<Conducente>>?>(null) }
    val backupLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        caricamento = true
        scope.launch {
            val res = withContext(Dispatchers.IO) {
                runCatching {
                    val nomeFile = context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
                        ?.use { c -> if (c.moveToFirst()) c.getString(0) else null }.orEmpty()
                    val lista = context.contentResolver.openInputStream(uri)!!.use {
                        conducentiDaBackup(PgDumpReader.fromStream(it))
                    }
                    nomeClienteDaFile(nomeFile) to lista
                }
            }
            caricamento = false
            res.onSuccess { backupLetto = it }
                .onFailure { toast(context, "Backup non leggibile: ${it.message}") }
        }
    }

    backupLetto?.let { (nomeSuggerito, conducenti) ->
        var nome by remember(backupLetto) { mutableStateOf(nomeSuggerito) }
        AlertDialog(
            onDismissRequest = { backupLetto = null },
            title = { Text("Importa ${conducenti.size} conducenti") },
            text = {
                Column {
                    Text("Trovati ${conducenti.size} conducenti attivi con badge RFID. In quale cliente vuoi salvarli?")
                    Spacer(Modifier.height(8.dp))
                    TextField(value = nome, onValueChange = { nome = it }, label = { Text("Nome cliente") }, singleLine = true)
                }
            },
            confirmButton = {
                TextButton(enabled = nome.isNotBlank(), onClick = {
                    val tags = androidx.compose.runtime.mutableStateListOf<TagItem>()
                    conducenti.forEach { tags.add(TagItem(it.uid, it.nome, it.linde)) }
                    val (nuovaLista, r) = mergeImport(context, clienti, listOf(Cliente(nome.trim(), tags)))
                    clienti = nuovaLista
                    backupLetto = null
                    toast(context, "Importati ${r.tagNuovi} codici (${conducenti.size - r.tagNuovi} già presenti)")
                }) { Text("Importa") }
            },
            dismissButton = { TextButton(onClick = { backupLetto = null }) { Text("Annulla") } }
        )
    }

    // --- Finestra di scrittura su magic card ---
    val wStatus by writeStatus
    wStatus?.let { msg ->
        val inCorso = pendingWriteUid.value != null
        AlertDialog(
            onDismissRequest = { pendingWriteUid.value = null; writeStatus.value = null },
            title = { Text("Scrivi su magic card") },
            text = { Text(msg) },
            confirmButton = {
                TextButton(onClick = { pendingWriteUid.value = null; writeStatus.value = null }) {
                    Text(if (inCorso) "Annulla" else "Chiudi")
                }
            }
        )
    }

    BackHandler(enabled = screen == "dettaglio") {
        screen = "clienti"
        clienteSelezionato = null
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeDrawingPadding()
            .padding(16.dp)
    ) {
        val sel = clienteSelezionato
        if (screen == "dettaglio" && sel != null) {
            DettaglioCliente(
                cliente = sel,
                onBack = { screen = "clienti"; clienteSelezionato = null; clienti = clienti.toList() }
            )
        } else {
            ListaClienti(
                clienti = clienti,
                onAdd = { nome ->
                    if (clienti.any { it.nome.equals(nome, ignoreCase = true) }) {
                        toast(context, "Cliente già esistente")
                    } else {
                        val nuovo = Cliente(nome)
                        saveClient(context, nuovo)
                        clienti = (clienti + nuovo).sortedBy { it.nome.lowercase(Locale.ROOT) }
                    }
                },
                onOpen = { clienteSelezionato = it; screen = "dettaglio" },
                onDelete = { c -> deleteClient(context, c); clienti = clienti - c },
                onExport = {
                    val data = SimpleDateFormat("yyyyMMdd_HHmm", Locale.ROOT).format(Date())
                    exportLauncher.launch("linde_clienti_$data.json")
                },
                onImport = { importLauncher.launch(arrayOf("application/json", "text/plain", "application/octet-stream")) },
                onImportBackup = { backupLauncher.launch(arrayOf("application/zip", "application/x-zip-compressed", "application/octet-stream", "*/*")) },
                caricamento = caricamento
            )
        }
    }
}

@Composable
private fun ListaClienti(
    clienti: List<Cliente>,
    onAdd: (String) -> Unit,
    onOpen: (Cliente) -> Unit,
    onDelete: (Cliente) -> Unit,
    onExport: () -> Unit,
    onImport: () -> Unit,
    onImportBackup: () -> Unit,
    caricamento: Boolean
) {
    var nomeCliente by remember { mutableStateOf("") }
    var daEliminare by remember { mutableStateOf<Cliente?>(null) }

    Text("Gestione clienti", style = MaterialTheme.typography.headlineSmall)
    Spacer(Modifier.height(12.dp))
    Row(verticalAlignment = Alignment.CenterVertically) {
        TextField(
            value = nomeCliente,
            onValueChange = { nomeCliente = it },
            label = { Text("Nome cliente") },
            singleLine = true,
            modifier = Modifier.weight(1f)
        )
        Spacer(Modifier.width(8.dp))
        Button(onClick = {
            val n = nomeCliente.trim()
            if (n.isNotEmpty()) { onAdd(n); nomeCliente = "" }
        }) { Text("Salva") }
    }
    Spacer(Modifier.height(8.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(onClick = onExport, modifier = Modifier.weight(1f)) { Text("Esporta DB") }
        OutlinedButton(onClick = onImport, modifier = Modifier.weight(1f)) { Text("Importa DB") }
    }
    OutlinedButton(onClick = onImportBackup, enabled = !caricamento, modifier = Modifier.fillMaxWidth()) {
        Text(if (caricamento) "Lettura backup in corso…" else "Importa conducenti da backup connect:desk")
    }
    Spacer(Modifier.height(12.dp))

    LazyColumn(modifier = Modifier.fillMaxSize()) {
        items(clienti, key = { it.nome }) { c ->
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 6.dp)
                    .clickable { onOpen(c) }
            ) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(c.nome, fontWeight = FontWeight.Bold)
                        Text("${c.tags.size} operatori")
                    }
                    TextButton(onClick = { daEliminare = c }) { Text("🗑") }
                }
            }
        }
    }

    daEliminare?.let { c ->
        AlertDialog(
            onDismissRequest = { daEliminare = null },
            title = { Text("Eliminare ${c.nome}?") },
            text = { Text("Verranno eliminati anche i suoi ${c.tags.size} codici.") },
            confirmButton = { TextButton(onClick = { onDelete(c); daEliminare = null }) { Text("Elimina") } },
            dismissButton = { TextButton(onClick = { daEliminare = null }) { Text("Annulla") } }
        )
    }
}

@Composable
private fun DettaglioCliente(cliente: Cliente, onBack: () -> Unit) {
    val context = LocalContext.current
    val uidNfc by scannedUid
    var nomeOperatore by remember { mutableStateOf("") }

    // Inserimento manuale: l'utente puo' scrivere l'UID oppure il codice gettone Linde
    var manuale by remember { mutableStateOf("") }
    var manualeIsLinde by remember { mutableStateOf(false) }

    // Una nuova lettura NFC svuota il campo manuale, cosi' si usa il tag appena letto
    LaunchedEffect(uidNfc) { if (uidNfc.isNotEmpty()) manuale = "" }

    val uidManuale: String? = when {
        manuale.isBlank() -> null
        manualeIsLinde -> lindeToUid(manuale)
        else -> normalizeUid(manuale)
    }
    val manualeNonValido = manuale.isNotBlank() && uidManuale == null
    val uid = if (manuale.isNotBlank()) uidManuale.orEmpty() else uidNfc
    val output = if (uid.isNotEmpty()) convertUid(uid) else ""

    TextButton(onClick = onBack) { Text("←") }
    Text(cliente.nome, style = MaterialTheme.typography.headlineSmall)
    Spacer(Modifier.height(8.dp))

    Text("UID: ${uid.ifEmpty { "avvicina un tag NFC o inseriscilo a mano" }}", fontFamily = FontFamily.Monospace)
    Text(
        "Codice gettone Linde: ${if (manualeNonValido) "—" else output}",
        fontFamily = FontFamily.Monospace,
        fontWeight = FontWeight.Bold
    )
    Spacer(Modifier.height(12.dp))

    Text("Inserimento manuale", style = MaterialTheme.typography.titleSmall)
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        FilterChip(selected = !manualeIsLinde, onClick = { manualeIsLinde = false }, label = { Text("UID") })
        FilterChip(selected = manualeIsLinde, onClick = { manualeIsLinde = true }, label = { Text("Codice Linde") })
    }
    TextField(
        value = manuale,
        onValueChange = { manuale = it },
        label = { Text(if (manualeIsLinde) "Codice Linde (es. 63DDCCBBAA)" else "UID esadecimale (es. AA:BB:CC:DD)") },
        isError = manualeNonValido,
        supportingText = if (manualeNonValido) {
            { Text(if (manualeIsLinde) "Il codice deve iniziare con 63 ed essere esadecimale" else "UID non valido") }
        } else null,
        singleLine = true,
        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters),
        modifier = Modifier.fillMaxWidth()
    )
    Spacer(Modifier.height(8.dp))

    Row(verticalAlignment = Alignment.CenterVertically) {
        TextField(
            value = nomeOperatore,
            onValueChange = { nomeOperatore = it },
            label = { Text("Operatore") },
            singleLine = true,
            modifier = Modifier.weight(1f)
        )
        Spacer(Modifier.width(8.dp))
        Button(onClick = {
            when {
                uid.isEmpty() || manualeNonValido -> toast(context, "Nessun UID valido")
                nomeOperatore.isBlank() -> toast(context, "Inserisci il nome dell'operatore")
                cliente.tags.any { it.uid.equals(uid, ignoreCase = true) } -> toast(context, "Codice già presente")
                else -> {
                    cliente.tags.add(TagItem(uid, nomeOperatore.trim(), output))
                    saveClient(context, cliente)
                    nomeOperatore = ""
                    manuale = ""
                }
            }
        }) { Text("Salva") }
    }
    Spacer(Modifier.height(12.dp))
    HorizontalDivider()

    LazyColumn(modifier = Modifier.fillMaxSize()) {
        items(cliente.tags.toList(), key = { it.uid }) { tag ->
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 6.dp)
            ) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Operatore: ${tag.operatore}", fontWeight = FontWeight.Bold)
                        Text("UID: ${tag.uid}", fontFamily = FontFamily.Monospace)
                        Text("Linde: ${tag.linde}", fontFamily = FontFamily.Monospace)
                    }
                    TextButton(onClick = {
                        pendingWriteUid.value = tag.uid
                        writeStatus.value = "Avvicina una magic card (13,56 MHz) al telefono per scrivervi l'UID ${tag.uid}…"
                    }) { Text("📝") }
                    TextButton(onClick = {
                        cliente.tags.remove(tag)
                        saveClient(context, cliente)
                    }) { Text("🗑") }
}
            }
        }
    }
}

/** "backup_tricom_08_10_25.zip" -> "tricom" */
private fun nomeClienteDaFile(nomeFile: String): String =
    nomeFile.substringBeforeLast('.')
        .removePrefix("backup_")
        .replace(Regex("""[_-]\d{2}[_-]\d{2}[_-]\d{2,4}$"""), "")
        .ifEmpty { "Backup" }
