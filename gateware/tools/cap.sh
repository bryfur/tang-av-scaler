#!/bin/bash
# cap.sh [OUT.png] [FRAMES]: a frame of the HDMI output as a USB capture dongle sees it (/dev/video0,
# raw 1080p; the FRAMESth frame, default 20: the first ones after opening are stale).
out=${1:-/tmp/cap.png}
exec ffmpeg -hide_banner -loglevel error -y -f v4l2 -input_format yuyv422 -video_size 1920x1080 \
    -i "${CAP_DEV:-/dev/video0}" -frames:v "${2:-20}" -update 1 "$out"
