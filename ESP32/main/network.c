#include "gateway.h"
#include <stdatomic.h>
#include <string.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_eth.h"
#include "esp_eth_mac_esp.h"
#include "esp_eth_phy.h"
#include "esp_eth_phy_ip101.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"

static const char *TAG = "network";
static esp_netif_t *ethernet, *station, *access_point;
static atomic_bool online, ethernet_up;
static atomic_int reconnect_attempt;
static TaskHandle_t reconnect_task;

static void reconnect(void *unused)
{
    (void)unused;
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        int shift = atomic_load(&reconnect_attempt);
        vTaskDelay(pdMS_TO_TICKS(1000 * (1 << (shift > 5 ? 5 : shift))));
        if (!atomic_load(&online)) {
            atomic_fetch_add(&reconnect_attempt, 1);
            esp_err_t result = esp_wifi_connect();
            if (result != ESP_OK) xTaskNotifyGive(reconnect_task);
        }
    }
}

static void event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) esp_wifi_connect();
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        atomic_store(&online, false);
        xTaskNotifyGive(reconnect_task);
    }
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *got = data;
        atomic_store(&online, true);
        atomic_store(&reconnect_attempt, 0);
        esp_netif_set_default_netif(station);
        ESP_LOGI(TAG, "Wi-Fi internet address " IPSTR, IP2STR(&got->ip_info.ip));
    }
    if (base == ETH_EVENT) {
        if (id == ETHERNET_EVENT_CONNECTED) atomic_store(&ethernet_up, true);
        if (id == ETHERNET_EVENT_DISCONNECTED) atomic_store(&ethernet_up, false);
    }
}

static void start_ethernet(void)
{
    esp_netif_inherent_config_t base = ESP_NETIF_INHERENT_DEFAULT_ETH();
    base.route_prio = 10;
    esp_netif_config_t netif_config = {.base = &base, .stack = ESP_NETIF_NETSTACK_DEFAULT_ETH};
    ethernet = esp_netif_new(&netif_config);
    configASSERT(ethernet);
    ESP_ERROR_CHECK(esp_netif_dhcpc_stop(ethernet));
    esp_netif_ip_info_t address = {0};
    configASSERT(inet_pton(AF_INET, CONFIG_SENTRY_ETH_IP, &address.ip) == 1);
    inet_pton(AF_INET, "255.255.255.0", &address.netmask);
    ESP_ERROR_CHECK(esp_netif_set_ip_info(ethernet, &address));
    eth_mac_config_t mac_config = ETH_MAC_DEFAULT_CONFIG();
    eth_esp32_emac_config_t config = ETH_ESP32_EMAC_DEFAULT_CONFIG();
    config.smi_gpio.mdc_num = CONFIG_SENTRY_ETH_MDC;
    config.smi_gpio.mdio_num = CONFIG_SENTRY_ETH_MDIO;
    config.clock_config.rmii.clock_gpio = CONFIG_SENTRY_ETH_CLOCK;
#if CONFIG_SENTRY_ETH_CLOCK_OUT
    config.clock_config.rmii.clock_mode = EMAC_CLK_OUT;
#else
    config.clock_config.rmii.clock_mode = EMAC_CLK_EXT_IN;
#endif
    config.emac_dataif_gpio.rmii.tx_en_num = CONFIG_SENTRY_ETH_TX_EN;
    config.emac_dataif_gpio.rmii.txd0_num = CONFIG_SENTRY_ETH_TXD0;
    config.emac_dataif_gpio.rmii.txd1_num = CONFIG_SENTRY_ETH_TXD1;
    config.emac_dataif_gpio.rmii.crs_dv_num = CONFIG_SENTRY_ETH_CRS;
    config.emac_dataif_gpio.rmii.rxd0_num = CONFIG_SENTRY_ETH_RXD0;
    config.emac_dataif_gpio.rmii.rxd1_num = CONFIG_SENTRY_ETH_RXD1;
    esp_eth_mac_t *mac = esp_eth_mac_new_esp32(&config, &mac_config);
    eth_phy_config_t phy_config = ETH_PHY_DEFAULT_CONFIG();
    phy_config.phy_addr = CONFIG_SENTRY_ETH_PHY_ADDR;
    phy_config.reset_gpio_num = CONFIG_SENTRY_ETH_RESET;
#if CONFIG_SENTRY_PHY_GENERIC
    esp_eth_phy_t *phy = esp_eth_phy_new_generic(&phy_config);
#else
    esp_eth_phy_t *phy = esp_eth_phy_new_ip101(&phy_config);
#endif
    configASSERT(mac && phy);
    esp_eth_config_t driver = ETH_DEFAULT_CONFIG(mac, phy);
    esp_eth_handle_t handle = NULL;
    ESP_ERROR_CHECK(esp_eth_driver_install(&driver, &handle));
    ESP_ERROR_CHECK(esp_netif_attach(ethernet, esp_eth_new_netif_glue(handle)));
    ESP_ERROR_CHECK(esp_eth_start(handle));
}

static void start_wifi(void)
{
    gateway_config_t config;
    config_read(&config);
    station = esp_netif_create_default_wifi_sta();
    access_point = esp_netif_create_default_wifi_ap();
    configASSERT(station && access_point);
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    wifi_config_t ap = {0}, sta = {0};
    strlcpy((char *)ap.ap.ssid, "SENTRY-Gateway", sizeof(ap.ap.ssid));
    ap.ap.ssid_len = strlen((char *)ap.ap.ssid);
    memcpy(ap.ap.password, config.ap_password, strnlen(config.ap_password, sizeof(ap.ap.password)));
    ap.ap.authmode = WIFI_AUTH_WPA2_PSK;
    ap.ap.max_connection = 4;
    ap.ap.channel = 6;
    memcpy(sta.sta.ssid, config.wifi_ssid, strnlen(config.wifi_ssid, sizeof(sta.sta.ssid)));
    memcpy(sta.sta.password, config.wifi_password, strnlen(config.wifi_password, sizeof(sta.sta.password)));
    sta.sta.pmf_cfg.capable = true;
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(config.wifi_ssid[0] ? WIFI_MODE_APSTA : WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap));
    if (config.wifi_ssid[0]) ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_LOGI(TAG, "Phone access point SENTRY-Gateway, http://192.168.4.1");
}

void network_start(void)
{
    configASSERT(xTaskCreate(reconnect, "wifi-reconnect", 3072, NULL, 3, &reconnect_task) == pdPASS);
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(ETH_EVENT, ESP_EVENT_ANY_ID, event, NULL));
    start_ethernet();
    start_wifi();
    esp_sntp_config_t sntp = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
    sntp.start = false;
    sntp.server_from_dhcp = false;
    ESP_ERROR_CHECK(esp_netif_sntp_init(&sntp));
    ESP_ERROR_CHECK(esp_netif_sntp_start());
}

bool network_online(void)
{
    return atomic_load(&online);
}

static void add_address(cJSON *json, const char *key, esp_netif_t *netif)
{
    esp_netif_ip_info_t ip;
    char text[16] = "";
    if (netif && esp_netif_get_ip_info(netif, &ip) == ESP_OK)
        snprintf(text, sizeof(text), IPSTR, IP2STR(&ip.ip));
    cJSON_AddStringToObject(json, key, text);
}

cJSON *network_status(void)
{
    cJSON *json = cJSON_CreateObject();
    cJSON_AddStringToObject(json, "device", "SENTRY Waveshare ESP32-P4-NANO");
    cJSON_AddBoolToObject(json, "ethernet_link", atomic_load(&ethernet_up));
    cJSON_AddBoolToObject(json, "wifi_online", network_online());
    cJSON_AddBoolToObject(json, "clock_ready", time(NULL) > 1700000000);
    cJSON_AddNumberToObject(json, "uptime_seconds", esp_timer_get_time() / 1000000);
    add_address(json, "ethernet_ip", ethernet);
    add_address(json, "wifi_ip", station);
    add_address(json, "ap_ip", access_point);
    gateway_config_t config;
    config_read(&config);
    cJSON_AddBoolToObject(json, "api_key_configured", config.api_key[0] != 0);
    cJSON_AddStringToObject(json, "model", config.model);
    return json;
}
