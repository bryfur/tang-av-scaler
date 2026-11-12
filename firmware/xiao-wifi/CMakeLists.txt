# A XIAO ESP32-C5 (or S3) on the AV board (rev C): the FPGA's programmer and console over Wi-Fi.
#   ./build.sh            (on fpga: ESP-IDF 6.x, . ~/esp/env.sh)
cmake_minimum_required(VERSION 3.22)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(avwifi)
