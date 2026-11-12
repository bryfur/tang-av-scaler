# capview: a USB capture dongle on a web page

`capview.py` serves the dongle's picture at `http://<host>:8090/`: the dongle's own Motion-JPEG
frames passed on untouched (about a tenth of a second behind HDMI on the local network; 1080p at
30 frames a second on a USB 2 port, 60 on USB 3). The device is opened only while somebody watches.
`/snapshot.jpg` is the newest frame, `/status` the rate.

The page's other ways, encoded by the GPU (VA-API, constant quantiser `--qp`) and sent as
fragmented MP4, a frame a fragment, played through Media Source Extensions: **H.264** and
**H.265** (about 5 Mbit/s for a game's picture where the Motion-JPEG is 34). This AMD GPU's H.265
decodes in ffmpeg but Apple's decoder refuses it (Chrome on a Mac: VideoToolbox -12909, whatever
the level, colour range, size, quantiser or slices tried): H.264 there; or **H.265 in software**
(x265: plays on the Mac, six processor cores). One encoder at a time: whoever watches has it. The
page tells the service what its player made of the stream (`journalctl --user -u capview`).

As a service of the user's (it starts at boot if lingering is on):

    cp capview.service ~/.config/systemd/user/ && systemctl --user enable --now capview

**Sound**: the page's switch plays the dongle's audio (ALSA `--sound`, AAC) beside whichever picture.

It needs Python 3 and ffmpeg (for H.265 a GPU with VA-API HEVC encoding at `/dev/dri/renderD128`:
`--render`), nothing else.
