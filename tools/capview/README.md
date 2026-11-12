# capview: a USB capture dongle on a web page

`capview.py` serves the dongle's picture at `http://<host>:8090/`: the dongle's own Motion-JPEG
frames passed on untouched (about a tenth of a second behind HDMI on the local network; 1080p at
30 frames a second on a USB 2 port, 60 on USB 3). The device is opened only while somebody watches.
`/snapshot.jpg` is the newest frame, `/status` the rate.

The page's second way: **H.265**, encoded by the GPU (VA-API `hevc_vaapi`, constant quantiser
`--qp`, 27: about 5 Mbit/s for a game's picture where the Motion-JPEG is 34), sent as fragmented
MP4 a frame a fragment and played through Media Source Extensions: for browsers that play HEVC
(the page says so if not and stays with Motion-JPEG). The encoder runs only while somebody
watches that way.

As a service of the user's (it starts at boot if lingering is on):

    cp capview.service ~/.config/systemd/user/ && systemctl --user enable --now capview

It needs Python 3 and ffmpeg (for H.265 a GPU with VA-API HEVC encoding at `/dev/dri/renderD128`:
`--render`), nothing else. No sound.
