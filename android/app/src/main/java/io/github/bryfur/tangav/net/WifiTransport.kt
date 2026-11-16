package io.github.bryfur.tangav.net

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

/** The board's web API on the local network (host: an address, or address:port). */
class WifiTransport(val host: String) : Transport {
    override val kind = Transport.Kind.WIFI
    override val label = host

    override suspend fun request(
        method: String, path: String, body: ByteArray?, type: String?,
        timeoutMs: Long, upload: Progress?, download: Progress?,
    ): Response = withContext(Dispatchers.IO) {
        val c = URL("http://$host$path").openConnection() as HttpURLConnection
        try {
            c.requestMethod = method
            c.connectTimeout = 4000
            c.readTimeout = timeoutMs.toInt()
            c.useCaches = false
            if (type != null) c.setRequestProperty("Content-Type", type)
            if (body != null || method != "GET") {
                val b = body ?: ByteArray(0)
                c.doOutput = true
                c.setFixedLengthStreamingMode(b.size)
                c.outputStream.use { o ->
                    var off = 0
                    while (off < b.size) {
                        val n = minOf(8192, b.size - off)
                        o.write(b, off, n)
                        off += n
                        upload?.invoke(off.toLong(), b.size.toLong())
                    }
                }
            }
            val code = c.responseCode
            val total = c.contentLengthLong
            val s = if (code >= 400) c.errorStream else c.inputStream
            val out = java.io.ByteArrayOutputStream()
            s?.use { i ->
                val b = ByteArray(8192)
                var got = 0L
                while (true) {
                    val r = i.read(b)
                    if (r < 0) break
                    out.write(b, 0, r)
                    got += r
                    download?.invoke(got, total)
                }
            }
            Response(code, out.toByteArray())
        } finally {
            c.disconnect()
        }
    }

    override fun close() = Unit
}
