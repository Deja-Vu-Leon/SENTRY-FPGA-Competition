# SENTRY 网口接口 v1

设备提供 HTTP/1.1 服务，默认 `http://192.168.50.1`。除静态网页 `GET /` 外均要求请求头：

```http
Authorization: Bearer sentry-development-token
```

JSON 使用 UTF-8，JSON 请求体最大 8192 字节。请求应带准确 Content-Length。JSON 响应和错误使用 `application/json`，错误体包含 `error`。

## 提交问题

`POST /v1/chat`

```json
{"request_id":"question-0001","question":"前方出现行人时应如何理解预警？"}
```

返回 202：

```json
{"request_id":"question-0001","state":"queued"}
```

相同 request_id 和 question 的重试返回现有任务。相同 ID 携带不同问题返回 409。

`GET /v1/chat/question-0001` 获取状态。

```json
{"request_id":"question-0001","state":"done","answer":"……","upstream_status":200}
```

state 为 queued / running / done / error。error 状态附带错误码，可能包括 `deepseek_api_key_missing`、`wifi_internet_unavailable`、`network_time_not_ready`、`deepseek_http_error`。上游响应错误会附带 upstream_status。

最多保存 4 个任务槽，新的请求可复用最早已完成槽。全部槽处于排队/运行状态时返回 429。结果应及时读取，ESP32 重启后任务清空。问题最长 4096 UTF-8 字节，回答最长 16384 UTF-8 字节。DeepSeek 请求超时 45 秒，实际整次网络传输时间可能更长。出现网络错误后由客户端以新 ID 再提交。

## 上传报警元数据

`POST /v1/alerts`

```json
{
  "event_id":"B01-20261118-000001",
  "camera":"B01",
  "reason":"疑似滑坡源区",
  "event_time":"2026-11-18T10:30:00+08:00",
  "confidence":0.93
}
```

新建返回 201，重试相同记录返回 200，ID 冲突返回 409，空间不足返回 507。confidence 可省略或为 null，数值范围 0 到 1。event_time 保留上传方提供的事件时刻和时区。

## 上传报警图像

`PUT /v1/alerts/B01-20261118-000001/image`

Content-Type 为 image/jpeg，请求体为原始 JPEG 字节。需先创建报警元数据，成功返回 201 和 has_image=true。同一 ID 已有图像返回 409。客户端可 GET 图像核对后将相同重传视为成功。

固件检查 JPEG 起止标记，最大 2097152 字节。图像分块写入，保留上传图片的分辨率。图像不完整返回 400，格式标记不符返回 415，空间不足返回 507。临时文件不作为完成图像展示，掉电后清理残留临时文件。

## 无线读取

- `GET /v1/alerts` 返回 `{"events":[...]}`，按入库顺序从新到旧。每条附带 sequence 和 has_image。
- `GET /v1/alerts/{event_id}/image` 返回 image/jpeg。
- `GET /v1/status` 返回网口、Wi-Fi、设备运行时间、校时状态、模型和 Key 是否已设置。
- `GET /` 为手机和 PC 共用报警网页，在页面输入令牌后可查看、下载图像。

event_id 和 request_id 均为 1–48 个 ASCII 字母、数字、下划线或连字符。

## 保存配置

`POST /v1/settings` 支持 wifi_ssid、wifi_password、deepseek_api_key、model、access_token、ap_password。保存成功返回 saved=true。切换 Wi-Fi 参数后调用 `POST /v1/restart`，请求体为 `{}`。

配置接口不返回秘密字段。令牌更新后，下一条请求使用新令牌。修改配置需已有令牌。
