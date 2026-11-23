#include "gateway.h"
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_timer.h"

#define CHAT_SLOTS 4
#define RESPONSE_LIMIT (64 * 1024)
typedef enum { JOB_EMPTY, JOB_QUEUED, JOB_RUNNING, JOB_DONE, JOB_FAILED } job_state_t;
typedef struct {
    char id[GW_ID_MAX + 1];
    char *question;
    char *answer;
    char error[160];
    job_state_t state;
    int upstream_status;
    int64_t touched;
} chat_job_t;
static chat_job_t jobs[CHAT_SLOTS];
static QueueHandle_t queue;
static SemaphoreHandle_t lock;
static const char *states[] = {"empty", "queued", "running", "done", "error"};

static cJSON *job_json(const chat_job_t *job)
{
    cJSON *json = cJSON_CreateObject();
    cJSON_AddStringToObject(json, "request_id", job->id);
    cJSON_AddStringToObject(json, "state", states[job->state]);
    if (job->answer) cJSON_AddStringToObject(json, "answer", job->answer);
    if (job->error[0]) cJSON_AddStringToObject(json, "error", job->error);
    if (job->upstream_status) cJSON_AddNumberToObject(json, "upstream_status", job->upstream_status);
    return json;
}

static bool same_question(const chat_job_t *job, const char *question)
{
    return job->question && strcmp(job->question, question) == 0;
}

int chat_submit(const cJSON *request, cJSON **out)
{
    const cJSON *id = cJSON_GetObjectItemCaseSensitive(request, "request_id");
    const cJSON *question = cJSON_GetObjectItemCaseSensitive(request, "question");
    if (!cJSON_IsString(id) || !gateway_id_valid(id->valuestring) ||
        !cJSON_IsString(question) || !gateway_text_valid(question->valuestring, GW_PROMPT_MAX)) return 400;
    xSemaphoreTake(lock, portMAX_DELAY);
    int slot = -1;
    int oldest_completed = -1;
    int64_t now = esp_timer_get_time();
    for (int i = 0; i < CHAT_SLOTS; i++) {
        if (jobs[i].state != JOB_EMPTY && strcmp(jobs[i].id, id->valuestring) == 0) {
            int code = same_question(&jobs[i], question->valuestring) ? 200 : 409;
            if (code == 200) *out = job_json(&jobs[i]);
            xSemaphoreGive(lock);
            return code;
        }
        bool expired = jobs[i].state >= JOB_DONE && now - jobs[i].touched > 600000000LL;
        if (slot < 0 && (jobs[i].state == JOB_EMPTY || expired)) slot = i;
        if (jobs[i].state >= JOB_DONE && (oldest_completed < 0 || jobs[i].touched < jobs[oldest_completed].touched))
            oldest_completed = i;
    }
    if (slot < 0) slot = oldest_completed;
    if (slot < 0) {
        xSemaphoreGive(lock);
        return 429;
    }
    char *copy = strdup(question->valuestring);
    if (!copy) {
        xSemaphoreGive(lock);
        return 503;
    }
    chat_job_t *job = &jobs[slot];
    free(job->question);
    free(job->answer);
    memset(job, 0, sizeof(*job));
    strlcpy(job->id, id->valuestring, sizeof(job->id));
    job->question = copy;
    job->state = JOB_QUEUED;
    job->touched = now;
    if (xQueueSend(queue, &slot, 0) != pdPASS) {
        free(job->question);
        memset(job, 0, sizeof(*job));
        xSemaphoreGive(lock);
        return 429;
    }
    *out = job_json(job);
    xSemaphoreGive(lock);
    return 202;
}

cJSON *chat_result(const char *id)
{
    cJSON *out = NULL;
    xSemaphoreTake(lock, portMAX_DELAY);
    for (int i = 0; i < CHAT_SLOTS; i++)
        if (jobs[i].state != JOB_EMPTY && strcmp(jobs[i].id, id) == 0) out = job_json(&jobs[i]);
    xSemaphoreGive(lock);
    return out;
}

static void fail(chat_job_t *job, const char *reason)
{
    strlcpy(job->error, reason, sizeof(job->error));
}

static cJSON *make_request(const gateway_config_t *config, const char *question)
{
    cJSON *body = cJSON_CreateObject();
    cJSON_AddStringToObject(body, "model", config->model);
    cJSON_AddBoolToObject(body, "stream", false);
    cJSON_AddNumberToObject(body, "max_tokens", 2048);
    cJSON *thinking = cJSON_AddObjectToObject(body, "thinking");
    cJSON_AddStringToObject(thinking, "type", "disabled");
    cJSON *messages = cJSON_AddArrayToObject(body, "messages");
    cJSON *system = cJSON_CreateObject();
    cJSON_AddStringToObject(system, "role", "system");
    cJSON_AddStringToObject(system, "content", "你是车载监测终端的中文助手。简洁回答用户问题。不要声称已看到未提供的摄像头图像或实时状态。");
    cJSON_AddItemToArray(messages, system);
    cJSON *user = cJSON_CreateObject();
    cJSON_AddStringToObject(user, "role", "user");
    cJSON_AddStringToObject(user, "content", question);
    cJSON_AddItemToArray(messages, user);
    return body;
}

static void ask_deepseek(chat_job_t *job)
{
    gateway_config_t config;
    config_read(&config);
    if (!config.api_key[0]) { fail(job, "deepseek_api_key_missing"); return; }
    if (!network_online()) { fail(job, "wifi_internet_unavailable"); return; }
    if (time(NULL) < 1700000000) { fail(job, "network_time_not_ready"); return; }
    cJSON *body = make_request(&config, job->question);
    char *payload = cJSON_PrintUnformatted(body);
    cJSON_Delete(body);
    char *response = calloc(1, RESPONSE_LIMIT + 1);
    if (!payload || !response) {
        fail(job, "out_of_memory");
        free(payload);
        free(response);
        return;
    }
    esp_http_client_config_t settings = {
        .url = "https://api.deepseek.com/chat/completions",
        .method = HTTP_METHOD_POST,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .timeout_ms = 45000,
        .disable_auto_redirect = true,
        .buffer_size = 2048,
    };
    esp_http_client_handle_t client = esp_http_client_init(&settings);
    if (!client) { fail(job, "http_client_init_failed"); goto cleanup; }
    char authorization[sizeof(config.api_key) + 8];
    snprintf(authorization, sizeof(authorization), "Bearer %s", config.api_key);
    esp_http_client_set_header(client, "Authorization", authorization);
    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_err_t err = esp_http_client_open(client, strlen(payload));
    if (err != ESP_OK) { fail(job, "deepseek_connect_failed"); goto close; }
    size_t sent = 0, size = strlen(payload);
    while (sent < size) {
        int n = esp_http_client_write(client, payload + sent, size - sent);
        if (n <= 0) { fail(job, "deepseek_send_failed"); goto close; }
        sent += n;
    }
    if (esp_http_client_fetch_headers(client) < 0) { fail(job, "deepseek_headers_failed"); goto close; }
    job->upstream_status = esp_http_client_get_status_code(client);
    size_t used = 0;
    while (used < RESPONSE_LIMIT) {
        int n = esp_http_client_read(client, response + used, RESPONSE_LIMIT - used);
        if (n < 0) { fail(job, "deepseek_receive_failed"); goto close; }
        if (!n) break;
        used += n;
    }
    if (!esp_http_client_is_complete_data_received(client)) { fail(job, "deepseek_response_incomplete_or_too_large"); goto close; }
    if (job->upstream_status != 200) { fail(job, "deepseek_http_error"); goto close; }
    cJSON *result = cJSON_Parse(response);
    cJSON *choices = cJSON_GetObjectItemCaseSensitive(result, "choices");
    cJSON *choice = cJSON_GetArrayItem(choices, 0);
    cJSON *message = cJSON_GetObjectItemCaseSensitive(choice, "message");
    cJSON *text = cJSON_GetObjectItemCaseSensitive(message, "content");
    if (cJSON_IsString(text) && gateway_text_valid(text->valuestring, GW_ANSWER_MAX)) {
        job->answer = strdup(text->valuestring);
        if (!job->answer) fail(job, "out_of_memory");
    } else fail(job, "deepseek_answer_missing_or_too_large");
    cJSON_Delete(result);
close:
    esp_http_client_close(client);
    esp_http_client_cleanup(client);
cleanup:
    free(payload);
    free(response);
    memset(&config, 0, sizeof(config));
}

static void worker(void *arg)
{
    (void)arg;
    for (;;) {
        int slot;
        xQueueReceive(queue, &slot, portMAX_DELAY);
        xSemaphoreTake(lock, portMAX_DELAY);
        jobs[slot].state = JOB_RUNNING;
        /* Work on a private result, while HTTP polling reads a stable job. */
        chat_job_t result = jobs[slot];
        xSemaphoreGive(lock);
        ask_deepseek(&result);
        xSemaphoreTake(lock, portMAX_DELAY);
        jobs[slot].answer = result.answer;
        strlcpy(jobs[slot].error, result.error, sizeof(result.error));
        jobs[slot].upstream_status = result.upstream_status;
        jobs[slot].state = result.answer ? JOB_DONE : JOB_FAILED;
        jobs[slot].touched = esp_timer_get_time();
        xSemaphoreGive(lock);
    }
}

void chat_start(void)
{
    lock = xSemaphoreCreateMutex();
    queue = xQueueCreate(CHAT_SLOTS, sizeof(int));
    configASSERT(lock && queue);
    configASSERT(xTaskCreate(worker, "deepseek", 12288, NULL, 4, NULL) == pdPASS);
}
