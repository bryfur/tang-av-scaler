#!/usr/bin/env python3
"""capview.py [--port 8090] [--dev /dev/video0] [--size 1920x1080] [--fps 60]: a USB capture
dongle's picture on a web page.

The dongle makes Motion-JPEG itself; its frames are passed on as they are (no decoding, no
encoding: a tenth of a second from HDMI to the page on the local network) as a multipart stream an
<img> shows.  The device is opened while somebody watches (and for 10 s after): other tools can
have it the rest of the time.

    /               the page
    /frame?after=N  the next frame newer than number N (its number in X-Frame): what the page asks for
    /stream         the frames (multipart/x-mixed-replace), for players that take that
    /snapshot.jpg   the newest frame
    /status         JSON: frames a second, viewers
"""
import argparse
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = b"""<!doctype html><html><head><meta charset="utf-8"><title>capture</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>html,body{margin:0;height:100%;background:#111;color:#999;font:13px system-ui,sans-serif}
#v{display:block;margin:auto;max-width:100vw;max-height:100vh;cursor:pointer;background:#000}
#s{position:fixed;left:.6em;bottom:.4em;background:#000a;padding:.1em .4em}a{color:#9cf}</style></head><body>
<canvas id="v" width="1920" height="1080" title="click: full screen"></canvas>
<div id="s">connecting...</div>
<script>
// each frame asked for by itself (the answer waits for a frame newer than the last one shown) and
// drawn on a canvas: every browser does that, which cannot be said of a multipart stream in an <img>
const v=document.getElementById('v'),s=document.getElementById('s'),c=v.getContext('2d');
v.onclick=()=>document.fullscreenElement?document.exitFullscreen():v.requestFullscreen();
let n=-1,shown=0,bytes=0,t0=performance.now(),err='';
async function loop(){
  for(;;){
    try{
      const r=await fetch('/frame?after='+n,{cache:'no-store'});
      if(r.status!=200){err=(await r.text()).trim()||('HTTP '+r.status);await new Promise(f=>setTimeout(f,500));continue}
      n=+r.headers.get('X-Frame');
      const b=await r.blob(),im=await createImageBitmap(b);
      if(v.width!=im.width||v.height!=im.height){v.width=im.width;v.height=im.height}
      c.drawImage(im,0,0);im.close();shown++;bytes+=b.size;err='';
    }catch(e){err='no answer from the server';await new Promise(f=>setTimeout(f,1000))}
  }
}
setInterval(()=>{const t=performance.now(),d=(t-t0)/1000;
  s.innerHTML=err?err:(shown/d).toFixed(0)+' frames/s &middot; '+(bytes*8/d/1e6).toFixed(1)+' Mbit/s &middot; '+v.width+' x '+v.height+' &middot; <a href="/snapshot.jpg" target="_blank">snapshot</a>';
  shown=0;bytes=0;t0=t},2000);
loop();
</script></body></html>"""


class Source:
    """the dongle through ffmpeg, while wanted: the newest frame, and a count of them"""

    def __init__(self, a):
        self.a = a
        self.cond = threading.Condition()
        self.frame, self.n = None, 0
        self.viewers, self.wanted_until = 0, 0.0
        self.fps = self.kbps = 0.0
        self.error = ""
        threading.Thread(target=self.run, daemon=True).start()

    def want(self):
        with self.cond:
            self.wanted_until = time.time() + 10
            self.cond.notify_all()

    def wanted(self):
        return self.viewers > 0 or time.time() < self.wanted_until

    def run(self):
        while True:
            with self.cond:
                while not self.wanted():
                    self.cond.wait(1)
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "v4l2", "-input_format", "mjpeg",
                   "-video_size", self.a.size, "-framerate", str(self.a.fps), "-i", self.a.dev,
                   "-c", "copy", "-f", "mjpeg", "-"]
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
            buf, t0, n0, bytes0 = bytearray(), time.time(), self.n, 0
            try:
                while self.wanted():
                    chunk = p.stdout.read(65536)
                    if not chunk:
                        self.error = p.stderr.read().decode(errors="replace").strip()[-300:]
                        break
                    buf += chunk
                    # a frame: from FF D8 to the FF D9 before the next FF D8 (or the buffer's end)
                    while True:
                        end = buf.find(b"\xff\xd9\xff\xd8", 2)
                        if end < 0:
                            break
                        frame = bytes(buf[:end + 2])
                        del buf[:end + 2]
                        bytes0 += len(frame)
                        with self.cond:
                            self.frame, self.n = frame, self.n + 1
                            self.error = ""
                            self.cond.notify_all()
                    now = time.time()
                    if now - t0 >= 2:
                        self.fps, self.kbps = (self.n - n0) / (now - t0), bytes0 * 8 / 1000 / (now - t0)
                        t0, n0, bytes0 = now, self.n, 0
            finally:
                p.kill()
                p.wait()
                self.fps = self.kbps = 0.0
            time.sleep(1)

    def next(self, after, timeout=5):
        """(count, frame) newer than `after`, or (after, None)"""
        with self.cond:
            self.cond.wait_for(lambda: self.n != after, timeout)
            return (self.n, self.frame) if self.n != after else (after, None)


def handler(src):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"           # (the page's frames on one connection)

        def log_message(self, *a):
            pass

        def send(self, code, kind, body, extra=()):
            self.send_response(code)
            for k, val in extra:
                self.send_header(k, val)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                self.send(200, "text/html; charset=utf-8", PAGE)
            elif path == "/status":
                self.send(200, "application/json", json.dumps(
                    {"fps": src.fps, "kbps": src.kbps, "viewers": src.viewers, "watched": src.wanted(), "error": src.error}).encode())
            elif path == "/snapshot.jpg":
                src.want()
                n, frame = src.next(src.n if src.fps == 0 else -1, 6)
                if frame:
                    self.send(200, "image/jpeg", frame)
                else:
                    self.send(503, "text/plain", ("no frame: " + src.error + "\n").encode())
            elif path == "/frame":
                try:
                    after = int(self.path.split("after=")[1].split("&")[0])
                except (IndexError, ValueError):
                    after = -1
                src.want()
                n, frame = src.next(after, 4)
                if frame:
                    self.send(200, "image/jpeg", frame, [("X-Frame", str(n))])
                else:
                    self.send(503, "text/plain", ("no frame from the dongle. " + src.error + "\n").encode())
            elif path == "/stream":
                self.close_connection = True
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=f")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with src.cond:
                    src.viewers += 1
                    src.cond.notify_all()
                try:
                    n = src.n
                    while True:
                        n, frame = src.next(n)
                        if frame:               # (a slow viewer gets the newest, not every one)
                            self.wfile.write(b"--f\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(frame))
                            self.wfile.write(frame)
                            self.wfile.write(b"\r\n")
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    with src.cond:
                        src.viewers -= 1
            else:
                self.send(404, "text/plain", b"not here\n")
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--dev", default="/dev/video0")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--fps", type=int, default=60)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), handler(Source(a)))
    srv.daemon_threads = True
    print("capture on http://0.0.0.0:%d/" % a.port, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
