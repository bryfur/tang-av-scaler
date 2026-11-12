#!/bin/bash
# cap.sh [OUT.png] [FRAMES]: a frame of the HDMI output as a USB capture dongle sees it.  If the
# capture page's service has the dongle (tools/capview, port 8090): its newest frame (the dongle's
# own JPEG); else straight from /dev/video0, raw 1080p (the FRAMESth frame, default 20: the first
# ones after opening are stale).
out=${1:-/tmp/cap.png}
if [ "$(curl -s -m 2 http://localhost:8090/status | grep -c '"watched": true')" = 1 ]; then
    curl -s -m 8 -o "$out.jpg" http://localhost:8090/snapshot.jpg && exec ffmpeg -hide_banner -loglevel error -y -i "$out.jpg" "$out"
fi
exec ffmpeg -hide_banner -loglevel error -y -f v4l2 -input_format yuyv422 -video_size 1920x1080 \
    -i "${CAP_DEV:-/dev/video0}" -frames:v "${2:-20}" -update 1 "$out"
