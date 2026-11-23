#include "gateway.h"
#include <ctype.h>
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "nvs.h"

static gateway_config_t settings;
static SemaphoreHandle_t lock;

bool gateway_id_valid(const char *id)
{
    if (!id || !*id || strlen(id) > GW_ID_MAX) return false;
    for (const unsigned char *p = (const unsigned char *)id; *p; ++p)
        if (!isalnum(*p) && *p != '-' && *p != '_') return false;
    return true;
}

bool gateway_text_valid(const char *text, size_t max_length)
{
    return text && *text && strlen(text) <= max_length;
}

static bool wifi_password_valid(const char *value, bool allow_open)
{
    size_t length = strlen(value);
    if (!length) return allow_open;
    if (length >= 8 && length <= 63) return true;
    if (length != 64) return false;
    for (size_t i = 0; i < length; i++) if (!isxdigit((unsigned char)value[i])) return false;
    return true;
}

void config_init(void)
{
    lock = xSemaphoreCreateMutex();
    configASSERT(lock);
    strlcpy(settings.wifi_ssid, CONFIG_SENTRY_WIFI_SSID, sizeof(settings.wifi_ssid));
    strlcpy(settings.wifi_password, CONFIG_SENTRY_WIFI_PASSWORD, sizeof(settings.wifi_password));
    strlcpy(settings.model, CONFIG_SENTRY_DEEPSEEK_MODEL, sizeof(settings.model));
    strlcpy(settings.token, CONFIG_SENTRY_API_TOKEN, sizeof(settings.token));
    strlcpy(settings.ap_password, CONFIG_SENTRY_AP_PASSWORD, sizeof(settings.ap_password));
    nvs_handle_t handle;
    if (nvs_open("sentry", NVS_READONLY, &handle) == ESP_OK) {
        gateway_config_t saved;
        size_t size = sizeof(saved);
        if (nvs_get_blob(handle, "settings", &saved, &size) == ESP_OK && size == sizeof(saved)) {
            saved.wifi_ssid[32] = 0;
            saved.wifi_password[64] = 0;
            saved.api_key[255] = 0;
            saved.model[79] = 0;
            saved.token[128] = 0;
            saved.ap_password[64] = 0;
            settings = saved;
        }
        nvs_close(handle);
    }
}

void config_read(gateway_config_t *out)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    *out = settings;
    xSemaphoreGive(lock);
}

esp_err_t config_update(const cJSON *json, char *error, size_t capacity)
{
    if (!cJSON_IsObject(json)) return ESP_ERR_INVALID_ARG;
    xSemaphoreTake(lock, portMAX_DELAY);
    gateway_config_t next = settings;
    struct field { const char *name; char *data; size_t size; size_t minimum; } fields[] = {
        {"wifi_ssid", next.wifi_ssid, sizeof(next.wifi_ssid), 0},
        {"wifi_password", next.wifi_password, sizeof(next.wifi_password), 0},
        {"deepseek_api_key", next.api_key, sizeof(next.api_key), 0},
        {"model", next.model, sizeof(next.model), 1},
        {"access_token", next.token, sizeof(next.token), 12},
        {"ap_password", next.ap_password, sizeof(next.ap_password), 0},
    };
    esp_err_t result = ESP_OK;
    for (size_t i = 0; i < sizeof(fields) / sizeof(fields[0]); ++i) {
        cJSON *value = cJSON_GetObjectItemCaseSensitive(json, fields[i].name);
        if (!value) continue;
        if (!cJSON_IsString(value) || strlen(value->valuestring) < fields[i].minimum ||
            strlen(value->valuestring) >= fields[i].size) {
            snprintf(error, capacity, "invalid %s", fields[i].name);
            result = ESP_ERR_INVALID_ARG;
            break;
        }
        strlcpy(fields[i].data, value->valuestring, fields[i].size);
    }
    if (result == ESP_OK && (!wifi_password_valid(next.wifi_password, true) ||
                            !wifi_password_valid(next.ap_password, true) ||
                            strlen(next.ap_password) > 63)) {
        strlcpy(error, "Invalid Wi-Fi password; AP needs 8-63 characters or empty to disable", capacity);
        result = ESP_ERR_INVALID_ARG;
    }
    if (result == ESP_OK && strpbrk(next.api_key, "\r\n")) {
        strlcpy(error, "invalid deepseek_api_key", capacity);
        result = ESP_ERR_INVALID_ARG;
    }
    if (result == ESP_OK) {
        nvs_handle_t handle;
        result = nvs_open("sentry", NVS_READWRITE, &handle);
        if (result == ESP_OK) {
            result = nvs_set_blob(handle, "settings", &next, sizeof(next));
            if (result == ESP_OK) result = nvs_commit(handle);
            nvs_close(handle);
        }
        if (result == ESP_OK) settings = next;
        else strlcpy(error, "settings write failed", capacity);
    }
    xSemaphoreGive(lock);
    return result;
}
