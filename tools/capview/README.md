# capview: a USB capture dongle on a web page

`capview.py` serves the dongle's picture at `http://<host>:8090/`: the dongle's own Motion-JPEG
frames passed on untouched (about a tenth of a second behind HDMI on the local network; 1080p at
30 frames a second on a USB 2 port, 60 on USB 3). The device is opened only while somebody watches.
`/snapshot.jpg` is the newest frame, `/status` the rate.

As a service of the user's (it starts at boot if lingering is on):

    cp capview.service ~/.config/systemd/user/ && systemctl --user enable --now capview

It needs Python 3 and ffmpeg, nothing else. No sound.
