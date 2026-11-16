#!/bin/sh
# tools/android-container/build.sh: build the avandroid image on this host (x86-64, Docker
# with buildx: fpga).  Tags avandroid:YYYYMMDD and avandroid:latest.
set -e
here=$(cd "$(dirname "$0")" && pwd)
tag=avandroid:$(date +%Y%m%d)
docker buildx build --load \
    --build-arg USER="$(id -un)" --build-arg UID="$(id -u)" --build-arg GID="$(id -g)" \
    -t "$tag" -t avandroid:latest "$here"
echo "built $tag (= avandroid:latest)"
