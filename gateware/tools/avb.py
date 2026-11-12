#!/usr/bin/env python3
"""avb.py: the host's end of the bring-up monitor (rtl/mon.v, rtl/top.v's registers) on the XIAO's
USB serial port.

    avb.py id                    # ID, build time, STAT
    avb.py r ADDR | w ADDR VALUE
    avb.py listen [SECONDS]      # whatever the FPGA says by itself (its "AVB1" banner)
    avb.py scan [BUS]            # I2C addresses that answer on bus 0 PLL, 1 DP, 2 DDC, 3 IN
    avb.py freq                  # the frequency meters

The port is opened without touching DTR/RTS by themselves: the ESP32-S3's USB-Serial-JTAG takes
RTS without DTR for a reset (and DTR before it for "into the loader").
"""
import glob
import os
import socket
import sys
import termios
import time

ID, BUILD, CTRL, STAT, I2C, I2C_SH, FREQ = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x10
BUSES = {"pll": 0, "dp": 1, "ddc": 2, "in": 3}
HZ_PER_COUNT = 16 * 50e6 / 2 ** 25


def port():
    """The monitor's UART: AVB_TTY (a serial device, or tcp:HOST[:PORT], the Wi-Fi link's console
    port, firmware/xiao-wifi); else the Wi-Fi link if it answers by name (AVX_HOST, avscaler.local);
    else a XIAO's USB serial port."""
    p = os.environ.get("AVB_TTY")
    if p:
        return p
    try:
        host = os.environ.get("AVX_HOST", "avscaler.local")
        socket.create_connection((socket.gethostbyname(host), 2323), timeout=1.5).close()
        return "tcp:" + host
    except OSError:
        pass
    found = glob.glob("/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_*")
    if not found:
        sys.exit("no Wi-Fi link (avscaler.local) and no XIAO (USB 303a:1001) serial port; AVB_TTY names one")
    return found[0]


class Mon:
    def __init__(self, tty=None):
        tty = tty or port()
        self.sock = None
        if tty.startswith("tcp:"):
            host, _, tcp_port = tty[4:].partition(":")
            self.sock = socket.create_connection((socket.gethostbyname(host), int(tcp_port or 2323)), timeout=5)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.sock.setblocking(False)
            self.fd = self.sock.fileno()
        else:
            self.fd = os.open(tty, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            a = termios.tcgetattr(self.fd)
            a[0] = a[1] = a[3] = 0
            a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            termios.tcsetattr(self.fd, termios.TCSANOW, a)
        self.out = bytearray()
        self.drv = 0
        time.sleep(0.05)
        self.read_raw()             # drop the banner

    def close(self):
        self.flush()
        if self.sock:
            self.sock.close()
        else:
            os.close(self.fd)

    def read_raw(self):
        try:
            return os.read(self.fd, 65536)
        except BlockingIOError:
            return b""

    def flush(self):
        data, self.out = bytes(self.out), bytearray()
        while data:
            try:
                n = os.write(self.fd, data)
            except BlockingIOError:
                n = 0
                time.sleep(0.001)
            data = data[n:]

    def w(self, addr, value):
        self.out += b"W" + bytes([addr]) + (value & 0xFFFFFFFF).to_bytes(4, "little")
        if len(self.out) > 3000:    # the monitor's FIFO is 4096
            self.flush()
            time.sleep(0.03)

    def r(self, addr, timeout=4.0):
        self.out += b"R" + bytes([addr])
        self.flush()
        buf, t0 = b"", time.time()
        while len(buf) < 4:
            buf += self.read_raw()
            if time.time() - t0 > timeout:
                raise TimeoutError("no answer from the monitor (register %#x): got %r" % (addr, buf))
            if len(buf) < 4:
                time.sleep(0.0005)
        return int.from_bytes(buf[:4], "little")

    # --- I2C, bit by bit through the I2C register (1 = line pulled low) ---

    def _lines(self, bus, scl=None, sda=None):
        if scl is not None:
            self.drv = self.drv & ~(1 << 2 * bus) | (0 if scl else 1) << 2 * bus
        if sda is not None:
            self.drv = self.drv & ~(2 << 2 * bus) | (0 if sda else 2) << 2 * bus
        self.w(I2C, self.drv)

    def i2c_start(self, bus):
        self._lines(bus, sda=1)
        self._lines(bus, scl=1)
        self._lines(bus, sda=0)
        self._lines(bus, scl=0)

    def i2c_stop(self, bus):
        self._lines(bus, sda=0)
        self._lines(bus, scl=1)
        self._lines(bus, sda=1)

    def _clock(self, bus, sda):
        self._lines(bus, sda=sda)
        self._lines(bus, scl=1)
        self._lines(bus, scl=0)

    def i2c_put(self, bus, byte):
        """A byte out; the acknowledge bit is left in the shift register's bit 0."""
        for k in range(7, -1, -1):
            self._clock(bus, byte >> k & 1)
        self._clock(bus, 1)

    def i2c_ack(self, bus):
        return not self.r(I2C_SH + bus) & 1

    def i2c_get(self, bus, ack):
        for _ in range(8):
            self._clock(bus, 1)
        self._clock(bus, 0 if ack else 1)

    # Nothing is read back from the monitor in the middle of a transaction: with the Wi-Fi link in
    # the socket each answer is a radio transmission beside the board, and the MS5351M's bus took
    # those for clock edges (the bytes after an answer came back wrong).  The shift register holds
    # the last 32 SCL rises: read once, after the stop (whose own rise is bit 0).

    def i2c_write(self, bus, dev, data):
        """True if the last three bytes sent were acknowledged (all of them, up to two bytes of
        data)."""
        self.i2c_start(bus)
        data = bytes([dev << 1]) + bytes(data)
        for b in data:
            self.i2c_put(bus, b)
        self.i2c_stop(bus)
        sh = self.r(I2C_SH + bus)
        return not any(sh >> (1 + 9 * j) & 1 for j in range(min(3, len(data))))

    def i2c_read(self, bus, dev, reg, n=1):
        """n bytes from reg on (write reg, repeated start, read), three a transaction."""
        out = bytearray()
        while len(out) < n:
            k = min(3, n - len(out))
            self.i2c_start(bus)
            self.i2c_put(bus, dev << 1)
            self.i2c_put(bus, reg + len(out) & 0xFF)
            self._lines(bus, sda=1)
            self.i2c_start(bus)
            self.i2c_put(bus, dev << 1 | 1)
            for j in range(k):
                self.i2c_get(bus, j != k - 1)
            self.i2c_stop(bus)
            sh = self.r(I2C_SH + bus)
            if sh >> (1 + 9 * k) & 1:
                raise IOError("I2C bus %d device %#x: no acknowledge" % (bus, dev))
            out += bytes(sh >> (2 + 9 * (k - 1 - j)) & 0xFF for j in range(k))
        return bytes(out)

    def i2c_recv(self, bus, dev, n):
        """n bytes read straight off (no register address first), or None with no acknowledge."""
        self.i2c_start(bus)
        self.i2c_put(bus, dev << 1 | 1)
        if not self.i2c_ack(bus):
            self.i2c_stop(bus)
            self.flush()
            return None
        out = bytearray()
        for k in range(n):
            self.i2c_get(bus, k != n - 1)
            out.append(self.r(I2C_SH + bus) >> 1 & 0xFF)
        self.i2c_stop(bus)
        self.flush()
        return bytes(out)

    def i2c_probe(self, bus, dev):
        self.i2c_start(bus)
        self.i2c_put(bus, dev << 1)
        ack = self.i2c_ack(bus)
        self.i2c_stop(bus)
        self.flush()
        return ack

    def freq(self, k):
        return self.r(FREQ + k) * HZ_PER_COUNT


def main():
    a = sys.argv[1:] or ["id"]
    if a[0] == "listen":
        fd = Mon()
        t0, buf = time.time(), b""
        while time.time() - t0 < float(a[1] if len(a) > 1 else 2):
            buf += fd.read_raw()
            time.sleep(0.02)
        print(buf)
        return
    m = Mon()
    if a[0] == "id":
        i = m.r(ID)
        b = m.r(BUILD)
        print("ID %08x (%s)  build %s  STAT %08x  CTRL %08x  I2C %08x" %
              (i, i.to_bytes(4, "little").decode(errors="replace"), time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(b)),
               m.r(STAT), m.r(CTRL), m.r(I2C)))
    elif a[0] == "r":
        print("%08x" % m.r(int(a[1], 0)))
    elif a[0] == "w":
        m.w(int(a[1], 0), int(a[2], 0))
    elif a[0] == "scan":
        for name, bus in BUSES.items():
            if len(a) > 1 and a[1] not in (name, str(bus)):
                continue
            print("%-3s:" % name, " ".join("%02x" % d for d in range(0x08, 0x78) if m.i2c_probe(bus, d)) or "-")
    elif a[0] == "freq":
        for k, name in enumerate(("pll_clk2", "in_llc")):
            print("%-9s %12.0f Hz" % (name, m.freq(k)))
    else:
        sys.exit(__doc__)
    m.close()


if __name__ == "__main__":
    main()
