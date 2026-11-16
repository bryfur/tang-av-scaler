package io.github.bryfur.tangav.net

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.IOException
import java.util.Timer
import kotlin.concurrent.schedule

/**
 * The board's web API over Bluetooth LE: an L2CAP channel (PSM 0x81, LE credit-based) is one
 * connection to the board's own web server, so the requests are the same bytes as over Wi-Fi.  No
 * pairing: the board lets anyone in range open one (firmware ble.c).  One request at a time on the
 * one channel; a channel the board closed is opened again.
 */
@SuppressLint("MissingPermission")     // (BLUETOOTH_CONNECT: asked for before a board is chosen)
class BleTransport(val device: BluetoothDevice) : Transport {
    companion object {
        const val PSM = 0x81
        val SERVICE: java.util.UUID = java.util.UUID.fromString("7a6e0001-5461-6e67-2041-562053636c72")
    }

    override val kind = Transport.Kind.BLUETOOTH
    override val label: String = (try { device.name } catch (e: SecurityException) { null }) ?: device.address

    private val lock = Mutex()
    private var sock: BluetoothSocket? = null
    private var inp: BufferedInputStream? = null
    private var out: BufferedOutputStream? = null
    private val timer = Timer("ble-timeout", true)

    private fun open() {
        val s = device.createInsecureL2capChannel(PSM)
        s.connect()
        sock = s
        inp = BufferedInputStream(s.inputStream, 16384)
        out = BufferedOutputStream(s.outputStream, 16384)
    }

    private fun drop() {
        try { sock?.close() } catch (_: IOException) {}
        sock = null; inp = null; out = null
    }

    override suspend fun request(
        method: String, path: String, body: ByteArray?, type: String?,
        timeoutMs: Long, upload: Progress?, download: Progress?,
    ): Response = lock.withLock {
        withContext(Dispatchers.IO) {
            // (a stale channel fails at once: one more try on a new one, unless a large body went out)
            val tries = if (body == null || body.size < 16384) 2 else 1
            var last: IOException? = null
            for (t in 0 until tries) {
                // (a Bluetooth socket has no timeout of its own: a dead link is closed under the read)
                val watchdog = timer.schedule(timeoutMs + (body?.size ?: 0) / 2) { drop() }
                try {
                    if (sock == null) open()
                    Http1.write(out!!, method, path, body, type, upload)
                    return@withContext Http1.read(inp!!, download)
                } catch (e: IOException) {
                    last = e
                    drop()
                } finally {
                    watchdog.cancel()
                }
            }
            throw last ?: BoardError("no answer over Bluetooth")
        }
    }

    override fun close() {
        drop()
        timer.cancel()
    }
}
