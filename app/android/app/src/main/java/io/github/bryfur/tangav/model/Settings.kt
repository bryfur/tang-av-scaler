package io.github.bryfur.tangav.model

import org.json.JSONObject

/**
 * The board's settings as the web page shows them (firmware/xiao-wifi/main/page.html): the same
 * names, the same rows, the same defaults (GET /api/defaults), sent the same way (POST /api/video,
 * every setting in one form).
 */
enum class Section(val title: String) { PICTURE("Picture"), DEINT("Deinterlacing"), AA("Anti-aliasing"), OUTPUT("Output") }

sealed interface Ctl {
    data object Switch : Ctl
    data class Seg(val options: List<Pair<Int, String>>) : Ctl
    data class Range(val min: Int, val max: Int) : Ctl
    data object Table : Ctl         // the scaling kernel (the board's list of tables)
    data object Area : Ctl          // the manual crop: four numbers
}

data class Spec(
    val key: String, val label: String, val section: Section, val ctl: Ctl,
    val hint: String? = null, val adv: Boolean = false, val sub: Boolean = false,
)

private fun seg(vararg o: Pair<Int, String>) = Ctl.Seg(o.toList())

val SPECS = listOf(
    Spec("crop", "Crop", Section.PICTURE, seg(1 to "Auto", 0 to "Off", 2 to "Manual"),
        "Auto finds the game's picture and leaves out the black around it."),
    Spec("area", "Area", Section.PICTURE, Ctl.Area, "Left, top, width, height in the 720 × 480 signal.", sub = true),
    Spec("wide", "Widescreen", Section.PICTURE, Ctl.Switch, "For a game set to 16:9."),
    Spec("nr", "Noise reduction", Section.PICTURE, seg(0 to "Off", 1 to "Low", 2 to "Medium", 3 to "High"),
        "Averages frames where the picture is still."),
    Spec("net", "Upscaler", Section.PICTURE, seg(0 to "Kernel", 1 to "Network"),
        "Kernel: edge-adaptive, from a table. Network: a small neural network doubles the picture, then a plain stretch."),
    Spec("table", "Kernel", Section.PICTURE, Ctl.Table, "FSR 1, or learnt from games' pictures."),
    Spec("sharp", "Sharpening", Section.PICTURE, Ctl.Range(0, 16)),
    Spec("dn", "Noise-aware sharpening", Section.PICTURE, Ctl.Switch, "Sharpens noise less."),
    Spec("phase", "Sampling phase", Section.PICTURE, Ctl.Range(0, 31),
        "Where in a pixel the decoder samples. Tune on a still picture (pause the game).", adv = true),
    Spec("freeze", "Freeze", Section.PICTURE, Ctl.Switch, adv = true),

    Spec("_m", "Method", Section.DEINT, seg(0 to "Motion adaptive", 1 to "Bob", 2 to "Weave"),
        "Motion adaptive: weave where still, fill in where moving. Bob: fill in every line. Weave: still pictures only."),
    Spec("_c", "Motion compensation", Section.DEINT, Ctl.Switch,
        "Filled-in lines come from the field before, moved block by block.", sub = true),
    Spec("_k", "30 fps games", Section.DEINT, Ctl.Switch,
        "For games that draw each frame twice: both fields are woven, full detail in motion.", sub = true),
    Spec("mv_dbg", "Show motion", Section.DEINT, Ctl.Switch, "Blue left, yellow right, red up, green down.", adv = true, sub = true),
    Spec("thr", "Motion threshold", Section.DEINT, Ctl.Range(0, 32), adv = true),
    Spec("top1", "Top field is F=1", Section.DEINT, Ctl.Switch, adv = true),

    Spec("aa", "SMAA", Section.AA, Ctl.Switch, "Smooths jagged edges."),
    Spec("aa_thr", "Edge threshold", Section.AA, Ctl.Range(4, 48), "Lower finds more edges.", adv = true),
    Spec("aa_keep", "Steady edges", Section.AA, Ctl.Range(0, 7),
        "Keeps last frame's edges so still edges do not shimmer. 0 is off.", adv = true),
    Spec("aa_diag", "Diagonal edges", Section.AA, Ctl.Switch, adv = true),
    Spec("aa_corner", "Sharp corners", Section.AA, Ctl.Switch, adv = true),
    Spec("aa_dbg", "Show edges", Section.AA, Ctl.Switch, "Edges green, blends blue and red.", adv = true),

    Spec("lock", "Frame lock", Section.OUTPUT, Ctl.Switch, "Output in step with the input: each field shown once, steady delay."),
    Spec("lowlat", "Low latency", Section.OUTPUT, Ctl.Switch, "Starts a frame while its field is still coming in. Needs frame lock."),
    Spec("osd", "On-screen display", Section.OUTPUT, Ctl.Switch),
    Spec("audio", "HDMI audio", Section.OUTPUT, Ctl.Switch, "Off: DVI, no sound."),
    Spec("surround", "Surround 5.1", Section.OUTPUT, Ctl.Switch, "Pro Logic II decoded to 5.1 (1080p only)."),
    Spec("ntsc", "Frame rate", Section.OUTPUT, seg(1 to "59.94 Hz", 0 to "60 Hz")),
    Spec("pattern", "Test picture", Section.OUTPUT, Ctl.Switch, adv = true),
    Spec("swap", "Swap Cb / Cr", Section.OUTPUT, Ctl.Switch, adv = true),
    Spec("on", "Run the scaler", Section.OUTPUT, Ctl.Switch, "Off leaves the FPGA to a host tool.", adv = true),
)

typealias Form = Map<String, Int>

/** The deinterlacer's three controls are bits of one setting, mode: 0 motion adaptive, 1 bob, 2 weave;
 * 4 more for 30 fps games, 8 more for motion compensation (both with motion adaptive only). */
private val MBITS = mapOf("_m" to 3, "_k" to 4, "_c" to 8)
private val AREA = listOf("crop_x", "crop_y", "crop_w", "crop_h")

object Values {
    fun get(f: Form, key: String): Int = when (key) {
        "_m" -> (f["mode"] ?: 0) and 3
        "_k", "_c" -> if ((f["mode"] ?: 0) and MBITS.getValue(key) != 0) 1 else 0
        else -> f[key] ?: 0
    }

    fun set(f: Form, key: String, v: Int): Form {
        var mode = f["mode"] ?: 0
        when (key) {
            "_m" -> mode = if (v != 0) v else (mode and 12)      // (bob and weave: no compensation, no 30 fps)
            "_k", "_c" -> if ((mode and 3) == 0) mode = if (v != 0) mode or MBITS.getValue(key) else mode and MBITS.getValue(key).inv()
            else -> return f + (key to v)
        }
        return f + ("mode" to mode)
    }

    /** The settings a row sets: (name, the bits of it; 0 all of it). */
    fun keys(s: Spec): List<Pair<String, Int>> = when {
        s.key in MBITS -> listOf("mode" to MBITS.getValue(s.key))
        s.ctl == Ctl.Area -> AREA.map { it to 0 }
        s.key == "phase" -> emptyList()      // (the board's own calibration: Tune is its reset)
        else -> listOf(s.key to 0)
    }

    fun differs(f: Form, def: Form, k: Pair<String, Int>): Boolean {
        val (name, mask) = k
        if (name !in def) return false
        if (name.startsWith("crop_") && f["crop"] != 2) return false
        val a = f[name] ?: 0
        val b = def.getValue(name)
        return if (mask != 0) (a and mask) != (b and mask) else a != b
    }

    fun changed(f: Form, def: Form?, s: Spec) = def != null && keys(s).any { differs(f, def, it) }

    fun reset(f: Form, def: Form, specs: List<Spec>): Form {
        val o = f.toMutableMap()
        for (s in specs) for ((k, m) in keys(s)) if (k in def) {
            o[k] = if (m != 0) ((o[k] ?: 0) and m.inv()) or (def.getValue(k) and m) else def.getValue(k)
        }
        return o
    }

    /** The form POST /api/video takes (every setting, as the page sends them). */
    fun encode(f: Form) = f.entries.joinToString("&") { "${it.key}=${it.value}" }

    fun of(j: JSONObject?): Form = j?.keys()?.asSequence()?.associateWith { j.optInt(it) } ?: emptyMap()

    /** Shown at all, given the board's state, the form and Advanced (rows that do not apply are hidden). */
    fun shown(s: Spec, f: Form, v: JSONObject?, advanced: Boolean): Boolean {
        if (s.adv && !advanced) return false
        val m = get(f, "_m")
        val tab = v?.optJSONObject("tab")
        val netThere = v?.optJSONObject("net")?.optBoolean("there") == true
        return when (s.key) {
            "area" -> f["crop"] == 2
            "net" -> netThere
            "table" -> tab != null && tab.optInt("state", -1) >= 0 && !(netThere && f["net"] == 1)
            "_c", "_k" -> m == 0
            "mv_dbg" -> m == 0 && get(f, "_c") == 1
            else -> true
        }
    }

    /** A bring-up setting that changes the picture, left on while Advanced is hidden (named in the header). */
    val BREAK = linkedMapOf("freeze" to "freeze", "pattern" to "test picture", "aa_dbg" to "edge view",
        "mv_dbg" to "motion view", "swap" to "Cb/Cr swapped", "top1" to "top field F=1")
}
