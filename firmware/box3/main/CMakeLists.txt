idf_component_register(SRCS "desk_buddy_main.c"
                       PRIV_REQUIRES spi_flash esp-box-3 esp_wifi esp_event esp_netif nvs_flash lwip
                       INCLUDE_DIRS "")
