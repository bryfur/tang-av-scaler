# The XIAO ESP32-S3 on the AV board (rev C): the FPGA's programmer and console.
#   . ~/esp/env.sh && idf.py build        (ESP-IDF 6.x)
cmake_minimum_required(VERSION 3.22)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(avxiao)
