idf_component_register(SRCS main.c jtag.c tap.c gowin.c xvc_core.c xvc.c console.c wifi.c web.c logbuf.c scaler.c link.c tables.c
                       INCLUDE_DIRS "." "../../../gateware/sw"
                       PRIV_REQUIRES esp_driver_gpio esp_driver_spi esp_driver_uart esp_driver_usb_serial_jtag
                                     esp_wifi esp_netif esp_event nvs_flash esp_http_server
                                     app_update esp_timer esp_rom soc hal lwip esp_app_format spi_flash)
# (main.c: a crash's place kept for the next start)
target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=esp_panic_handler")
target_add_binary_data(${COMPONENT_LIB} "page.html" TEXT)
# the scaler's CPU's program (gateware/sw: make): the link gives it to the CPU if the bitstream's is older
target_add_binary_data(${COMPONENT_LIB} "../../../gateware/sw/build/cpu.bin" BINARY)
# the scaler's learnt tables (tables.c: the CPU is given them)
target_add_binary_data(${COMPONENT_LIB} "../../../gateware/tables/learnt-plain.tab" BINARY)
target_add_binary_data(${COMPONENT_LIB} "../../../gateware/tables/learnt-aa12.tab" BINARY)
