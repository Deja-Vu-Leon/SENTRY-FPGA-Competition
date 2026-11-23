#include "gateway.h"
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_system.h"

extern const char page_start[] asm("_binary_index_html_start");
extern const char page_end[] asm("_binary_index_html_end");
static TaskHandle_t restart_task;

static const char *status_text(int code)
{
    switch (code) {
    case 200: return "200 OK";
    case 201: return "201 Created";
    case 202: return "202 Accepted";
    case 400: return "400 Bad Request";
    case 401: return "401 Unauthorized";
    case 404: return "404 Not Found";
    case 409: return "409 Conflict";
    case 413: return "413 Payload Too Large";
    case 415: return "415 Unsupported Media Type";
    case 429: return "429 Too Many Requests";
    case 503: return "503 Service Unavailable";
    case 507: return "507 Insufficient Storage";
    default: return "500 Internal Server Error";
    }
}

esp_err_t json_send(httpd_req_t *req, int code, cJSON *body)
{
    char *payload = body ? cJSON_PrintUnformatted(body) : NULL;
    cJSON_Delete(body);
    if (!payload) return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "out_of_memory");
    httpd_resp_set_status(req, status_text(code));
    httpd_resp_set_type(req, "application/json; charset=utf-8");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    httpd_resp_set_hdr(req, "X-Content-Type-Options", "nosniff");
    esp_err_t result = httpd_resp_sendstr(req, payload);
    free(payload);
    return result;
}

esp_err_t api_error(httpd_req_t *req, int code, const char *reason)
{
    cJSON *body = cJSON_CreateObject();
    cJSON_AddStringToObject(body, "error", reason);
    /* A rejected or incomplete upload cannot be reused as the next HTTP request. */
    if (req->content_len) httpd_resp_set_hdr(req, "Connection", "close");
    esp_err_t status = json_send(req, code, body);
    return req->content_len ? ESP_FAIL : status;
}

static bool authorized(httpd_req_t *req)
{
    gateway_config_t settings;
    config_read(&settings);
    char authorization[160], expected[160];
    if (!settings.token[0] || httpd_req_get_hdr_value_str(req, "Authorization", authorization, sizeof(authorization)) != ESP_OK)
        return false;
    snprintf(expected, sizeof(expected), "Bearer %s", settings.token);
    if (strlen(expected) != strlen(authorization)) return false;
    unsigned diff = 0;
    for (size_t i = 0; i < strlen(expected); i++) diff |= expected[i] ^ authorization[i];
    return diff == 0;
}

static cJSON *receive_json(httpd_req_t *req)
{
    if (!req->content_len || req->content_len > GW_JSON_MAX) return NULL;
    char *buffer = calloc(1, req->content_len + 1);
    if (!buffer) return NULL;
    size_t used = 0;
    int timeouts = 0;
    while (used < req->content_len) {
        int n = httpd_req_recv(req, buffer + used, req->content_len - used);
        if (n == HTTPD_SOCK_ERR_TIMEOUT && timeouts++ < 3) continue;
        if (n <= 0) { free(buffer); return NULL; }
        used += n;
    }
    const char *end;
    cJSON *value = cJSON_ParseWithLengthOpts(buffer, used + 1, &end, true);
    if (!cJSON_IsObject(value)) { cJSON_Delete(value); value = NULL; }
    free(buffer);
    return value;
}

static esp_err_t home(httpd_req_t *req)
{
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    httpd_resp_set_hdr(req, "Cache-Control", "no-cache");
    httpd_resp_set_hdr(req, "X-Content-Type-Options", "nosniff");
    return httpd_resp_send(req, page_start, page_end - page_start - 1);
}

static esp_err_t api(httpd_req_t *req)
{
    if (!authorized(req)) return api_error(req, 401, "access_token_required");
    if (!strcmp(req->uri, "/v1/status") && req->method == HTTP_GET) return json_send(req, 200, network_status());
    if (!strcmp(req->uri, "/v1/alerts") && req->method == HTTP_GET) return json_send(req, 200, alerts_list());
    if (!strncmp(req->uri, "/v1/chat/", 9) && req->method == HTTP_GET) {
        const char *id = req->uri + 9;
        if (!gateway_id_valid(id)) return api_error(req, 400, "invalid_request_id");
        cJSON *result = chat_result(id);
        return result ? json_send(req, 200, result) : api_error(req, 404, "request_not_found");
    }
    if (!strncmp(req->uri, "/v1/alerts/", 11)) {
        const char *start = req->uri + 11, *suffix = strstr(start, "/image");
        if (!suffix || strcmp(suffix, "/image") || suffix - start > GW_ID_MAX) return api_error(req, 400, "invalid_event_path");
        char id[GW_ID_MAX + 1];
        memcpy(id, start, suffix - start);
        id[suffix - start] = 0;
        if (!gateway_id_valid(id)) return api_error(req, 400, "invalid_event_id");
        if (req->method == HTTP_GET) return alerts_image_send(req, id);
        if (req->method == HTTP_PUT) {
            int code = alerts_image_upload(req, id);
            if (code != 201) return api_error(req, code, code == 409 ? "image_already_stored" : "image_upload_failed");
            cJSON *reply = cJSON_CreateObject();
            cJSON_AddStringToObject(reply, "event_id", id);
            cJSON_AddBoolToObject(reply, "has_image", true);
            return json_send(req, code, reply);
        }
    }
    if (req->method != HTTP_POST) return api_error(req, 404, "endpoint_not_found");
    if (strcmp(req->uri, "/v1/chat") && strcmp(req->uri, "/v1/alerts") &&
        strcmp(req->uri, "/v1/settings") && strcmp(req->uri, "/v1/restart")) return api_error(req, 404, "endpoint_not_found");
    cJSON *body = receive_json(req);
    if (!body) return api_error(req, req->content_len > GW_JSON_MAX ? 413 : 400, "invalid_json_body");
    cJSON *reply = NULL;
    int code = 200;
    if (!strcmp(req->uri, "/v1/chat")) code = chat_submit(body, &reply);
    if (!strcmp(req->uri, "/v1/alerts")) code = alerts_save(body, &reply);
    if (!strcmp(req->uri, "/v1/settings")) {
        char error[128] = "";
        esp_err_t result = config_update(body, error, sizeof(error));
        cJSON_Delete(body);
        if (result != ESP_OK) return api_error(req, result == ESP_ERR_INVALID_ARG ? 400 : 507, error);
        reply = cJSON_CreateObject();
        cJSON_AddBoolToObject(reply, "saved", true);
        cJSON_AddBoolToObject(reply, "restart_for_wifi", true);
        return json_send(req, 200, reply);
    }
    if (!strcmp(req->uri, "/v1/restart")) {
        xTaskNotifyGive(restart_task);
        reply = cJSON_CreateObject();
        cJSON_AddBoolToObject(reply, "restarting", true);
    }
    cJSON_Delete(body);
    if (reply) return json_send(req, code, reply);
    const char *error = code == 409 ? "id_conflict" : code == 429 ? "chat_queue_full" :
                        code == 507 ? "storage_full" : "invalid_request";
    return api_error(req, code, error);
}

static void restart_worker(void *arg)
{
    (void)arg;
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    vTaskDelay(pdMS_TO_TICKS(1500));
    esp_restart();
}

void http_start(void)
{
    configASSERT(xTaskCreate(restart_worker, "restart", 2048, NULL, 2, &restart_task) == pdPASS);
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.stack_size = 10240;
    config.max_uri_handlers = 4;
    config.max_open_sockets = 7;
    config.lru_purge_enable = true;
    config.recv_wait_timeout = 4;
    config.send_wait_timeout = 4;
    config.uri_match_fn = httpd_uri_match_wildcard;
    httpd_handle_t server;
    ESP_ERROR_CHECK(httpd_start(&server, &config));
    const httpd_uri_t routes[] = {
        {.uri = "/", .method = HTTP_GET, .handler = home},
        {.uri = "/v1/*", .method = HTTP_GET, .handler = api},
        {.uri = "/v1/*", .method = HTTP_POST, .handler = api},
        {.uri = "/v1/*", .method = HTTP_PUT, .handler = api},
    };
    for (size_t i = 0; i < sizeof(routes) / sizeof(routes[0]); i++)
        ESP_ERROR_CHECK(httpd_register_uri_handler(server, &routes[i]));
}
