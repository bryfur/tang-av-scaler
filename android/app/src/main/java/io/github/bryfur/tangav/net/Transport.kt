package io.github.bryfur.tangav.net

import java.io.Closeable
import java.io.IOException

/** An answer from the board's web server (the same over Wi-Fi and over Bluetooth). */
class Response(val code: Int, val body: ByteArray) {
    val ok get() = code in 200..299
    val text get() = body.decodeToString()
}

/** A request's bytes moving: done, of total (total -1 when not known). */
typealias Progress = (done: Long, total: Long) -> Unit

/**
 * The way to the board: its HTTP API over Wi-Fi, or the same bytes over a Bluetooth L2CAP channel
 * (the firmware passes each channel to its own web server: firmware/xiao-wifi/main/ble.c).
 */
interface Transport : Closeable {
    enum class Kind { WIFI, BLUETOOTH }
    val kind: Kind
    /** What it is to a person: an address, or the board's Bluetooth name. */
    val label: String

    suspend fun request(
        method: String, path: String, body: ByteArray? = null, type: String? = null,
        timeoutMs: Long = 15_000, upload: Progress? = null, download: Progress? = null,
    ): Response

    suspend fun get(path: String, timeoutMs: Long = 15_000, download: Progress? = null) =
        request("GET", path, timeoutMs = timeoutMs, download = download)

    /** A form (a=1&b=2), as the page sends it. */
    suspend fun post(path: String, form: String) =
        request("POST", path, form.toByteArray(), "application/x-www-form-urlencoded")
}

class BoardError(msg: String) : IOException(msg)
