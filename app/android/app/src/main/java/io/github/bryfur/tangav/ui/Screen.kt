@file:OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)

package io.github.bryfur.tangav.ui

import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.PrimaryTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Slider
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import kotlinx.coroutines.launch
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.bryfur.tangav.model.BoardModel
import io.github.bryfur.tangav.model.Ctl
import io.github.bryfur.tangav.model.Form
import io.github.bryfur.tangav.model.Link
import io.github.bryfur.tangav.model.SPECS
import io.github.bryfur.tangav.model.Section
import io.github.bryfur.tangav.model.Spec
import io.github.bryfur.tangav.model.Values
import io.github.bryfur.tangav.net.Found
import io.github.bryfur.tangav.net.Transport
import org.json.JSONObject
import java.util.Locale

private const val X = "×"
private const val D = " · "

@Composable
fun App(vm: BoardModel) {
    val p = LocalPal.current
    val link by vm.link.collectAsState()
    val video by vm.video.collectAsState()
    val snack = remember { SnackbarHostState() }
    var choosing by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { vm.messages.collect { snack.showSnackbar(it) } }

    Box(Modifier.fillMaxSize().background(p.bg).windowInsetsPadding(WindowInsets.safeDrawing)) {
        Column(Modifier.fillMaxSize()) {
            Header(vm) { choosing = true }
            if (video == null) Waiting(link) { choosing = true } else Dashboard(vm)
        }
        SnackbarHost(snack, Modifier.align(Alignment.BottomCenter))
    }
    if (choosing) Chooser(vm) { choosing = false }
}

// ---- the header: the name, the board's state, the way to it, Advanced, power ----

@Composable
private fun Header(vm: BoardModel, onChoose: () -> Unit) {
    val p = LocalPal.current
    val link by vm.link.collectAsState()
    val v by vm.video.collectAsState()
    val st by vm.status.collectAsState()
    val adv by vm.advanced.collectAsState()
    val def by vm.defaults.collectAsState()
    Column(Modifier.fillMaxWidth().background(p.bg).padding(horizontal = 16.dp, vertical = 10.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Tang AV Scaler", color = p.text, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, maxLines = 1,
                modifier = Modifier.weight(1f))
            Power(vm, v)
        }
        // (the chips on one line, scrolled sideways where they do not fit)
        Row(
            Modifier.fillMaxWidth().padding(top = 8.dp).horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically,
        ) {
            Way(link, onChoose)
            for ((t, s, _) in barChips(v, link, adv, def)) Chip(t, s, big = true)
            val pk = st?.optJSONObject("ble")?.optString("passkey").orEmpty()
            if (pk.isNotEmpty()) Chip("Bluetooth pairing: $pk", St.BUSY, big = true)
        }
    }
    Box(Modifier.fillMaxWidth().height(1.dp).background(p.line))
}

/** Wi-Fi or Bluetooth, and where: tapped, the boards found. */
@Composable
private fun Way(link: Link, onChoose: () -> Unit) {
    val (t, s) = when (link) {
        is Link.Up -> (if (link.t.kind == Transport.Kind.WIFI) "Wi-Fi ${link.t.label}" else "Bluetooth") to St.OK
        is Link.Connecting -> "connecting ${link.what}" to St.BUSY
        is Link.Lost -> "lost: looking again" to St.BAD
        Link.Searching -> "looking for the board" to St.BUSY
    }
    Chip(t, s, big = true, modifier = Modifier.clickable(onClick = onChoose))
}

@Composable
private fun Power(vm: BoardModel, v: JSONObject?) {
    if (v == null) return
    val standby = v.optBoolean("standby")
    val fpga = v.optBoolean("fpga")
    val wake = standby || !fpga
    val label = if (standby) "Wake" else if (fpga) "Stand by" else "Load again"
    val click: () -> Unit = { vm.command("standby=${if (wake) 0 else 1}", if (wake) "waking" else "standing by") }
    val content: @Composable () -> Unit = { PowerIcon(); Spacer(Modifier.width(8.dp)); Text(label) }
    if (standby) Button(click) { content() } else OutlinedButton(click) { content() }
}

private fun barChips(v: JSONObject?, link: Link, adv: Boolean, def: Form?): List<Triple<String, St, Boolean>> {
    if (v == null) return emptyList()
    val set = v.optJSONObject("set") ?: JSONObject()
    val out = mutableListOf<Triple<String, St, Boolean>>()
    val sig = v.optInt("fields_s") in 49..61
    val name = v.optString("in").takeIf { it.isNotEmpty() && it != "none" }
    val main = when {
        v.optBoolean("host") -> "Host tool" to St.BUSY
        set.optInt("on") == 0 -> "Scaler off" to St.BUSY
        v.optBoolean("standby") -> "Standby" to St.IDLE
        !v.optBoolean("fpga") -> "FPGA not answering" to St.BAD
        !v.optBoolean("ok") -> "Not up" to St.BAD
        !sig -> "No input" to St.BAD
        else -> "${name ?: "${v.optInt("pix")}$X${v.optInt("lines") * 2}i"} → 1080p${if (set.optInt("ntsc") == 1) "59.94" else "60"}" +
            "$D${v.optDouble("delay_ms").toInt()} ms" to St.OK
    }
    out += Triple(main.first, main.second, false)
    if (sig && !v.optBoolean("pll")) out += Triple("PLL unlocked", St.BAD, false)
    if (v.optBoolean("fpga") && !v.optBoolean("standby") && !v.optBoolean("hpd")) out += Triple("no display", St.IDLE, false)
    if (v.optDouble("temp_c") >= 85) out += Triple("${v.optDouble("temp_c").toInt()} °C", St.BUSY, false)
    if (!adv) {
        val br = Values.BREAK.filter { (k, _) -> set.optInt(k) != (def?.get(k) ?: 0) }.values
        if (br.isNotEmpty()) out += Triple(br.joinToString(", "), St.BUSY, true)
    }
    return out
}

@Composable
private fun Waiting(link: Link, onChoose: () -> Unit) {
    val p = LocalPal.current
    Column(Modifier.fillMaxSize().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        CircularProgressIndicator(color = p.acc)
        Spacer(Modifier.height(20.dp))
        Text(when (link) {
            is Link.Connecting -> "Connecting to ${link.what}"
            is Link.Lost -> "The board stopped answering: looking for it again"
            else -> "Looking for the board on Wi-Fi and Bluetooth"
        }, color = p.text, fontSize = 16.sp)
        Spacer(Modifier.height(20.dp))
        OutlinedButton(onChoose) { Text("Choose a board") }
    }
}

// ---- the dashboard: one column on a phone, two on a middle screen, three on a wide one ----

private enum class Page(val title: String) { SETTINGS("Settings"), STATUS("Status"), BOARD("Board") }

/** Three pages, swiped between or chosen by their tab: the picture's settings; what the board is doing
 * (and a capture of it); the board itself. */
@Composable
private fun Dashboard(vm: BoardModel) {
    val p = LocalPal.current
    val pager = rememberPagerState(pageCount = { Page.entries.size })
    val scope = rememberCoroutineScope()
    // (the logs fetched only while their page is the one shown)
    LaunchedEffect(pager.settledPage) { vm.logsOnScreen(pager.settledPage == Page.BOARD.ordinal) }
    Column(Modifier.fillMaxSize()) {
        PrimaryTabRow(pager.currentPage, containerColor = p.bg, contentColor = p.text, divider = { Hairline() }) {
            for (t in Page.entries) Tab(pager.currentPage == t.ordinal, { scope.launch { pager.animateScrollToPage(t.ordinal) } }, text = {
                Text(t.title, fontSize = 15.sp, color = if (pager.currentPage == t.ordinal) p.text else p.dim)
            })
        }
        HorizontalPager(pager, Modifier.fillMaxSize(), beyondViewportPageCount = 1, verticalAlignment = Alignment.Top) { page ->
            BoxWithConstraints(Modifier.fillMaxSize()) {
                val wide = maxWidth >= 640.dp
                // (a page's cards: side by side where the screen is wide, one under another on a phone)
                val two: @Composable (@Composable () -> Unit, @Composable () -> Unit) -> Unit = { a, b ->
                    if (wide) Row(horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                        Column(Modifier.weight(1f)) { a() }
                        Column(Modifier.weight(1f)) { b() }
                    } else { a(); b() }
                }
                Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp).padding(bottom = 48.dp)) {
                    when (Page.entries[page]) {
                        Page.SETTINGS -> two({ Settings(vm, Section.PICTURE); Settings(vm, Section.DEINT) },
                            { Settings(vm, Section.AA); Settings(vm, Section.OUTPUT) })
                        Page.STATUS -> two({ Status(vm) }, { CaptureCard(vm) })
                        Page.BOARD -> two({ WifiCard(vm); Maintenance(vm) }, { Logs(vm) })
                    }
                }
            }
        }
    }
}

// ---- the settings ----

@Composable
private fun Settings(vm: BoardModel, section: Section) {
    val f by vm.form.collectAsState()
    val v by vm.video.collectAsState()
    val adv by vm.advanced.collectAsState()
    val def by vm.defaults.collectAsState()
    val rows = SPECS.filter { it.section == section && Values.shown(it, f, v, adv) }
    val d = def
    Heading(section.title, onReset = { vm.reset(rows, "${section.title}: back to defaults") },
        canReset = d != null && rows.any { Values.changed(f, d, it) })
    Card {
        rows.forEachIndexed { i, s ->
            if (i > 0) Hairline()
            SettingRow(
                s.label, s.hint, Values.changed(f, d, s), onReset = { vm.reset(listOf(s), "back to the default") },
                sub = s.sub, below = (s.ctl as? Ctl.Seg)?.options?.sumOf { it.second.length }?.let { it > 18 } == true,
                chip = live(s.key, v, f)?.let { (t, st) -> { Chip(t, st) } },
            ) { Control(vm, s, f, v) }
        }
        if (section == Section.PICTURE && adv && v?.optJSONObject("tab")?.optInt("state", -1)?.let { it >= 0 } == true) {
            Hairline(); OwnTable(vm, f)
        }
    }
}

@Composable
private fun Control(vm: BoardModel, s: Spec, f: Form, v: JSONObject?) {
    val value = Values.get(f, s.key)
    when (val c = s.ctl) {
        Ctl.Switch -> Switch(value == 1, { vm.change(s.key, if (it) 1 else 0) })
        is Ctl.Seg -> SingleChoiceSegmentedButtonRow {
            c.options.forEachIndexed { i, (n, label) ->
                SegmentedButton(
                    selected = value == n, onClick = { vm.change(s.key, n) },
                    shape = SegmentedButtonDefaults.itemShape(i, c.options.size), icon = {}, colors = segColors(),
                ) { Text(label, maxLines = 1, softWrap = false, fontSize = 13.sp) }
            }
        }
        is Ctl.Range -> Row(verticalAlignment = Alignment.CenterVertically) {
            RangeSlider(value, c) { vm.change(s.key, it) }
            if (s.key == "phase") TextButton({ vm.command("tune=1", "tuning") }) { Text("Tune") }
        }
        Ctl.Table -> TablePick(vm, value, v)
        Ctl.Area -> Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            for ((k, label) in listOf("crop_x" to "left", "crop_y" to "top", "crop_w" to "width", "crop_h" to "height")) {
                NumberBox(f[k] ?: 0, label) { vm.change(k, it) }
            }
        }
    }
}

@Composable
private fun RangeSlider(value: Int, c: Ctl.Range, onDone: (Int) -> Unit) {
    val p = LocalPal.current
    var pos by remember(value) { mutableFloatStateOf(value.toFloat()) }
    Row(Modifier.widthIn(min = 200.dp, max = 260.dp), verticalAlignment = Alignment.CenterVertically) {
        Slider(
            pos, { pos = it }, Modifier.weight(1f), valueRange = c.min.toFloat()..c.max.toFloat(),
            onValueChangeFinished = { onDone(Math.round(pos)) },
        )
        Text("${Math.round(pos)}", color = p.dim, fontSize = 14.sp, modifier = Modifier.width(30.dp).padding(start = 8.dp))
    }
}

@Composable
private fun NumberBox(value: Int, label: String, onChange: (Int) -> Unit) {
    var text by remember(value) { mutableStateOf(value.toString()) }
    OutlinedTextField(
        text, { text = it.filter(Char::isDigit).take(3); text.toIntOrNull()?.let(onChange) },
        Modifier.width(72.dp), label = { Text(label, fontSize = 11.sp) }, singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
    )
}

@Composable
private fun TablePick(vm: BoardModel, value: Int, v: JSONObject?) {
    val names = v?.optJSONObject("tab")?.optJSONArray("names")
    val opts = buildList {
        add(0 to "FSR")
        if (names != null && names.optString(1).isNotEmpty() && names.optString(2).isNotEmpty()) add(1 to "Learnt")
        for (k in 3..7) names?.optString(k)?.takeIf { it.isNotEmpty() }?.let { add(k - 1 to it) }
    }
    var open by remember { mutableStateOf(false) }
    Box {
        OutlinedButton({ open = true }) { Text((opts.firstOrNull { it.first == value }?.second ?: "FSR") + "  ▾") }
        DropdownMenu(open, { open = false }) {
            for ((n, label) in opts) DropdownMenuItem({ Text(label) }, { open = false; vm.change("table", n) })
        }
    }
}

@Composable
private fun OwnTable(vm: BoardModel, f: Form) {
    val ctx = LocalContext.current
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        if (uri != null) vm.uploadTable(uri, fileName(ctx, uri) ?: "table")
    }
    SettingRow("Own table", "A .tab file: tables kept in the board, five places.", sub = true) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton({ pick.launch("*/*") }) { Text("Add .tab") }
            if ((f["table"] ?: 0) >= 2) OutlinedButton({ vm.dropTable() }) { Text("Remove") }
        }
    }
}

/** A row's live state: the board's own words, made short (as the page's chips). */
private fun live(key: String, v: JSONObject?, f: Form): Pair<String, St>? {
    if (v == null) return null
    val set = v.optJSONObject("set") ?: return null
    fun sgn(x: Double) = (if (x > 0) "+" else if (x < 0) "−" else "") + String.format(Locale.US, "%s", Math.abs(x).let { if (it % 1.0 == 0.0) it.toInt().toString() else it.toString() })
    return when (key) {
        "crop" -> if (set.optInt("crop") == 1) v.optJSONArray("shown")?.let { "${it.optInt(1)} $X ${it.optInt(3)} at ${it.optInt(0)}, ${it.optInt(2)}" to St.OK } else null
        "net" -> {
            val n = v.optJSONObject("net") ?: return null
            if (!(n.optBoolean("there") && set.optInt("net") == 1)) null
            else when (n.optInt("state")) { 2 -> n.optString("name").ifEmpty { "own weights" } to St.OK; 1 -> "own weights, not saved" to St.OK; else -> "built-in weights" to St.IDLE }
        }
        "table" -> {
            val t = v.optJSONObject("tab") ?: return null
            when {
                t.optInt("bad") > 0 -> "${t.optInt("bad")} bad entries" to St.BAD
                t.optInt("state") == 1 -> "changing" to St.BUSY
                t.optInt("state") == 3 -> "starting" to St.BUSY
                else -> null
            }
        }
        "phase" -> when (v.optInt("tune")) {
            1 -> "tuning" to St.BUSY; 2 -> "tuned +${v.optInt("tune_gain") - 100} %" to St.OK
            3 -> "picture moved" to St.BAD; 4 -> "no picture" to St.BAD; else -> null
        }
        "lock" -> if (!v.optBoolean("relay") || set.optInt("lock") == 0) null else when (v.optInt("lock")) {
            1 -> "no input" to St.BAD
            2 -> "locking$D${String.format(Locale.US, "%.1f", v.optDouble("lock_us") / 1000)} ms" to St.BUSY
            3 -> "locked$D${sgn(v.optDouble("lock_ppm"))} ppm" to St.OK
            else -> null
        }
        "lowlat" -> if (set.optInt("lowlat") == 0) null else when {
            v.optBoolean("ll") -> "${v.optInt("ll_lines")} lines" to St.OK
            set.optInt("lock") == 1 -> "waiting for lock" to St.BUSY
            else -> "needs frame lock" to St.IDLE
        }
        "_c" -> {
            val pan = v.optJSONArray("pan")
            if ((set.optInt("mode") and 11) == 8 && pan != null && pan.optInt(0) != 0)
                "pan ${sgn(pan.optDouble(1))}, ${sgn(pan.optDouble(2))}" to St.OK else null
        }
        else -> null
    }
}

// ---- the capture ----

@Composable
private fun CaptureCard(vm: BoardModel) {
    val img by vm.capture.collectAsState()
    val busy by vm.busy.collectAsState()
    var step by remember { mutableIntStateOf(4) }
    Heading("Capture")
    Card {
        Box(Modifier.fillMaxWidth().aspectRatio(16 / 9f).background(Color.Black), contentAlignment = Alignment.Center) {
            val b = img
            if (b != null) Image(b.asImageBitmap(), "capture", Modifier.fillMaxSize(), contentScale = ContentScale.Fit)
            else Text(busy ?: "No capture yet", color = Color(0xFF5D6472), fontSize = 13.sp)
        }
        FlowRow(
            Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp), itemVerticalAlignment = Alignment.CenterVertically,
        ) {
            val opts = listOf(4 to "Small", 2 to "Half", 1 to "Full")
            SingleChoiceSegmentedButtonRow {
                opts.forEachIndexed { i, (n, label) ->
                    SegmentedButton(step == n, { step = n }, SegmentedButtonDefaults.itemShape(i, opts.size), icon = {}, colors = segColors()) {
                        Text(label, fontSize = 13.sp, maxLines = 1, softWrap = false)
                    }
                }
            }
            Spacer(Modifier.weight(1f))
            if (img != null) OutlinedButton({ vm.saveCapture() }) { Text("Save") }
            // (the progress in the frame while there is no picture yet; on the button over an old one)
            Button({ vm.grab(step) }, enabled = busy == null) { Text(if (busy != null && img != null) busy!! else "Capture") }
        }
    }
}

// ---- the board: status, Wi-Fi, maintenance, logs ----

@Composable
private fun Status(vm: BoardModel) {
    val v by vm.video.collectAsState()
    val s by vm.status.collectAsState()
    val adv by vm.advanced.collectAsState()
    Heading("Status")
    Card {
        val rows = statusRows(v, s, adv)
        rows.forEachIndexed { i, (k, value, bad) -> if (i > 0) Hairline(); KeyValue(k, value, bad) }
    }
}

private fun day(s: Long) = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US).apply { timeZone = java.util.TimeZone.getTimeZone("UTC") }.format(java.util.Date(s * 1000))
private fun dur(s: Long) = if (s < 3600) "${s / 60} min" else "${s / 3600} h ${s % 3600 / 60} min"

private fun statusRows(v: JSONObject?, s: JSONObject?, adv: Boolean): List<Triple<String, String, Boolean>> {
    val r = mutableListOf<Triple<String, String, Boolean>>()
    if (v != null) {
        val set = v.optJSONObject("set") ?: JSONObject()
        val sig = v.optInt("fields_s") in 49..61
        val named = v.optString("in").let { it.isNotEmpty() && it != "none" }
        r += Triple("Input", if (sig) (if (named) v.optString("in") + D else "") + String.format(Locale.US, "%.2f Hz", v.optDouble("in_hz")) else "none", !sig)
        r += Triple("Field", "${v.optInt("pix")} $X ${v.optInt("lines")}$D${v.optInt("fields_s")}/s$D${String.format(Locale.US, "%.3f", v.optInt("llc_khz") / 1000.0)} MHz", false)
        v.optJSONArray("shown")?.let { r += Triple("Shown", "${it.optInt(1)} $X ${it.optInt(3)} at ${it.optInt(0)}, ${it.optInt(2)}$D${if (set.optInt("wide") == 1) "16:9" else "4:3"}", false) }
        r += Triple("Output", "1080p${if (set.optInt("ntsc") == 1) "59.94" else "60"}$D${v.optInt("frames_s")} fps$D${if (v.optBoolean("pll")) "PLL locked" else "PLL unlocked"}", !v.optBoolean("pll"))
        r += Triple("Display", if (v.optBoolean("hpd")) "connected" else "not seen", !v.optBoolean("hpd"))
        r += Triple("Delay", if (sig) String.format(Locale.US, "%.1f ms$D%.2f frames", v.optDouble("delay_ms"), v.optDouble("delay_ms") / 16.68) else "–", false)
        r += Triple("FPGA", if (v.optBoolean("fpga")) (if (v.optDouble("temp_c") > -100) String.format(Locale.US, "%.1f °C$D", v.optDouble("temp_c")) else "") +
            (if (v.optBoolean("ok")) "up" else "not up") + "${D}CPU ${if (v.optBoolean("cpu")) "runs" else "stopped"}" else "not answering", !v.optBoolean("fpga") || !v.optBoolean("ok"))
        if (adv) r += Triple("Builds", "FPGA ${day(v.optLong("build"))}" + if (v.optBoolean("relay")) "${D}CPU ${day(v.optLong("cpu_build"))}" else "", false)
        v.optJSONObject("store")?.let { st ->
            r += Triple("Saved", when {
                !st.optBoolean("there") -> "in the link"; st.optBoolean("failed") -> "write failed"
                st.optBoolean("busy") -> "writing"; st.optBoolean("set") -> "in flash"; else -> "nothing yet"
            }, st.optBoolean("failed"))
        }
    }
    if (s != null) {
        val w = s.optJSONObject("wifi") ?: JSONObject()
        val f = s.optJSONObject("firmware") ?: JSONObject()
        r += Triple("Wi-Fi", if (w.optBoolean("joined")) "${w.optString("ssid")}$D${w.optInt("rssi")} dBm${D}ch ${w.optInt("channel")}" else "not joined", !w.optBoolean("joined"))
        r += Triple("Address", "${w.optString("ip")}$D${w.optString("host")}.local", false)
        s.optJSONObject("ble")?.let { b ->
            r += Triple("Bluetooth", if (!b.optBoolean("on")) b.optString("err").ifEmpty { "off" } else when (b.optInt("connected")) {
                0 -> "waiting for a phone"; 1 -> "a phone"; else -> "${b.optInt("connected")} phones"
            } + (if (b.optBoolean("encrypted")) "${D}paired" else ""), !b.optBoolean("on"))
        }
        r += Triple("Firmware", "${f.optString("version")}${D}up ${dur(f.optLong("uptime_s"))}", false)
        if (adv) {
            r += Triple("Memory", "${f.optInt("heap_int") / 1024} KB own${D}low ${f.optInt("heap_int_min") / 1024} KB", false)
            s.optJSONObject("jtag")?.let { j -> r += Triple("JTAG", ":${j.optInt("port")}$D${if (j.optBoolean("connected")) "in use by " + j.optString("peer") else "free"}", false) }
            s.optJSONObject("console")?.let { c -> r += Triple("Console", ":${c.optInt("port")}$D${if (c.optBoolean("tcp")) "client " + c.optString("peer") else "no client"}", false) }
        }
    }
    return r
}

@Composable
private fun WifiCard(vm: BoardModel) {
    var ssid by remember { mutableStateOf("") }
    var pass by remember { mutableStateOf("") }
    Heading("Wi-Fi")
    Card {
        FlowRow(
            Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp), itemVerticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(ssid, { ssid = it }, Modifier.widthIn(min = 140.dp).weight(1f), label = { Text("Network") }, singleLine = true)
            OutlinedTextField(pass, { pass = it }, Modifier.widthIn(min = 140.dp).weight(1f), label = { Text("Password") }, singleLine = true,
                visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
            Button({ vm.joinWifi(ssid, pass) }, enabled = ssid.isNotBlank()) { Text("Join") }
        }
    }
}

@Composable
private fun Maintenance(vm: BoardModel) {
    val adv by vm.advanced.collectAsState()
    val fp by vm.fpgaRead.collectAsState()
    val busy by vm.busy.collectAsState()
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? -> if (uri != null) vm.uploadFirmware(uri) }
    Heading("Maintenance")
    Card {
        SettingRow("Scaler") { OutlinedButton({ vm.command("again=1", "bringing it up") }) { Text("Bring up again") } }
        Hairline()
        SettingRow("Firmware", "avwifi.bin, from the firmware's build", chip = busy?.takeIf { it.startsWith("Uploading") }?.let { { Chip(it, St.BUSY) } }) {
            OutlinedButton({ pick.launch("*/*") }, enabled = busy == null) { Text("Upload…") }
        }
        if (adv) {
            Hairline()
            SettingRow("JTAG", chip = fp?.let { { Chip(it, St.OK) } }) { OutlinedButton({ vm.readFpga() }) { Text("Read FPGA") } }
        }
    }
}

@Composable
private fun Logs(vm: BoardModel) {
    val open by vm.logsOpen.collectAsState()
    val kind by vm.logKind.collectAsState()
    val text by vm.logText.collectAsState()
    Heading("Logs")
    Card {
        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            val opts = listOf("console" to "FPGA", "log" to "Firmware")
            // (its own width, the names on one line: Hide at the far end)
            SingleChoiceSegmentedButtonRow(Modifier.width(IntrinsicSize.Max)) {
                opts.forEachIndexed { i, (k, label) ->
                    SegmentedButton(kind == k, { vm.showLog(k); vm.openLogs(true) }, SegmentedButtonDefaults.itemShape(i, opts.size), icon = {}, colors = segColors()) {
                        Text(label, fontSize = 13.sp, maxLines = 1, softWrap = false)
                    }
                }
            }
            Spacer(Modifier.weight(1f))
            TextButton({ vm.openLogs(!open) }) { Text(if (open) "Hide" else "Show") }
        }
        if (open) {
            val scroll = rememberScrollState()
            LaunchedEffect(text) { scroll.scrollTo(scroll.maxValue) }
            Box(Modifier.fillMaxWidth().heightIn(min = 240.dp, max = 420.dp).background(Color(0xFF0A0B0E)).verticalScroll(scroll)) {
                Text(text, color = Color(0xFFCFD3DC), fontFamily = FontFamily.Monospace, fontSize = 11.sp, lineHeight = 15.sp,
                    modifier = Modifier.horizontalScroll(rememberScrollState()).padding(12.dp))
            }
        }
    }
}

// ---- the boards found: choose one, and the way to it ----

@Composable
private fun Chooser(vm: BoardModel, onDone: () -> Unit) {
    val p = LocalPal.current
    val wifi by vm.discovery.wifi.collectAsState()
    val ble by vm.discovery.ble.collectAsState()
    var addr by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDone,
        confirmButton = { TextButton(onDone) { Text("Close") } },
        title = { Text("Boards") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text("ON THIS NETWORK", color = p.dim, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                if (wifi.isEmpty()) Text("none found yet", color = p.dim, fontSize = 14.sp, modifier = Modifier.padding(vertical = 8.dp))
                for (f in wifi.values) Pick(f.name, f.host ?: "") { vm.choose(f, false); onDone() }
                Spacer(Modifier.height(14.dp))
                Text("BLUETOOTH", color = p.dim, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                if (!vm.discovery.bluetoothThere) Text("no Bluetooth on this phone", color = p.dim, fontSize = 14.sp)
                else if (ble.isEmpty()) Text(if (vm.discovery.bluetoothOn) "none in range yet" else "Bluetooth is off", color = p.dim, fontSize = 14.sp, modifier = Modifier.padding(vertical = 8.dp))
                for (f in ble.values) Pick(f.name, listOfNotNull(if (f.bonded) "paired" else "not paired yet", f.rssi?.let { "$it dBm" }).joinToString(D)) {
                    vm.choose(f, true); onDone()
                }
                Spacer(Modifier.height(14.dp))
                Text("BY ADDRESS", color = p.dim, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(addr, { addr = it.trim() }, Modifier.weight(1f), placeholder = { Text("192.168.1.112") }, singleLine = true)
                    TextButton({ vm.choose(Found(addr, host = addr), false); onDone() }, enabled = addr.isNotEmpty()) { Text("Connect") }
                }
            }
        },
    )
}

@Composable
private fun Pick(name: String, detail: String, onClick: () -> Unit) {
    val p = LocalPal.current
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable(onClick = onClick).padding(vertical = 10.dp, horizontal = 4.dp)) {
        Text(name, color = p.text, fontSize = 15.sp)
        Text(detail, color = p.dim, fontSize = 12.sp)
    }
}

private fun fileName(ctx: android.content.Context, uri: Uri): String? =
    ctx.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
        if (c.moveToFirst()) c.getString(0) else null
    }

@Composable
fun segColors() = LocalPal.current.let { p ->
    SegmentedButtonDefaults.colors(
        activeContainerColor = p.acc.copy(alpha = .22f), activeContentColor = p.text, activeBorderColor = p.line,
        inactiveContainerColor = p.input, inactiveContentColor = p.dim, inactiveBorderColor = p.line,
    )
}

/** The power symbol, drawn (a circle open at the top, a stroke down into it). */
@Composable
private fun PowerIcon() {
    val c = androidx.compose.material3.LocalContentColor.current
    androidx.compose.foundation.Canvas(Modifier.width(16.dp).height(16.dp)) {
        val w = 1.8.dp.toPx()
        drawArc(c, -60f, 300f, false, topLeft = androidx.compose.ui.geometry.Offset(w, w + 1.dp.toPx()),
            size = androidx.compose.ui.geometry.Size(size.width - 2 * w, size.height - 2 * w),
            style = androidx.compose.ui.graphics.drawscope.Stroke(w, cap = androidx.compose.ui.graphics.StrokeCap.Round))
        drawLine(c, androidx.compose.ui.geometry.Offset(size.width / 2, 0f), androidx.compose.ui.geometry.Offset(size.width / 2, size.height / 2),
            w, androidx.compose.ui.graphics.StrokeCap.Round)
    }
}
