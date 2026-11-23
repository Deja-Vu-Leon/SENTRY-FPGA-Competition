#include "gateway.h"
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "esp_spiffs.h"
#include "nvs.h"

static SemaphoreHandle_t lock;
static uint32_t next_sequence;

static void file_path(char *out, size_t capacity, const char *id, const char *extension)
{
    snprintf(out, capacity, GW_ROOT "/%s.%s", id, extension);
}

static cJSON *load_record(const char *id)
{
    char path[96];
    file_path(path, sizeof(path), id, "json");
    FILE *file = fopen(path, "rb");
    if (!file) return NULL;
    char *data = calloc(1, GW_JSON_MAX + 1);
    if (!data) { fclose(file); return NULL; }
    size_t length = fread(data, 1, GW_JSON_MAX, file);
    bool valid = !ferror(file) && feof(file);
    fclose(file);
    cJSON *record = valid ? cJSON_ParseWithLength(data, length) : NULL;
    free(data);
    return record;
}

static bool record_id(const char *name, char *id)
{
    size_t length = strlen(name);
    if (length < 6 || length - 5 > GW_ID_MAX || strcmp(name + length - 5, ".json")) return false;
    memcpy(id, name, length - 5);
    id[length - 5] = 0;
    return gateway_id_valid(id);
}

static void delete_record(const char *id)
{
    char path[96];
    file_path(path, sizeof(path), id, "json");
    unlink(path); /* Removing the catalog first keeps any interrupted prune invisible. */
    file_path(path, sizeof(path), id, "jpg");
    unlink(path);
}

static int count_records(char *oldest_id, const char *protected_id)
{
    DIR *directory = opendir(GW_ROOT);
    if (!directory) return -1;
    struct dirent *entry;
    int count = 0;
    uint32_t oldest = UINT32_MAX;
    oldest_id[0] = 0;
    while ((entry = readdir(directory))) {
        char id[GW_ID_MAX + 1];
        if (!record_id(entry->d_name, id)) continue;
        cJSON *record = load_record(id);
        cJSON *number = cJSON_GetObjectItemCaseSensitive(record, "sequence");
        if (cJSON_IsNumber(number)) {
            count++;
            if (strcmp(id, protected_id) && number->valuedouble < oldest) {
                oldest = number->valuedouble;
                strlcpy(oldest_id, id, GW_ID_MAX + 1);
            }
        }
        cJSON_Delete(record);
    }
    closedir(directory);
    return count;
}

static bool reserve_space(size_t bytes, const char *protected_id, bool new_record)
{
    for (;;) {
        size_t total, used;
        if (esp_spiffs_info("alerts", &total, &used) != ESP_OK) return false;
        char oldest[GW_ID_MAX + 1];
        int count = count_records(oldest, protected_id);
        if (count < 0) return false;
        if ((size_t)used + bytes + 32768 < total * 3 / 4 &&
            count + (new_record ? 1 : 0) <= CONFIG_SENTRY_ALERT_LIMIT) return true;
        if (!oldest[0]) return false;
        delete_record(oldest);
    }
}

static bool image_exists(const char *id)
{
    char path[96];
    struct stat info;
    file_path(path, sizeof(path), id, "jpg");
    return stat(path, &info) == 0 && info.st_size >= 4;
}

esp_err_t alerts_init(void)
{
    lock = xSemaphoreCreateMutex();
    if (!lock) return ESP_ERR_NO_MEM;
    nvs_handle_t nvs;
    esp_err_t result = nvs_open("archive", NVS_READWRITE, &nvs);
    if (result != ESP_OK) return result;
    uint8_t initialized = 0;
    nvs_get_u8(nvs, "initialized", &initialized);
    esp_vfs_spiffs_conf_t config = {
        .base_path = GW_ROOT, .partition_label = "alerts", .max_files = 6,
        .format_if_mount_failed = !initialized,
    };
    result = esp_vfs_spiffs_register(&config);
    if (result == ESP_OK) result = nvs_set_u8(nvs, "initialized", 1);
    if (result == ESP_OK) result = nvs_commit(nvs);
    nvs_close(nvs);
    if (result != ESP_OK) return result;
    DIR *directory = opendir(GW_ROOT);
    if (!directory) return ESP_FAIL;
    struct dirent *entry;
    while ((entry = readdir(directory))) {
        char id[GW_ID_MAX + 1];
        size_t length = strlen(entry->d_name);
        if (length > 4 && !strcmp(entry->d_name + length - 4, ".tmp")) {
            char path[128];
            snprintf(path, sizeof(path), GW_ROOT "/%.90s", entry->d_name);
            unlink(path);
        }
        if (length > 4 && !strcmp(entry->d_name + length - 4, ".jpg")) {
            if (length - 4 > GW_ID_MAX) continue;
            memcpy(id, entry->d_name, length - 4);
            id[length - 4] = 0;
            cJSON *record = gateway_id_valid(id) ? load_record(id) : NULL;
            if (!record && gateway_id_valid(id)) delete_record(id);
            cJSON_Delete(record);
        }
        if (!record_id(entry->d_name, id)) continue;
        cJSON *record = load_record(id);
        cJSON *sequence = cJSON_GetObjectItemCaseSensitive(record, "sequence");
        if (cJSON_IsNumber(sequence) && sequence->valuedouble >= next_sequence)
            next_sequence = sequence->valuedouble + 1;
        cJSON_Delete(record);
    }
    closedir(directory);
    return ESP_OK;
}

int alerts_save(const cJSON *request, cJSON **out)
{
    const cJSON *id = cJSON_GetObjectItemCaseSensitive(request, "event_id");
    const cJSON *camera = cJSON_GetObjectItemCaseSensitive(request, "camera");
    const cJSON *reason = cJSON_GetObjectItemCaseSensitive(request, "reason");
    const cJSON *time = cJSON_GetObjectItemCaseSensitive(request, "event_time");
    const cJSON *confidence = cJSON_GetObjectItemCaseSensitive(request, "confidence");
    if (!cJSON_IsString(id) || !gateway_id_valid(id->valuestring) ||
        !cJSON_IsString(camera) || !gateway_text_valid(camera->valuestring, 24) ||
        !cJSON_IsString(reason) || !gateway_text_valid(reason->valuestring, 512) ||
        !cJSON_IsString(time) || !gateway_text_valid(time->valuestring, 64) ||
        (confidence && !cJSON_IsNull(confidence) &&
         (!cJSON_IsNumber(confidence) || confidence->valuedouble < 0 || confidence->valuedouble > 1))) return 400;
    xSemaphoreTake(lock, portMAX_DELAY);
    cJSON *record = load_record(id->valuestring);
    if (record) {
        bool same = true;
        const char *keys[] = {"camera", "reason", "event_time", "confidence"};
        for (size_t i = 0; i < sizeof(keys) / sizeof(keys[0]); i++) {
            const cJSON *left = cJSON_GetObjectItemCaseSensitive(record, keys[i]);
            const cJSON *right = cJSON_GetObjectItemCaseSensitive(request, keys[i]);
            if ((left || right) && !cJSON_Compare(left, right, true)) same = false;
        }
        int code = same ? 200 : 409;
        if (same) *out = record;
        else cJSON_Delete(record);
        xSemaphoreGive(lock);
        return code;
    }
    record = cJSON_Duplicate(request, true);
    if (!record) { xSemaphoreGive(lock); return 503; }
    cJSON_DeleteItemFromObjectCaseSensitive(record, "sequence");
    cJSON_DeleteItemFromObjectCaseSensitive(record, "has_image");
    cJSON_AddNumberToObject(record, "sequence", next_sequence);
    char *payload = cJSON_PrintUnformatted(record);
    int code = 507;
    if (payload && reserve_space(strlen(payload), id->valuestring, true)) {
        char path[96], temporary[96];
        file_path(path, sizeof(path), id->valuestring, "json");
        file_path(temporary, sizeof(temporary), id->valuestring, "tmp");
        FILE *file = fopen(temporary, "wb");
        if (file) {
            bool ok = fwrite(payload, 1, strlen(payload), file) == strlen(payload);
            if (fclose(file)) ok = false;
            if (ok && rename(temporary, path) == 0) {
                next_sequence++;
                code = 201;
                *out = record;
                record = NULL;
            } else unlink(temporary);
        }
    }
    free(payload);
    cJSON_Delete(record);
    xSemaphoreGive(lock);
    return code;
}

static int newest_first(const void *a, const void *b)
{
    const cJSON *left = *(cJSON *const *)a, *right = *(cJSON *const *)b;
    double l = cJSON_GetObjectItemCaseSensitive(left, "sequence")->valuedouble;
    double r = cJSON_GetObjectItemCaseSensitive(right, "sequence")->valuedouble;
    return l < r ? 1 : l > r ? -1 : 0;
}

cJSON *alerts_list(void)
{
    cJSON *records[CONFIG_SENTRY_ALERT_LIMIT];
    unsigned count = 0;
    xSemaphoreTake(lock, portMAX_DELAY);
    DIR *directory = opendir(GW_ROOT);
    struct dirent *entry;
    if (directory) {
        while (count < CONFIG_SENTRY_ALERT_LIMIT && (entry = readdir(directory))) {
            char id[GW_ID_MAX + 1];
            if (!record_id(entry->d_name, id)) continue;
            cJSON *record = load_record(id);
            if (!record || !cJSON_IsNumber(cJSON_GetObjectItemCaseSensitive(record, "sequence"))) {
                cJSON_Delete(record);
                continue;
            }
            cJSON_AddBoolToObject(record, "has_image", image_exists(id));
            records[count++] = record;
        }
        closedir(directory);
    }
    xSemaphoreGive(lock);
    qsort(records, count, sizeof(records[0]), newest_first);
    cJSON *array = cJSON_CreateArray();
    for (unsigned i = 0; i < count; i++) cJSON_AddItemToArray(array, records[i]);
    cJSON *json = cJSON_CreateObject();
    cJSON_AddItemToObject(json, "events", array);
    return json;
}

int alerts_image_upload(httpd_req_t *req, const char *id)
{
    if (req->content_len < 4 || req->content_len > GW_IMAGE_MAX) return 413;
    xSemaphoreTake(lock, portMAX_DELAY);
    cJSON *record = load_record(id);
    if (!record) { xSemaphoreGive(lock); return 404; }
    cJSON_Delete(record);
    if (image_exists(id)) { xSemaphoreGive(lock); return 409; }
    if (!reserve_space(req->content_len, id, false)) { xSemaphoreGive(lock); return 507; }
    char temporary[96], path[96];
    file_path(temporary, sizeof(temporary), id, "tmp");
    file_path(path, sizeof(path), id, "jpg");
    FILE *file = fopen(temporary, "wb");
    if (!file) { xSemaphoreGive(lock); return 507; }
    uint8_t buffer[4096], first[2] = {0}, previous = 0, last = 0;
    size_t used = 0;
    int code = 201, timeouts = 0;
    while (used < req->content_len) {
        int n = httpd_req_recv(req, (char *)buffer, sizeof(buffer) < req->content_len - used ?
                               sizeof(buffer) : req->content_len - used);
        if (n == HTTPD_SOCK_ERR_TIMEOUT && timeouts++ < 3) continue;
        if (n <= 0) { code = 400; break; }
        for (int i = 0; i < n; i++) {
            if (used + i < 2) first[used + i] = buffer[i];
            previous = last;
            last = buffer[i];
        }
        if (fwrite(buffer, 1, n, file) != (size_t)n) { code = 507; break; }
        used += n;
    }
    if (fclose(file)) code = 507;
    if (code == 201 && (first[0] != 0xff || first[1] != 0xd8 || previous != 0xff || last != 0xd9)) code = 415;
    if (code == 201 && rename(temporary, path)) code = 507;
    if (code != 201) unlink(temporary);
    xSemaphoreGive(lock);
    return code;
}

esp_err_t alerts_image_send(httpd_req_t *req, const char *id)
{
    char path[96];
    file_path(path, sizeof(path), id, "jpg");
    xSemaphoreTake(lock, portMAX_DELAY);
    FILE *file = fopen(path, "rb");
    if (!file) {
        xSemaphoreGive(lock);
        return api_error(req, 404, "image_not_found");
    }
    httpd_resp_set_type(req, "image/jpeg");
    char disposition[96];
    snprintf(disposition, sizeof(disposition), "inline; filename=\"%s.jpg\"", id);
    httpd_resp_set_hdr(req, "Content-Disposition", disposition);
    char buffer[4096];
    size_t count;
    esp_err_t status = ESP_OK;
    while ((count = fread(buffer, 1, sizeof(buffer), file)) != 0)
        if ((status = httpd_resp_send_chunk(req, buffer, count)) != ESP_OK) break;
    if (ferror(file)) status = ESP_FAIL;
    fclose(file);
    xSemaphoreGive(lock);
    if (status == ESP_OK) status = httpd_resp_send_chunk(req, NULL, 0);
    return status;
}
