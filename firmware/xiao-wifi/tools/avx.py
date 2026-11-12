#!/usr/bin/env python3
"""avx.py: the PC's end of the Wi-Fi debug link (firmware/xiao-wifi) on the AV board's XIAO.

    avx.py status                 the link: firmware, Wi-Fi, who is on the JTAG and console ports
    avx.py fpga                   the FPGA's ID code and status register, read over JTAG by the link
    avx.py load FILE.fs           the bitstream into the FPGA's SRAM, by the link itself (the file is
                                  sent whole; a PC's loader over the XVC port is too slow between
                                  its steps for this FPGA: avx.py ofl FILE.fs fails)
    avx.py flash FILE.fs          the bitstream into the SOM's flash
    avx.py ofl ARGS...            openFPGALoader with the link as its cable, and ARGS
    avx.py console                the FPGA's UART on this terminal (Ctrl-] ends it)
    avx.py pty [PATH]             the FPGA's UART as a serial port at PATH (default /tmp/avb-tty) until
                                  interrupted: AVB_TTY=/tmp/avb-tty gateware/tools/avb.py id
    avx.py tail | log             the FPGA's last output | the link's own log
    avx.py ota [IMAGE]            a new firmware into the link over Wi-Fi (default: the C5 build here)
    avx.py wifi SSID              give the link a Wi-Fi network (asks for the password)
    avx.py restart

The link is found by name, avscaler.local; AVX_HOST names another host or address (192.168.4.1 on
the link's own access point).  OFL names openFPGALoader (default ~/tools/ofl/bin/openFPGALoader).
"""
import getpass
import json
import os
import pty
import select
import socket
import subprocess
import sys
import termios
import time
import tty
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PORT_XVC, PORT_CONSOLE = 2542, 2323


def host():
    return os.environ.get("AVX_HOST", "avscaler.local")


def address():
    try:
        return socket.gethostbyname(host())
    except OSError:
        sys.exit(f"{host()}: no such host on this network (AVX_HOST names the link's address)")


def http(path, data=None, timeout=10, kind="application/octet-stream"):
    req = urllib.request.Request(f"http://{address()}{path}", data=data, method="POST" if data is not None else "GET")
    if data is not None:
        req.add_header("Content-Type", kind)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"{path}: {e.code} {e.read().decode(errors='replace').strip()}")
    except OSError as e:
        sys.exit(f"{host()}: no answer ({e})")


def status():
    return json.loads(http("/api/status"))


def show_status():
    s = status()
    f, w, j, c = s["firmware"], s["wifi"], s["jtag"], s["console"]
    print(f"firmware  {f['version']}, built {f['built']}, {f['chip']} slot {f['slot']}, up {f['uptime_s']} s, "
          f"{f['heap']} bytes free")
    print(f"wifi      {w['ssid']} {w['ip']} {w['rssi']} dBm channel {w['channel']}, {w['host']}.local, {w['mac']}"
          + (f", access point {w['ap_ssid']} open" if w["ap"] else "") + (f", {w['drops']} drops" if w["drops"] else ""))
    print(f"jtag      port {j['port']}: " + (f"in use by {j['peer']}" if j["connected"] else "free")
          + f", {j['sessions']} sessions, {j['bits']} bits, TCK {j['tck_ns']} ns (fastest {j['fastest_ns']} ns)")
    print(f"console   port {c['port']} at {c['baud']} baud: " + (f"client {c['peer']}" if c["tcp"] else "no client")
          + (", USB" if c["usb"] else "") + f", {c['to_fpga']} bytes to the FPGA, {c['from_fpga']} from it")


def show_fpga():
    f = json.loads(http("/api/fpga"))
    if f["busy"]:
        sys.exit("the JTAG port is in use by a client")
    print(f"idcode {f['idcode']} status {f['status']}" + ("" if f["answers"] else ": nothing answers on JTAG"))
    return 0 if f["answers"] else 1


def bitstream(path):
    """(bytes, sum) of a Gowin .fs file: its bits as bytes, each byte's first bit its top one, and
    the 16-bit sum of its configuration words, both as openFPGALoader takes them (src/fsparser.cpp:
    every line that is not a comment is data; the line whose first byte's low seven bits are 0x3B
    ends the header and tells the number of configuration lines and whether each ends with a CRC;
    the sum is over those lines less their last six bytes, eight with a CRC)."""
    lines = []
    for raw in open(path, "rb").read().split(b"\n"):
        line = raw.rstrip(b"\r").decode("ascii", "replace")
        if not line:
            break
        if line[0] != "/":
            lines.append(line)
    end = crc = count = None
    for k, line in enumerate(lines):
        key = int(line[:8], 2) & 0x7F
        if key == 0x10 and int(line, 2) >> 13 & 1:
            sys.exit(f"{path}: a compressed bitstream (set_option -bit_compress 0)")
        if key == 0x3B:
            v = int(line, 2)
            end, crc, count = k, v >> 23 & 1, v & 0xFFFF
            break
    if end is None:
        sys.exit(f"{path}: not a Gowin .fs file (no end of header)")
    data = b"".join(int(line, 2).to_bytes(len(line) // 8, "big") for line in lines)
    drop = (8 if crc else 6) * 8
    total = 0
    for line in lines[end + 1:end + 1 + min(count, 65535)]:
        body = line[:len(line) - drop]
        if body:
            total += sum(int.from_bytes(int(body, 2).to_bytes(len(body) // 8, "big")[p:p + 2], "big")
                         for p in range(0, len(body) // 8, 2))
    return data, total & 0xFFFF


def load(path):
    """The bitstream into the FPGA's SRAM by the link itself (POST /api/load, firmware gowin.c).  The
    link answers at once and loads on its own, off the network for the while (it may drop off Wi-Fi
    and join again); its report is fetched afterwards."""
    data, total = bitstream(path)
    print(f"{os.path.basename(path)}: {len(data)} bytes, sum {total:04x}, to {host()}")
    extra = os.environ.get("AVX_LOAD", "")     # e.g. "&stop=30&hold=1": the loader's waits (firmware gowin.c)
    started = http(f"/api/load?sum={total}{extra}", data, timeout=120).decode(errors="replace").split()
    if len(started) < 2 or started[1] != "started":
        sys.exit("the link did not start the load: " + " ".join(started))
    # its report, asked for every 2 s; a link that has started again (its count of loads back at
    # zero) lost it: said at once, with why it restarted
    reasons = {4: "a crash", 5: "its interrupt watchdog", 6: "its task watchdog", 7: "a watchdog", 9: "a brown-out"}
    t0 = time.time()
    while time.time() - t0 < 100:
        time.sleep(2)
        try:
            with urllib.request.urlopen(f"http://{address()}/api/load", timeout=3) as r:
                out = r.read().decode(errors="replace")
        except (OSError, SystemExit):
            continue                            # off the network while it loads
        head, _, report = out.partition("\n")
        if head.split()[:2] == [started[0], "done"]:
            print(report.strip())
            return 0 if "\nloaded" in "\n" + report else 1
        if head.split()[:1] != [started[0]]:
            f = status()["firmware"]
            sys.exit(f"the link restarted during the load ({reasons.get(f.get('reset'), 'reset %s' % f.get('reset'))}, "
                     f"{time.time() - t0:.0f} s in): the FPGA is not loaded")
    sys.exit("no report from the link in 100 s")


def ofl(args):
    exe = os.environ.get("OFL", os.path.expanduser("~/tools/ofl/bin/openFPGALoader"))
    return subprocess.call([exe, "-c", "xvc-client", "--ip", address(), "--port", str(PORT_XVC)] + args)


def console_socket():
    try:
        s = socket.create_connection((address(), PORT_CONSOLE), timeout=5)
    except OSError as e:
        sys.exit(f"{host()}: no console port ({e})")
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.settimeout(None)
    return s


def pump(s, fd_in, fd_out, quit_byte=None):
    """bytes between the socket and a pair of file descriptors until either ends"""
    while True:
        r, _, _ = select.select([s, fd_in], [], [])
        if s in r:
            data = s.recv(65536)
            if not data:
                return "the link closed the console"
            os.write(fd_out, data)
        if fd_in in r:
            try:
                data = os.read(fd_in, 65536)
            except OSError:
                data = b""              # (a pty with no program on its other end)
                time.sleep(0.05)
            if quit_byte is not None and quit_byte in data:
                return None
            if data:
                s.sendall(data)


def console():
    s = console_socket()
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        return pump(s, fd, sys.stdout.fileno())
    old = termios.tcgetattr(fd)
    print(f"the FPGA's console on {host()} (Ctrl-] ends it)\r")
    try:
        tty.setraw(fd)
        why = pump(s, fd, sys.stdout.fileno(), quit_byte=0x1D)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    print("\r\n" + (why or "ended"))


def serial_port(path):
    s = console_socket()
    master, slave = pty.openpty()
    tty.setraw(slave)
    if os.path.islink(path):
        os.unlink(path)
    os.symlink(os.ttyname(slave), path)
    print(f"{path} -> {os.ttyname(slave)}: the FPGA's UART on {host()} (Ctrl-C ends it)", flush=True)
    try:
        why = pump(s, master, master)
        print(why)
    except KeyboardInterrupt:
        pass
    finally:
        os.unlink(path)


def ota(image):
    image = image or os.path.join(HERE, "..", "build-esp32c5", "avwifi.bin")
    data = open(image, "rb").read()
    before = status()["firmware"]
    print(f"{os.path.basename(image)}: {len(data)} bytes to {host()} (now {before['version']}, slot {before['slot']})")
    print(http("/api/ota", data, timeout=120).decode().strip())
    # the new firmware is on trial until its status has been read: this is that read
    t0 = time.time()
    time.sleep(3)
    while time.time() - t0 < 90:
        try:
            with urllib.request.urlopen(f"http://{address()}/api/status", timeout=3) as r:
                f = json.loads(r.read())["firmware"]
            if f["uptime_s"] < 60 and f["slot"] != before["slot"]:
                print(f"running {f['version']}, built {f['built']}, slot {f['slot']}: kept")
                return 0
            if f["uptime_s"] < 60:
                print(f"back in slot {f['slot']} ({f['version']}): the new firmware was not taken")
                return 1
        except (OSError, SystemExit):
            pass
        time.sleep(1)
    print("the link has not come back: if the new firmware cannot be reached it goes back to the old one "
          "by itself 3 minutes after its start")
    return 1


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "status":
        show_status()
    elif cmd == "fpga":
        return show_fpga()
    elif cmd == "load" and len(argv) == 3:
        return load(argv[2])
    elif cmd == "flash" and len(argv) == 3:
        return ofl(["-f", argv[2]])
    elif cmd == "ofl":
        return ofl(argv[2:])
    elif cmd == "console":
        console()
    elif cmd == "pty":
        serial_port(argv[2] if len(argv) > 2 else "/tmp/avb-tty")
    elif cmd == "tail":
        sys.stdout.buffer.write(http("/api/console"))
    elif cmd == "log":
        sys.stdout.buffer.write(http("/api/log"))
    elif cmd == "ota":
        return ota(argv[2] if len(argv) > 2 else None)
    elif cmd == "wifi" and len(argv) == 3:
        password = getpass.getpass(f"password for {argv[2]}: ")
        body = urllib.parse.urlencode({"ssid": argv[2], "pass": password}).encode()
        print(http("/api/wifi", body, kind="application/x-www-form-urlencoded").decode().strip())
    elif cmd == "restart":
        print(http("/api/restart", b"").decode().strip())
    else:
        sys.exit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
