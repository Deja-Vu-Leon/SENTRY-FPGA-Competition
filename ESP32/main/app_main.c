#include "gateway.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "nvs_flash.h"

void app_main(void)
{
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    config_init();
    ESP_ERROR_CHECK(alerts_init());
    chat_start();
    network_start();
    http_start();
    ESP_LOGI("sentry", "Gateway ready; Ethernet address is " CONFIG_SENTRY_ETH_IP);
}
