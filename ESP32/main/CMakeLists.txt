idf_component_register(SRCS "app_main.c" "gateway_config.c" "network.c"
    "chat.c" "alerts.c" "http_api.c"
    INCLUDE_DIRS "."
    REQUIRES esp_eth esp_event esp_netif esp_http_server esp_http_client
             esp_wifi nvs_flash spiffs espressif__cjson espressif__ip101 mbedtls esp_timer
    EMBED_TXTFILES "web/index.html")
