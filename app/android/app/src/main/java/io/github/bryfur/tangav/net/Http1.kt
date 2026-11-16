package io.github.bryfur.tangav.net

import java.io.InputStream
import java.io.OutputStream

/**
 * HTTP/1.1 over a stream (the Bluetooth channel): one request, one response, the connection kept for
 * the next.  What the board's server sends: Content-Length, or chunked (a capture), or to the close.
 */
object Http1 {
    fun write(out: OutputStream, method: String, path: String, body: ByteArray?, type: String?, upload: Progress?) {
        val h = StringBuilder("$method $path HTTP/1.1\r\nHost: avscaler\r\n")
        if (body != null || method != "GET") h.append("Content-Length: ${body?.size ?: 0}\r\n")
        if (type != null) h.append("Content-Type: $type\r\n")
        h.append("\r\n")
        out.write(h.toString().toByteArray())
        if (body != null) {
            var off = 0
            while (off < body.size) {
                val n = minOf(8192, body.size - off)
                out.write(body, off, n)
                off += n
                upload?.invoke(off.toLong(), body.size.toLong())
            }
        }
        out.flush()
    }

    fun read(inp: InputStream, download: Progress?): Response {
        val status = line(inp) ?: throw BoardError("the channel closed")
        val code = status.split(' ').getOrNull(1)?.toIntOrNull() ?: throw BoardError("not HTTP: $status")
        var length = -1L
        var chunked = false
        while (true) {
            val l = line(inp) ?: throw BoardError("the channel closed in the headers")
            if (l.isEmpty()) break
            val i = l.indexOf(':')
            if (i < 0) continue
            val k = l.substring(0, i).trim().lowercase()
            val v = l.substring(i + 1).trim()
            if (k == "content-length") length = v.toLongOrNull() ?: -1
            if (k == "transfer-encoding" && v.contains("chunked", true)) chunked = true
        }
        val buf = java.io.ByteArrayOutputStream(if (length in 0..(64L shl 20)) length.toInt() else 4096)
        var got = 0L
        fun take(n: Long) {
            val b = ByteArray(8192)
            var left = n
            while (left > 0) {
                val r = inp.read(b, 0, minOf(b.size.toLong(), left).toInt())
                if (r < 0) throw BoardError("the channel closed in the body")
                buf.write(b, 0, r)
                left -= r
                got += r
                download?.invoke(got, length)
            }
        }
        when {
            chunked -> while (true) {
                val size = (line(inp) ?: throw BoardError("the channel closed")).substringBefore(';').trim().toLong(16)
                if (size == 0L) {
                    while ((line(inp) ?: "").isNotEmpty()) Unit      // (trailers)
                    break
                }
                take(size)
                line(inp)                                           // (the chunk's CRLF)
            }
            length >= 0 -> take(length)
            else -> {
                val b = ByteArray(8192)
                while (true) {
                    val r = inp.read(b)
                    if (r < 0) break
                    buf.write(b, 0, r)
                }
            }
        }
        return Response(code, buf.toByteArray())
    }

    private fun line(inp: InputStream): String? {
        val sb = StringBuilder()
        while (true) {
            val c = inp.read()
            if (c < 0) return if (sb.isEmpty()) null else sb.toString()
            if (c == '\n'.code) return sb.toString().trimEnd('\r')
            sb.append(c.toChar())
        }
    }
}
