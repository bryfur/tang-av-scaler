#!/usr/bin/env python3
"""capview.py [--port 8090] [--dev /dev/video0] [--size 1920x1080] [--fps 60] [--qp 27]: a USB
capture dongle's picture on a web page, two ways:

  Motion-JPEG   the dongle's own frames passed on as they are (no decoding, no encoding here): the
                least delay, 30-40 Mbit/s
  H.264, H.265  the frames decoded and encoded again by the GPU (VA-API: h264_vaapi, hevc_vaapi;
                quantiser --qp), sent as fragmented MP4, a frame a fragment, and played through Media
                Source Extensions: a fraction of the bit rate, a few frames more delay.  This AMD
                GPU's H.265 plays in ffmpeg but not in Apple's decoder (VideoToolbox: -12909,
                whatever the level, range, size, quantiser or slices): H.264 for a Mac
  H.265 (x265)  the same in software: plays everywhere, six processor cores for 1080p60

One ffmpeg has the dongle while somebody watches (and for 10 s after); the encoder runs only while
somebody watches H.265.

    /                 the page
    /frame?after=N    the next JPEG frame newer than number N (its number in X-Frame)
    /stream           the JPEG frames as multipart/x-mixed-replace
    /h264 /h265 /x265 the encoded stream: the MP4's header, then fragments from the next key frame on
                      (one encoder at a time: whoever watches has it)
    /audio            the dongle's sound: AAC in fragmented MP4 (the page's "sound" switch)
    /snapshot.jpg     the newest JPEG frame
    /status           JSON: frames a second, bit rates, viewers
"""
import argparse
import json
import os
import queue
import struct
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = rb"""<!doctype html><html><head><meta charset="utf-8"><title>capture</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>html,body{margin:0;height:100%;background:#111;color:#999;font:13px system-ui,sans-serif}
#v,#h{display:block;margin:auto;max-width:100vw;max-height:100vh;cursor:pointer;background:#000}
#bar{position:fixed;left:.6em;bottom:.4em;background:#000a;padding:.15em .5em}a{color:#9cf}
select{font:inherit;background:#222;color:#ccc;border:1px solid #555}label{margin:0 .6em}</style></head><body>
<canvas id="v" width="1920" height="1080" title="click: full screen"></canvas>
<video id="h" muted autoplay playsinline style="display:none" title="click: full screen"></video>
<audio id="au"></audio>
<div id="bar"><select id="mode"><option value="mjpeg">Motion-JPEG (as the dongle sends it)</option>
<option value="h264">H.264 (encoded by the GPU)</option>
<option value="h265">H.265 (encoded by the GPU: not for Apple's decoder)</option>
<option value="x265">H.265 (encoded in software: six processor cores)</option></select>
<label><input type="checkbox" id="snd"> sound</label> <span id="s">connecting...</span></div>
<script>
const $=i=>document.getElementById(i),v=$('v'),h=$('h'),s=$('s'),c=v.getContext('2d');
const CODECS={h264:'video/mp4; codecs="avc1.64002A"',h265:'video/mp4; codecs="hvc1.1.6.L153.B0"',x265:'video/mp4; codecs="hvc1.1.6.L123.B0"'};
for(const e of [v,h])e.onclick=()=>document.fullscreenElement?document.exitFullscreen():e.requestFullscreen();
let gen=0,shown=0,bytes=0,t0=performance.now(),err='',note='',told='';
const wait=ms=>new Promise(f=>setTimeout(f,ms));
const say=t=>fetch('/log?'+encodeURIComponent(t+' | '+navigator.userAgent)).catch(()=>{});

// Motion-JPEG: each frame asked for by itself (the answer waits for one newer than the last shown)
async function mjpeg(g){
  let n=-1;
  while(g==gen){
    try{
      const r=await fetch('/frame?after='+n,{cache:'no-store'});
      if(r.status!=200){err=(await r.text()).trim()||('HTTP '+r.status);await wait(500);continue}
      n=+r.headers.get('X-Frame');
      const b=await r.blob(),im=await createImageBitmap(b);
      if(g!=gen)break;
      if(v.width!=im.width||v.height!=im.height){v.width=im.width;v.height=im.height}
      c.drawImage(im,0,0);im.close();shown++;bytes+=b.size;err='';
    }catch(e){err='no answer from the server';await wait(1000)}
  }
}

// H.265: the MP4 fragments into a MediaSource as they come; the player kept at the newest frame
async function coded(g,kind){
  const MS=window.ManagedMediaSource||window.MediaSource,CODEC=CODECS[kind];
  if(!MS||!MS.isTypeSupported(CODEC)){err='this browser does not play that here';$('mode').value='mjpeg';start();return}
  while(g==gen){
    const ms=new MS(),ac=new AbortController();
    h.disableRemotePlayback=true;h.src=URL.createObjectURL(ms);
    try{
      await new Promise(f=>ms.addEventListener('sourceopen',f,{once:true}));
      const sb=ms.addSourceBuffer(CODEC);sb.mode='segments';
      const r=await fetch('/'+kind,{cache:'no-store',signal:ac.signal});
      if(r.status!=200)throw new Error((await r.text()).trim()||('HTTP '+r.status));
      const rd=r.body.getReader();let last=performance.now(),f0=0;
      const tick=setInterval(()=>{
        if(g!=gen){ac.abort();return}
        const b=h.buffered;if(!b.length)return;
        const end=b.end(b.length-1),lag=end-h.currentTime;
        if(lag>0.35||h.currentTime<b.start(b.length-1))h.currentTime=end-0.05;   // fallen behind: to the newest
        h.playbackRate=lag>0.15?1.1:1;
        if(h.paused)h.play().catch(()=>{});
        const q=h.getVideoPlaybackQuality?h.getVideoPlaybackQuality().totalVideoFrames:0;shown+=q-f0;f0=q;
        note=(lag*1000).toFixed(0)+' ms buffered';
        if(q>120&&told!=kind){told=kind;say(kind+': playing, '+h.videoWidth+'x'+h.videoHeight)}
        if(!sb.updating&&b.start(0)<end-10)try{sb.remove(0,end-5)}catch(e){}
      },250);
      try{
        for(;;){
          const {value,done}=await rd.read();if(done)throw new Error('the stream ended');
          bytes+=value.length;err='';
          while(sb.updating)await new Promise(f=>sb.addEventListener('updateend',f,{once:true}));
          sb.appendBuffer(value);
        }
      }finally{clearInterval(tick);ac.abort()}
    }catch(e){if(g==gen){
      const me=h.error?' [media error '+h.error.code+': '+(h.error.message||'')+']':'';
      err=String(e.message||e)+me;say(kind+': '+err);await wait(2000)}}
  }
}
// the sound: its own stream (AAC) beside whichever picture, kept at the newest too
let sgen=0;
async function sound(g){
  const au=$('au'),MS=window.ManagedMediaSource||window.MediaSource,T='audio/mp4; codecs="mp4a.40.2"';
  while(g==sgen){
    const ms=new MS(),ac=new AbortController();
    au.disableRemotePlayback=true;au.src=URL.createObjectURL(ms);
    try{
      await new Promise(f=>ms.addEventListener('sourceopen',f,{once:true}));
      const sb=ms.addSourceBuffer(T);
      const r=await fetch('/audio',{cache:'no-store',signal:ac.signal});
      if(r.status!=200)throw new Error((await r.text()).trim()||('HTTP '+r.status));
      const rd=r.body.getReader();
      const tick=setInterval(()=>{
        if(g!=sgen){ac.abort();return}
        const b=au.buffered;if(!b.length)return;
        const end=b.end(b.length-1),lag=end-au.currentTime;
        if(lag>0.4||au.currentTime<b.start(b.length-1))au.currentTime=end-0.08;
        au.playbackRate=lag>0.2?1.05:1;
        if(au.paused)au.play().catch(e=>{snote='click the page for sound'});else snote='';
        if(!sb.updating&&b.start(0)<end-10)try{sb.remove(0,end-5)}catch(e){}
      },250);
      try{
        for(;;){
          const {value,done}=await rd.read();if(done)throw new Error('the sound ended');
          while(sb.updating)await new Promise(f=>sb.addEventListener('updateend',f,{once:true}));
          sb.appendBuffer(value);
        }
      }finally{clearInterval(tick);ac.abort()}
    }catch(e){if(g==sgen){snote='sound: '+String(e.message||e);say(snote);await wait(2000)}}
  }
}
let snote='';
$('snd').onchange=()=>{sgen++;snote='';localStorage.capsound=$('snd').checked?1:0;
  if($('snd').checked)sound(sgen);else{$('au').pause();$('au').removeAttribute('src');$('au').load()}};
document.addEventListener('click',()=>{if($('snd').checked&&$('au').paused)$('au').play().catch(()=>{})});
function start(){
  gen++;err='';note='';
  const m=$('mode').value;localStorage.capmode=m;
  v.style.display=m=='mjpeg'?'block':'none';h.style.display=m!='mjpeg'?'block':'none';
  if(m=='mjpeg'){h.removeAttribute('src');h.load();mjpeg(gen)}else coded(gen,m);
}
$('mode').onchange=start;
if(localStorage.capmode)$('mode').value=localStorage.capmode;
if(localStorage.capsound==1){$('snd').checked=true;sound(++sgen)}
setInterval(()=>{const t=performance.now(),d=(t-t0)/1000,e=$('mode').value!='mjpeg'?h:v;
  s.innerHTML=err?err:(shown/d).toFixed(0)+' frames/s &middot; '+(bytes*8/d/1e6).toFixed(1)+' Mbit/s &middot; '+
    (e.videoWidth||e.width)+' x '+(e.videoHeight||e.height)+(note?' &middot; '+note:'')+(snote?' &middot; '+snote:'')+' &middot; <a href="/snapshot.jpg" target="_blank">snapshot</a>';
  shown=0;bytes=0;t0=t},2000);
start();
</script></body></html>"""


def key_fragment(moof):
    """is a moof's first sample a sync sample [ISO 14496-12: trun, tfhd; flag bit 16: not sync]"""
    def boxes(buf, start, end):
        while start + 8 <= end:
            size, kind = struct.unpack(">I4s", buf[start:start + 8])
            if size < 8:
                return
            yield kind, start + 8, start + size
            start += size
    default = None
    for kind, a, b in boxes(moof, 8, len(moof)):
        if kind != b"traf":
            continue
        for k2, a2, b2 in boxes(moof, a, b):
            flags = int.from_bytes(moof[a2 + 1:a2 + 4], "big") if b2 - a2 >= 4 else 0
            if k2 == b"tfhd":
                p = a2 + 8 + (8 if flags & 1 else 0) + (4 if flags & 2 else 0) + (4 if flags & 8 else 0) + (4 if flags & 0x10 else 0)
                if flags & 0x20:
                    default = int.from_bytes(moof[p:p + 4], "big")
            elif k2 == b"trun":
                p = a2 + 8 + (4 if flags & 1 else 0)
                if flags & 4:
                    return not int.from_bytes(moof[p:p + 4], "big") & 0x10000
                if flags & 0x400:
                    p += (4 if flags & 0x100 else 0) + (4 if flags & 0x200 else 0)
                    return not int.from_bytes(moof[p:p + 4], "big") & 0x10000
                return default is not None and not default & 0x10000
    return False


class Source:
    """the dongle through one ffmpeg, while wanted: the newest JPEG frame; with H.265 viewers the
    same frames encoded too, their MP4 fragments to each viewer's queue"""

    def __init__(self, a):
        self.a = a
        self.cond = threading.Condition()
        self.frame, self.n = None, 0
        self.viewers, self.wanted_until = 0, 0.0
        self.fps = self.kbps = self.hkbps = 0.0
        self.error = ""
        self.hq = []                    # the encoded stream's viewers' queues
        self.kind = ""                  # which encoder they watch: h264, h265, x265 (the last asked for)
        self.init = None                # the MP4's ftyp and moov
        self.hbytes = 0
        threading.Thread(target=self.run, daemon=True).start()

    def want(self):
        with self.cond:
            self.wanted_until = time.time() + 10
            self.cond.notify_all()

    def wanted(self):
        return self.viewers > 0 or bool(self.hq) or time.time() < self.wanted_until

    def command(self, enc, fd):
        """ffmpeg: the dongle's Motion-JPEG out as it is and, with enc (h264, h265, x265), encoded too"""
        a = self.a
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
        if enc in ("h264", "h265"):
            cmd += ["-vaapi_device", a.render]
        cmd += ["-f", "v4l2", "-input_format", "mjpeg", "-video_size", a.size, "-framerate", str(a.fps), "-i", a.dev,
                "-map", "0:v", "-c", "copy", "-f", "mjpeg", "pipe:1"]
        mp4 = ["-tag:v", "avc1" if enc == "h264" else "hvc1", "-f", "mp4", "-movflags",
               "frag_every_frame+empty_moov+default_base_moof", "pipe:%d" % fd]
        gop = ["-g", str(a.fps // 2), "-bf", "0"]
        # (the GPU's encoders at a constant quantiser: its bit-rate modes make H.265 streams ffmpeg's
        # own decoder finds faults in, cu_qp_delta out of range)
        if enc == "h264":
            cmd += ["-map", "0:v", "-vf", a.vf, "-c:v", "h264_vaapi", "-rc_mode", "CQP", "-qp", str(a.qp - 3),
                    "-profile:v", "high", "-level", "4.2"] + gop + ["-async_depth", "1"] + mp4
        elif enc == "h265":
            # (level 5.1 said outright: left alone the encoder says 4.0 for 1080p60)
            cmd += ["-map", "0:v", "-vf", a.vf, "-c:v", "hevc_vaapi", "-rc_mode", "CQP", "-qp", str(a.qp)] + \
                   a.hevc.split() + gop + ["-async_depth", "1"] + mp4
        elif enc == "x265":
            cmd += ["-map", "0:v", "-vf", "format=yuv420p", "-c:v", "libx265", "-preset", "ultrafast", "-tune", "zerolatency",
                    "-crf", str(a.qp), "-x265-params",
                    "keyint=%d:min-keyint=%d:log-level=error" % (a.fps // 2, a.fps // 2)] + mp4
        return cmd

    def read_mp4(self, f):
        """the encoder's MP4: its header kept, each moof with its mdat to the viewers"""
        def box():
            head = f.read(8)
            if len(head) < 8:
                return None, None
            size, kind = struct.unpack(">I4s", head)
            body = b""
            while len(body) < size - 8:
                more = f.read(size - 8 - len(body))
                if not more:
                    return None, None
                body += more
            return kind, head + body
        init, moof = b"", None
        while True:
            kind, data = box()
            if kind is None:
                return
            if kind in (b"ftyp", b"moov"):
                init += data
                if kind == b"moov":
                    self.init = init
            elif kind == b"moof":
                moof = data
            elif kind == b"mdat" and moof:
                item = (key_fragment(moof), moof + data)
                self.hbytes += len(item[1])
                with self.cond:
                    for q in self.hq:
                        try:
                            q.put_nowait(item)
                        except queue.Full:          # a viewer too slow: it starts again
                            while not q.empty():
                                q.get_nowait()
                            q.put_nowait(None)
                moof = None

    def run(self):
        while True:
            with self.cond:
                while not self.wanted():
                    self.cond.wait(1)
                enc = self.kind if self.hq else ""
            rfd, wfd = os.pipe()
            p = subprocess.Popen(self.command(enc, wfd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
                                 pass_fds=(wfd,))
            os.close(wfd)
            self.init = None
            mp4 = os.fdopen(rfd, "rb", buffering=0)
            threading.Thread(target=self.read_mp4, args=(mp4,), daemon=True).start()
            buf, t0, n0, bytes0, self.hbytes = bytearray(), time.time(), self.n, 0, 0
            try:
                while self.wanted() and (self.kind if self.hq else "") == enc:     # (another encoder, or none: again)
                    chunk = p.stdout.read(65536)
                    if not chunk:
                        self.error = p.stderr.read().decode(errors="replace").strip()[-300:]
                        break
                    buf += chunk
                    # a frame: from FF D8 to the FF D9 before the next FF D8
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
                        self.hkbps = self.hbytes * 8 / 1000 / (now - t0)
                        t0, n0, bytes0, self.hbytes = now, self.n, 0, 0
            finally:
                p.kill()
                p.wait()
                mp4.close()
                self.init = None
                self.fps = self.kbps = self.hkbps = 0.0
                with self.cond:
                    for q in self.hq:                   # the viewers begin again with the new header
                        while not q.empty():
                            q.get_nowait()
                        q.put_nowait(None)
            time.sleep(0.5)

    def next(self, after, timeout=5):
        """(count, frame) newer than `after`, or (after, None)"""
        with self.cond:
            self.cond.wait_for(lambda: self.n != after, timeout)
            return (self.n, self.frame) if self.n != after else (after, None)


class Sound:
    """the dongle's sound (ALSA) as AAC in fragmented MP4, while somebody listens: the MP4's header,
    its fragments to each listener's queue"""

    def __init__(self, a):
        self.a = a
        self.cond = threading.Condition()
        self.hq = []
        self.init = None
        self.error = ""
        if a.sound:
            threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while True:
            with self.cond:
                while not self.hq:
                    self.cond.wait(1)
            p = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "alsa", "-ac", "2", "-ar", "48000",
                                  "-thread_queue_size", "64", "-i", self.a.sound, "-c:a", "aac", "-b:a", "160k",
                                  "-f", "mp4", "-movflags", "frag_every_frame+empty_moov+default_base_moof", "pipe:1"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
            f = p.stdout
            init, moof = b"", None
            try:
                while self.hq:
                    head = f.read(8)
                    if len(head) < 8:
                        self.error = p.stderr.read().decode(errors="replace").strip()[-300:]
                        break
                    size, kind = struct.unpack(">I4s", head)
                    body = b""
                    while len(body) < size - 8:
                        more = f.read(size - 8 - len(body))
                        if not more:
                            break
                        body += more
                    data = head + body
                    if kind in (b"ftyp", b"moov"):
                        init += data
                        if kind == b"moov":
                            self.init = init
                    elif kind == b"moof":
                        moof = data
                    elif kind == b"mdat" and moof:
                        with self.cond:
                            for q in self.hq:
                                try:
                                    q.put_nowait(moof + data)
                                except queue.Full:
                                    while not q.empty():
                                        q.get_nowait()
                                    q.put_nowait(None)
                        moof = None
            finally:
                p.kill()
                p.wait()
                self.init = None
                with self.cond:
                    for q in self.hq:
                        q.put(None)
            time.sleep(0.5)


def handler(src, snd):
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
            elif path == "/log":                    # what a page could not do, for the journal
                from urllib.parse import unquote
                print("page:", unquote(self.path[5:])[:600], flush=True)
                self.send(200, "text/plain", b"")
            elif path == "/status":
                self.send(200, "application/json", json.dumps(
                    {"fps": src.fps, "kbps": src.kbps, "enc_kbps": src.hkbps, "viewers": src.viewers,
                     "enc": src.kind, "enc_viewers": len(src.hq), "watched": src.wanted(), "error": src.error}).encode())
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
            elif path in ("/h264", "/h265", "/x265"):
                self.close_connection = True
                q = queue.Queue(maxsize=240)
                with src.cond:
                    if src.kind != path[1:]:
                        if src.hq:                  # one encoder at a time: whoever watches has it
                            busy = src.kind
                        else:                       # the encoder changes: its header is not this one's
                            busy = ""
                            src.kind = path[1:]
                            src.init = None
                    else:
                        busy = ""
                    if not busy:
                        src.hq.append(q)
                        src.cond.notify_all()
                if busy:
                    self.send(503, "text/plain", ("somebody is watching %s: one encoder at a time\n" % busy).encode())
                    return
                try:
                    # the header (the encoder may be starting), then from a key frame on
                    t = time.time()
                    while src.init is None:
                        if time.time() - t > 8:
                            self.send(503, "text/plain", ("nothing from the encoder. " + src.error + "\n").encode())
                            return
                        time.sleep(0.05)
                    while not q.empty():
                        q.get_nowait()
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(src.init)
                    started = False
                    while True:
                        item = q.get(timeout=10)
                        if item is None:            # the encoder began again, or this viewer fell behind
                            return
                        key, data = item
                        if started or key:
                            started = True
                            self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError, OSError, queue.Empty):
                    pass
                finally:
                    with src.cond:
                        if q in src.hq:
                            src.hq.remove(q)
                        src.wanted_until = max(src.wanted_until, time.time() + 3)
            elif path == "/audio":
                self.close_connection = True
                if not snd.a.sound:
                    self.send(404, "text/plain", b"no sound device given (--sound)\n")
                    return
                q = queue.Queue(maxsize=400)
                with snd.cond:
                    snd.hq.append(q)
                    snd.cond.notify_all()
                try:
                    t = time.time()
                    while snd.init is None:
                        if time.time() - t > 6:
                            self.send(503, "text/plain", ("no sound from the dongle. " + snd.error + "\n").encode())
                            return
                        time.sleep(0.05)
                    while not q.empty():
                        q.get_nowait()
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/mp4")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(snd.init)
                    while True:
                        data = q.get(timeout=10)
                        if data is None:
                            return
                        self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError, OSError, queue.Empty):
                    pass
                finally:
                    with snd.cond:
                        if q in snd.hq:
                            snd.hq.remove(q)
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
    ap.add_argument("--qp", type=int, default=27, help="H.265's quantiser: lower is better and bigger (22-32)")
    ap.add_argument("--vf", default="format=nv12,hwupload", help="the filter before the GPU's encoder")
    ap.add_argument("--hevc", default="-profile:v main -tier main -level 5.1 -aud 1", help="more of hevc_vaapi's options")
    ap.add_argument("--sound", default="hw:CARD=U15389", help="the dongle's ALSA device (empty: no sound)")
    ap.add_argument("--render", default="/dev/dri/renderD128", help="the GPU's VA-API device")
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), handler(Source(a), Sound(a)))
    srv.daemon_threads = True
    print("capture on http://0.0.0.0:%d/" % a.port, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
