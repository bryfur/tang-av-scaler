idf_component_register(SRCS main.c jtag.c tap.c gowin.c xvc_core.c xvc.c console.c wifi.c web.c logbuf.c scaler.c
                       INCLUDE_DIRS "."
                       PRIV_REQUIRES esp_driver_gpio esp_driver_spi esp_driver_uart esp_driver_usb_serial_jtag
                                     esp_wifi esp_netif esp_event nvs_flash esp_http_server
                                     app_update esp_timer esp_rom soc hal lwip esp_app_format)
target_add_binary_data(${COMPONENT_LIB} "page.html" TEXT)
