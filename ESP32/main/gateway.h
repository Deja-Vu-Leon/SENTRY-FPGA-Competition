#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "esp_http_server.h"
#include "cJSON.h"

#define GW_ID_MAX 48
#define GW_PROMPT_MAX 4096
#define GW_ANSWER_MAX 16384
#define GW_IMAGE_MAX (2 * 1024 * 1024)
#define GW_JSON_MAX 8192
#define GW_ROOT "/alerts"

typedef struct {
    char wifi_ssid[33];
    char wifi_password[65];
    char api_key[256];
    char model[80];
    char token[129];
    char ap_password[65];
} gateway_config_t;

void config_init(void);
void config_read(gateway_config_t *out);
esp_err_t config_update(const cJSON *json, char *error, size_t capacity);
bool gateway_id_valid(const char *id);
bool gateway_text_valid(const char *text, size_t max_length);
void network_start(void);
cJSON *network_status(void);
bool network_online(void);
void chat_start(void);
int chat_submit(const cJSON *request, cJSON **out);
cJSON *chat_result(const char *id);
esp_err_t alerts_init(void);
int alerts_save(const cJSON *request, cJSON **out);
cJSON *alerts_list(void);
int alerts_image_upload(httpd_req_t *req, const char *id);
esp_err_t alerts_image_send(httpd_req_t *req, const char *id);
void http_start(void);
esp_err_t json_send(httpd_req_t *req, int code, cJSON *body);
esp_err_t api_error(httpd_req_t *req, int code, const char *reason);
