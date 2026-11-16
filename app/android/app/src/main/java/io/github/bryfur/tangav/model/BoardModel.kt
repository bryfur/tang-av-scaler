package io.github.bryfur.tangav.model

import android.app.Application
import android.content.ContentValues
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.provider.MediaStore
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import io.github.bryfur.tangav.net.BleTransport
import io.github.bryfur.tangav.net.Discovery
import io.github.bryfur.tangav.net.Found
import io.github.bryfur.tangav.net.Transport
import io.github.bryfur.tangav.net.WifiTransport
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject
import java.net.URLEncoder

sealed interface Link {
    data object Searching : Link
    data class Connecting(val what: String) : Link
    data class Up(val t: Transport) : Link
    /** The board stopped answering: looking for it again, on either way. */
    data class Lost(val why: String) : Link
}

class BoardModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("board", 0)
    val discovery = Discovery(app)

    val link = MutableStateFlow<Link>(Link.Searching)
    val video = MutableStateFlow<JSONObject?>(null)
    val status = MutableStateFlow<JSONObject?>(null)
    val defaults = MutableStateFlow<Form?>(null)
    /** What the controls show: the board's settings, with this phone's changes not yet echoed back. */
    val form = MutableStateFlow<Form>(emptyMap())
    val advanced = MutableStateFlow(prefs.getBoolean("advanced", false))
    val messages = MutableSharedFlow<String>(extraBufferCapacity = 8)
    val capture = MutableStateFlow<Bitmap?>(null)
    val busy = MutableStateFlow<String?>(null)          // a long job's progress (a capture, an upload)
    val logKind = MutableStateFlow("console")
    val logText = MutableStateFlow("")
    val logsOpen = MutableStateFlow(false)
    val fpgaRead = MutableStateFlow<String?>(null)

    private var transport: Transport? = null
    private var poller: Job? = null
    private var sender: Job? = null
    private var touched = 0L                             // (the last local change: the board's echo waits)
    private var bluetoothAllowed = false

    fun setAdvanced(on: Boolean) {
        advanced.value = on
        prefs.edit().putBoolean("advanced", on).apply()
    }

    // ---- finding and keeping the board ----

    /** Called when the screen is shown (Bluetooth: whether its permissions were given). */
    fun start(withBluetooth: Boolean) {
        bluetoothAllowed = withBluetooth
        discovery.start(withBluetooth)
        if (transport == null && poller == null) autoConnect()
        else resume()
    }

    fun stop() {
        discovery.stop()
        poller?.cancel(); poller = null
    }

    private fun resume() {
        if (poller == null && transport != null) poller = viewModelScope.launch { pollLoop() }
    }

    /** The way to the board, chosen: the last one that worked, else Wi-Fi as soon as it is found,
     * else Bluetooth (a board paired already, or one in range). */
    private fun autoConnect() {
        poller?.cancel()
        poller = viewModelScope.launch {
            link.value = Link.Searching
            val last = prefs.getString("host", null)
            if (last != null && tryConnect(WifiTransport(last))) return@launch
            for (i in 0 until 600) {
                discovery.wifi.value.values.firstOrNull()?.host?.let { if (tryConnect(WifiTransport(it))) return@launch }
                if (i >= 8) {       // (Wi-Fi first: a couple of seconds' head start)
                    val ble = discovery.ble.value.values.sortedByDescending { it.bonded }.firstOrNull { it.bonded }
                    val lastBle = prefs.getString("ble", null)
                    val pick = ble ?: discovery.ble.value.values.firstOrNull { it.device?.address == lastBle }
                    if (pick?.device != null && tryConnect(BleTransport(pick.device))) return@launch
                }
                delay(400)
            }
        }
    }

    /** A board chosen by hand (the connection sheet): a found one, or an address typed in. */
    fun choose(f: Found, viaBluetooth: Boolean) {
        poller?.cancel()
        poller = viewModelScope.launch {
            val t = if (viaBluetooth && f.device != null) BleTransport(f.device) else WifiTransport(f.host ?: return@launch)
            if (!tryConnect(t)) {
                messages.tryEmit("${f.name}: no answer ${if (t.kind == Transport.Kind.BLUETOOTH) "over Bluetooth" else "at ${t.label}"}")
                autoConnect()
            }
        }
    }

    private suspend fun tryConnect(t: Transport): Boolean {
        link.value = Link.Connecting(t.label)
        val d = try {
            withTimeoutOrNull(if (t.kind == Transport.Kind.WIFI) 3_000 else 20_000) {
                t.get("/api/defaults", 15_000)
            }
        } catch (e: Exception) { null }
        if (d == null || !d.ok) {
            t.close()
            return false
        }
        transport?.close()
        transport = t
        defaults.value = Values.of(JSONObject(d.text))
        when (t) {
            is WifiTransport -> prefs.edit().putString("host", t.host).apply()
            is BleTransport -> prefs.edit().putString("ble", t.device.address).apply()
        }
        link.value = Link.Up(t)
        touched = 0
        pollLoop()
        return true
    }

    private suspend fun pollLoop() {
        var fails = 0
        var n = 0
        while (viewModelScope.isActive) {
            val t = transport ?: return
            val slow = t.kind == Transport.Kind.BLUETOOTH
            try {
                refreshVideo(t)
                if (n % (if (slow) 4 else 2) == 0) status.value = JSONObject(t.get("/api/status").text)
                if (logsOpen.value && n % (if (slow) 3 else 1) == 0) logText.value = t.get("/api/${logKind.value}").text
                fails = 0
                if (link.value !is Link.Up) link.value = Link.Up(t)
            } catch (e: Exception) {
                if (++fails >= 3) {
                    // (gone: the other way may still reach it)
                    link.value = Link.Lost(e.message ?: "no answer")
                    transport?.close(); transport = null
                    autoConnect()
                    return
                }
            }
            n++
            delay(if (slow) 3_000 else 2_500)
        }
    }

    private suspend fun refreshVideo(t: Transport) {
        val v = JSONObject(t.get("/api/video").text)
        video.value = v
        // (the board's settings shown, unless this phone changed one a moment ago: then its echo)
        if (System.currentTimeMillis() - touched > 2_500) form.value = Values.of(v.optJSONObject("set"))
    }

    // ---- settings ----

    fun change(key: String, value: Int) = edit(Values.set(form.value, key, value))

    fun reset(specs: List<Spec>, note: String) {
        val d = defaults.value ?: return
        edit(Values.reset(form.value, d, specs))
        messages.tryEmit(note)
    }

    private fun edit(f: Form) {
        form.value = f
        touched = System.currentTimeMillis()
        sender?.cancel()
        sender = viewModelScope.launch {
            delay(150)          // (a slider let go, a burst of taps: one send)
            val t = transport ?: return@launch
            try {
                val r = t.post("/api/video", Values.encode(form.value))
                if (!r.ok) messages.tryEmit(r.text.ifBlank { "not taken" })
                refreshVideo(t)
            } catch (e: Exception) { messages.tryEmit("no answer from the board") }
        }
    }

    /** One of the board's commands (measure=1, tune=1, again=1, standby=0/1), as the page sends them. */
    fun command(body: String, note: String) = viewModelScope.launch {
        val t = transport ?: return@launch
        try {
            val r = t.post("/api/video", body)
            messages.tryEmit(if (r.ok) note else r.text)
            touched = 0
            refreshVideo(t)
        } catch (e: Exception) { messages.tryEmit("no answer from the board") }
    }

    // ---- the capture: the picture going out, read back (a BMP) ----

    fun grab(step: Int) = viewModelScope.launch {
        val t = transport ?: return@launch
        busy.value = "Capturing"
        try {
            val r = t.get("/api/grab?step=$step&t=${System.currentTimeMillis()}", 120_000) { done, _ ->
                busy.value = "Capturing · ${done / 1024} KB"
            }
            if (!r.ok) throw Exception(r.text)
            capture.value = withContext(Dispatchers.Default) { BitmapFactory.decodeByteArray(r.body, 0, r.body.size) }
                ?: throw Exception("not a picture")
        } catch (e: Exception) { messages.tryEmit("capture failed: ${e.message}") }
        busy.value = null
    }

    fun saveCapture() = viewModelScope.launch(Dispatchers.IO) {
        val b = capture.value ?: return@launch
        val ctx = getApplication<Application>()
        val v = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, "tang-av-${System.currentTimeMillis()}.png")
            put(MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/Tang AV Scaler")
        }
        val uri = ctx.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, v)
        val ok = uri != null && ctx.contentResolver.openOutputStream(uri)?.use { b.compress(Bitmap.CompressFormat.PNG, 100, it) } == true
        messages.tryEmit(if (ok) "saved in Pictures/Tang AV Scaler" else "could not save")
    }

    // ---- the board: Wi-Fi, firmware, tables, JTAG, logs ----

    fun joinWifi(ssid: String, pass: String) = viewModelScope.launch {
        val t = transport ?: return@launch
        try {
            messages.tryEmit(t.post("/api/wifi", "ssid=${enc(ssid)}&pass=${enc(pass)}").text.trim())
        } catch (e: Exception) { messages.tryEmit("no answer from the board") }
    }

    private fun read(uri: Uri) = getApplication<Application>().contentResolver.openInputStream(uri)?.use { it.readBytes() }

    fun uploadFirmware(uri: Uri) = viewModelScope.launch {
        val t = transport ?: return@launch
        val b = withContext(Dispatchers.IO) { read(uri) } ?: return@launch
        busy.value = "Uploading firmware"
        try {
            val r = t.request("POST", "/api/ota", b, "application/octet-stream", 600_000, upload = { d, n ->
                busy.value = "Uploading firmware · ${d * 100 / maxOf(n, 1)} %"
            })
            messages.tryEmit(r.text.trim())
        } catch (e: Exception) { messages.tryEmit("the upload failed: ${e.message}") }
        busy.value = null
    }

    fun uploadTable(uri: Uri, name: String) = viewModelScope.launch {
        val t = transport ?: return@launch
        val tab = video.value?.optJSONObject("tab") ?: return@launch
        val b = withContext(Dispatchers.IO) { read(uri) } ?: return@launch
        if (b.size != 131072) { messages.tryEmit("not a table: a .tab file is 131072 bytes"); return@launch }
        val names = tab.optJSONArray("names")
        val slot = (3..7).firstOrNull { (names?.optString(it) ?: "").isEmpty() }
            ?: run { messages.tryEmit("all five places are taken: remove one first"); return@launch }
        val n = name.removeSuffix(".tab").replace(Regex("[^A-Za-z0-9._-]"), "_").take(23)
        try {
            val r = t.request("POST", "/api/table?slot=$slot&name=$n", b, "application/octet-stream", 120_000)
            messages.tryEmit(r.text.trim())
            if (r.ok) change("table", slot - 1)
        } catch (e: Exception) { messages.tryEmit("the upload failed") }
    }

    fun dropTable() = viewModelScope.launch {
        val t = transport ?: return@launch
        val set = form.value["table"] ?: return@launch
        if (set < 2) return@launch
        try { messages.tryEmit(t.post("/api/table?slot=${set + 1}&drop=1", "").text.trim()) } catch (_: Exception) {}
        change("table", 0)
    }

    fun readFpga() = viewModelScope.launch {
        val t = transport ?: return@launch
        try {
            val f = JSONObject(t.get("/api/fpga").text)
            fpgaRead.value = if (f.optBoolean("busy")) "in use" else
                "ID ${f.optString("idcode")} · ${if (f.optBoolean("answers")) "answers" else "no answer"} · status ${f.optString("status")}"
        } catch (e: Exception) { messages.tryEmit("no answer from the board") }
    }

    fun openLogs(open: Boolean) {
        logsOpen.value = open
        if (open) refreshLogs()
    }

    fun showLog(kind: String) {
        logKind.value = kind
        logText.value = ""
        refreshLogs()
    }

    private fun refreshLogs() = viewModelScope.launch {
        val t = transport ?: return@launch
        try { logText.value = t.get("/api/${logKind.value}").text } catch (_: Exception) {}
    }

    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")

    override fun onCleared() {
        discovery.stop()
        transport?.close()
    }
}
