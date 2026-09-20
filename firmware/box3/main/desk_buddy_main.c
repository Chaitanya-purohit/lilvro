#include <stdio.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>

#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include "bsp/esp-box-3.h"
#include "esp_codec_dev.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "lvgl.h"
#include "nvs_flash.h"
#include "lwip/netdb.h"
#include "lwip/sockets.h"

#define BUFFER_SIZE 1024
#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAILED_BIT    BIT1
#define WIFI_GLOBAL_IP6_BIT BIT2
#define WIFI_MAX_RETRY     5
#define AUDIO_RECONNECT_DELAY_US (2 * 1000 * 1000)
#define SPEAKER_TONE_SAMPLE_RATE 16000
#define SPEAKER_TONE_SAMPLES     (SPEAKER_TONE_SAMPLE_RATE / 5)
#define AUDIO_REPLY_HEADER_SIZE  16
#define AUDIO_REPLY_MAX_BYTES    (512 * 1024)

/* Wire format for the initial 12-byte audio-stream header. */
#define AUDIO_STREAM_HEADER_SIZE 12
#define AUDIO_STREAM_CONNECTED_BIT BIT0

typedef enum {
    FACE_LISTENING,
    FACE_THINKING,
    FACE_TALKING,
} face_state_t;

static const char *TAG = "desk_buddy";
static EventGroupHandle_t s_wifi_event_group;
static esp_netif_t *s_wifi_sta_netif;
static int s_wifi_retry_count;
static int s_audio_socket = -1;
static int64_t s_next_audio_connect_us;
static esp_codec_dev_handle_t s_speaker;
static int16_t s_speaker_tone[SPEAKER_TONE_SAMPLES];
static SemaphoreHandle_t s_audio_stream_mutex;
static EventGroupHandle_t s_audio_stream_event_group;
static bool s_speaker_playing;
static bool s_waiting_for_global_ip6;
static lv_obj_t *s_face_eyes[2];
static lv_obj_t *s_face_pupils[2];
static lv_obj_t *s_face_smile;
static lv_obj_t *s_face_thinking_mouth;
static lv_obj_t *s_face_talking_mouth;
static bool s_face_initialized;

static const char *wifi_disconnect_reason_name(uint8_t reason)
{
    switch ((wifi_err_reason_t)reason) {
    case WIFI_REASON_UNSPECIFIED: return "UNSPECIFIED";
    case WIFI_REASON_AUTH_EXPIRE: return "AUTH_EXPIRE";
    case WIFI_REASON_AUTH_LEAVE: return "AUTH_LEAVE";
    case WIFI_REASON_DISASSOC_DUE_TO_INACTIVITY: return "DISASSOC_DUE_TO_INACTIVITY";
    case WIFI_REASON_ASSOC_TOOMANY: return "ASSOC_TOOMANY";
    case WIFI_REASON_CLASS2_FRAME_FROM_NONAUTH_STA: return "CLASS2_FRAME_FROM_NONAUTH_STA";
    case WIFI_REASON_CLASS3_FRAME_FROM_NONASSOC_STA: return "CLASS3_FRAME_FROM_NONASSOC_STA";
    case WIFI_REASON_ASSOC_LEAVE: return "ASSOC_LEAVE";
    case WIFI_REASON_ASSOC_NOT_AUTHED: return "ASSOC_NOT_AUTHED";
    case WIFI_REASON_DISASSOC_PWRCAP_BAD: return "DISASSOC_PWRCAP_BAD";
    case WIFI_REASON_DISASSOC_SUPCHAN_BAD: return "DISASSOC_SUPCHAN_BAD";
    case WIFI_REASON_BSS_TRANSITION_DISASSOC: return "BSS_TRANSITION_DISASSOC";
    case WIFI_REASON_IE_INVALID: return "IE_INVALID";
    case WIFI_REASON_MIC_FAILURE: return "MIC_FAILURE";
    case WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT: return "4WAY_HANDSHAKE_TIMEOUT";
    case WIFI_REASON_GROUP_KEY_UPDATE_TIMEOUT: return "GROUP_KEY_UPDATE_TIMEOUT";
    case WIFI_REASON_IE_IN_4WAY_DIFFERS: return "IE_IN_4WAY_DIFFERS";
    case WIFI_REASON_GROUP_CIPHER_INVALID: return "GROUP_CIPHER_INVALID";
    case WIFI_REASON_PAIRWISE_CIPHER_INVALID: return "PAIRWISE_CIPHER_INVALID";
    case WIFI_REASON_AKMP_INVALID: return "AKMP_INVALID";
    case WIFI_REASON_UNSUPP_RSN_IE_VERSION: return "UNSUPP_RSN_IE_VERSION";
    case WIFI_REASON_INVALID_RSN_IE_CAP: return "INVALID_RSN_IE_CAP";
    case WIFI_REASON_802_1X_AUTH_FAILED: return "802_1X_AUTH_FAILED";
    case WIFI_REASON_CIPHER_SUITE_REJECTED: return "CIPHER_SUITE_REJECTED";
    case WIFI_REASON_TDLS_PEER_UNREACHABLE: return "TDLS_PEER_UNREACHABLE";
    case WIFI_REASON_TDLS_UNSPECIFIED: return "TDLS_UNSPECIFIED";
    case WIFI_REASON_SSP_REQUESTED_DISASSOC: return "SSP_REQUESTED_DISASSOC";
    case WIFI_REASON_NO_SSP_ROAMING_AGREEMENT: return "NO_SSP_ROAMING_AGREEMENT";
    case WIFI_REASON_BAD_CIPHER_OR_AKM: return "BAD_CIPHER_OR_AKM";
    case WIFI_REASON_NOT_AUTHORIZED_THIS_LOCATION: return "NOT_AUTHORIZED_THIS_LOCATION";
    case WIFI_REASON_SERVICE_CHANGE_PERCLUDES_TS: return "SERVICE_CHANGE_PERCLUDES_TS";
    case WIFI_REASON_UNSPECIFIED_QOS: return "UNSPECIFIED_QOS";
    case WIFI_REASON_NOT_ENOUGH_BANDWIDTH: return "NOT_ENOUGH_BANDWIDTH";
    case WIFI_REASON_MISSING_ACKS: return "MISSING_ACKS";
    case WIFI_REASON_EXCEEDED_TXOP: return "EXCEEDED_TXOP";
    case WIFI_REASON_STA_LEAVING: return "STA_LEAVING";
    case WIFI_REASON_END_BA: return "END_BA";
    case WIFI_REASON_UNKNOWN_BA: return "UNKNOWN_BA";
    case WIFI_REASON_TIMEOUT: return "TIMEOUT";
    case WIFI_REASON_PEER_INITIATED: return "PEER_INITIATED";
    case WIFI_REASON_AP_INITIATED: return "AP_INITIATED";
    case WIFI_REASON_INVALID_FT_ACTION_FRAME_COUNT: return "INVALID_FT_ACTION_FRAME_COUNT";
    case WIFI_REASON_INVALID_PMKID: return "INVALID_PMKID";
    case WIFI_REASON_INVALID_MDE: return "INVALID_MDE";
    case WIFI_REASON_INVALID_FTE: return "INVALID_FTE";
    case WIFI_REASON_TRANSMISSION_LINK_ESTABLISH_FAILED: return "TRANSMISSION_LINK_ESTABLISH_FAILED";
    case WIFI_REASON_ALTERATIVE_CHANNEL_OCCUPIED: return "ALTERATIVE_CHANNEL_OCCUPIED";
    case WIFI_REASON_BEACON_TIMEOUT: return "BEACON_TIMEOUT";
    case WIFI_REASON_NO_AP_FOUND: return "NO_AP_FOUND";
    case WIFI_REASON_AUTH_FAIL: return "AUTH_FAIL";
    case WIFI_REASON_ASSOC_FAIL: return "ASSOC_FAIL";
    case WIFI_REASON_HANDSHAKE_TIMEOUT: return "HANDSHAKE_TIMEOUT";
    case WIFI_REASON_CONNECTION_FAIL: return "CONNECTION_FAIL";
    case WIFI_REASON_AP_TSF_RESET: return "AP_TSF_RESET";
    case WIFI_REASON_ROAMING: return "ROAMING";
    case WIFI_REASON_ASSOC_COMEBACK_TIME_TOO_LONG: return "ASSOC_COMEBACK_TIME_TOO_LONG";
    case WIFI_REASON_SA_QUERY_TIMEOUT: return "SA_QUERY_TIMEOUT";
    case WIFI_REASON_NO_AP_FOUND_W_COMPATIBLE_SECURITY: return "NO_AP_FOUND_W_COMPATIBLE_SECURITY";
    case WIFI_REASON_NO_AP_FOUND_IN_AUTHMODE_THRESHOLD: return "NO_AP_FOUND_IN_AUTHMODE_THRESHOLD";
    case WIFI_REASON_NO_AP_FOUND_IN_RSSI_THRESHOLD: return "NO_AP_FOUND_IN_RSSI_THRESHOLD";
    default: return "UNKNOWN_REASON";
    }
}

static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_ERROR_CHECK(esp_wifi_connect());
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_CONNECTED) {
        ESP_ERROR_CHECK(esp_netif_create_ip6_linklocal(s_wifi_sta_netif));
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        const wifi_event_sta_disconnected_t *event = event_data;
        uint8_t reason = event != NULL ? event->reason : 0;
        xEventGroupClearBits(s_wifi_event_group, WIFI_GLOBAL_IP6_BIT);
        s_waiting_for_global_ip6 = false;
        ESP_LOGW(TAG, "Wi-Fi disconnected: reason=%u (%s)", reason,
                 wifi_disconnect_reason_name(reason));
        if (s_wifi_retry_count < WIFI_MAX_RETRY) {
            s_wifi_retry_count++;
            ESP_LOGW(TAG, "Wi-Fi disconnected; retrying (%d/%d)",
                     s_wifi_retry_count, WIFI_MAX_RETRY);
            ESP_ERROR_CHECK(esp_wifi_connect());
        } else {
            xEventGroupSetBits(s_wifi_event_group, WIFI_FAILED_BIT);
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        const ip_event_got_ip_t *event = (const ip_event_got_ip_t *)event_data;
        s_wifi_retry_count = 0;
        ESP_LOGI(TAG, "Wi-Fi connected; IP address: " IPSTR, IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_GOT_IP6) {
        const ip_event_got_ip6_t *event = (const ip_event_got_ip6_t *)event_data;
        if (event->esp_netif == s_wifi_sta_netif) {
            ESP_LOGI(TAG, "Wi-Fi IPv6 address[%d]: " IPV6STR,
                     event->ip_index, IPV62STR(event->ip6_info.ip));
            if (esp_netif_ip6_get_addr_type(&event->ip6_info.ip) == ESP_IP6_ADDR_IS_GLOBAL) {
                xEventGroupSetBits(s_wifi_event_group, WIFI_GLOBAL_IP6_BIT);
                s_waiting_for_global_ip6 = false;
                ESP_LOGI(TAG, "Wi-Fi global IPv6 is ready for audio backend connections");
            }
        }
    }
}

/*
 * Starts the station and waits for either a DHCP lease or a bounded retry
 * failure. The caller can continue with local audio features if Wi-Fi is down.
 */
static bool wifi_connect(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    s_wifi_sta_netif = esp_netif_create_default_wifi_sta();
    configASSERT(s_wifi_sta_netif != NULL);

    s_wifi_event_group = xEventGroupCreate();
    configASSERT(s_wifi_event_group != NULL);

    wifi_init_config_t init_config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_config));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_GOT_IP6, &wifi_event_handler, NULL, NULL));

    wifi_config_t wifi_config = {
        .sta = {
            .threshold.authmode = WIFI_AUTH_WPA2_PSK,
            .pmf_cfg = {
                .capable = true,
                .required = false,
            },
        },
    };
    snprintf((char *)wifi_config.sta.ssid, sizeof(wifi_config.sta.ssid), "%s",
             CONFIG_DESK_BUDDY_WIFI_SSID);
    snprintf((char *)wifi_config.sta.password, sizeof(wifi_config.sta.password), "%s",
             CONFIG_DESK_BUDDY_WIFI_PASSWORD);

    ESP_LOGI(TAG, "Connecting to Wi-Fi SSID '%s'", CONFIG_DESK_BUDDY_WIFI_SSID);
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    EventBits_t bits = xEventGroupWaitBits(s_wifi_event_group,
                                            WIFI_CONNECTED_BIT | WIFI_FAILED_BIT,
                                            pdFALSE, pdFALSE, portMAX_DELAY);
    if (bits & WIFI_CONNECTED_BIT) {
        return true;
    }

    ESP_LOGE(TAG, "Unable to connect to '%s' after %d attempts",
             CONFIG_DESK_BUDDY_WIFI_SSID, WIFI_MAX_RETRY);
    return false;
}

static void audio_stream_disconnect(void)
{
    if (s_audio_socket >= 0) {
        shutdown(s_audio_socket, SHUT_RDWR);
        close(s_audio_socket);
        s_audio_socket = -1;
    }
    s_next_audio_connect_us = esp_timer_get_time() + AUDIO_RECONNECT_DELAY_US;
    xEventGroupClearBits(s_audio_stream_event_group, AUDIO_STREAM_CONNECTED_BIT);
}

static bool audio_stream_send_all(const void *data, size_t length)
{
    const uint8_t *bytes = data;
    while (length > 0) {
        int sent = send(s_audio_socket, bytes, length, 0);
        if (sent <= 0) {
            return false;
        }
        bytes += sent;
        length -= sent;
    }
    return true;
}

static bool audio_stream_recv_all(int socket_fd, void *data, size_t length)
{
    uint8_t *bytes = data;
    while (length > 0) {
        int received = recv(socket_fd, bytes, length, 0);
        if (received <= 0) {
            return false;
        }
        bytes += received;
        length -= received;
    }
    return true;
}

static uint32_t audio_stream_read_be32(const uint8_t *bytes)
{
    return ((uint32_t)bytes[0] << 24) | ((uint32_t)bytes[1] << 16) |
           ((uint32_t)bytes[2] << 8) | bytes[3];
}

static bool audio_stream_connect(void)
{
    if (CONFIG_DESK_BUDDY_BACKEND_HOST[0] == '\0') {
        ESP_LOGW(TAG, "Audio backend host is empty; microphone streaming is disabled");
        return false;
    }
    if (s_audio_socket >= 0) {
        return true;
    }
    if ((xEventGroupGetBits(s_wifi_event_group) & WIFI_GLOBAL_IP6_BIT) == 0) {
        if (!s_waiting_for_global_ip6) {
            ESP_LOGI(TAG, "Waiting for a global IPv6 address before connecting audio backend");
            s_waiting_for_global_ip6 = true;
        }
        return false;
    }
    if (esp_timer_get_time() < s_next_audio_connect_us) {
        return false;
    }

    char port[6];
    snprintf(port, sizeof(port), "%d", CONFIG_DESK_BUDDY_BACKEND_PORT);
    ESP_LOGI(TAG, "Attempting audio backend connection to %s:%s",
             CONFIG_DESK_BUDDY_BACKEND_HOST, port);
    struct addrinfo hints = {
        /* Accept both IPv4 and IPv6 results; the hotspot's IPv4 route remains
         * usable even when IPv6 is unavailable or not configured. */
        .ai_family = AF_UNSPEC,
        .ai_socktype = SOCK_STREAM,
    };
    struct addrinfo *addresses = NULL;
    int result = getaddrinfo(CONFIG_DESK_BUDDY_BACKEND_HOST, port, &hints, &addresses);
    if (result != 0 || addresses == NULL) {
        ESP_LOGW(TAG, "Cannot resolve backend '%s' (getaddrinfo=%d)",
                 CONFIG_DESK_BUDDY_BACKEND_HOST, result);
        s_next_audio_connect_us = esp_timer_get_time() + AUDIO_RECONNECT_DELAY_US;
        return false;
    }

    for (const struct addrinfo *address = addresses;
         address != NULL && s_audio_socket < 0;
         address = address->ai_next) {
        int socket_fd = socket(address->ai_family, address->ai_socktype, address->ai_protocol);
        if (socket_fd < 0) {
            continue;
        }
        if (connect(socket_fd, address->ai_addr, address->ai_addrlen) == 0) {
            s_audio_socket = socket_fd;
        } else {
            ESP_LOGW(TAG, "Audio backend connect failed (family=%d, errno=%d)",
                     address->ai_family, errno);
            close(socket_fd);
        }
    }
    freeaddrinfo(addresses);

    if (s_audio_socket < 0) {
        audio_stream_disconnect();
        return false;
    }

    /* DBA1, 16000 Hz (network byte order), mono, signed 16-bit PCM, reserved. */
    const uint8_t header[AUDIO_STREAM_HEADER_SIZE] = {
        'D', 'B', 'A', '1', 0x00, 0x00, 0x3e, 0x80, 0x01, 0x10, 0x00, 0x00,
    };
    if (!audio_stream_send_all(header, sizeof(header))) {
        audio_stream_disconnect();
        return false;
    }

    xEventGroupSetBits(s_audio_stream_event_group, AUDIO_STREAM_CONNECTED_BIT);
    ESP_LOGI(TAG, "Streaming microphone PCM to %s:%d",
             CONFIG_DESK_BUDDY_BACKEND_HOST, CONFIG_DESK_BUDDY_BACKEND_PORT);
    return true;
}

static void audio_stream_send_pcm(const int16_t *samples, size_t byte_count)
{
    if (!audio_stream_connect()) {
        return;
    }
    if (!audio_stream_send_all(samples, byte_count)) {
        ESP_LOGW(TAG, "Audio backend connection closed; will retry");
        audio_stream_disconnect();
    }
}

static void face_set_obj_height(void *obj, int32_t height)
{
    lv_obj_set_height(obj, height);
}

static void face_set_obj_width(void *obj, int32_t width)
{
    lv_obj_set_width(obj, width);
}

static void face_set_obj_translate_x(void *obj, int32_t offset)
{
    lv_obj_set_style_translate_x(obj, offset, 0);
}

static void face_stop_animations_locked(void)
{
    for (size_t i = 0; i < 2; ++i) {
        lv_anim_delete(s_face_eyes[i], NULL);
        lv_anim_delete(s_face_pupils[i], NULL);
        lv_obj_set_style_translate_x(s_face_eyes[i], 0, 0);
        lv_obj_set_style_translate_x(s_face_pupils[i], 0, 0);
    }
    lv_anim_delete(s_face_talking_mouth, NULL);
}

static void face_start_blink_locked(void)
{
    for (size_t i = 0; i < 2; ++i) {
        lv_anim_t blink;
        lv_anim_init(&blink);
        lv_anim_set_var(&blink, s_face_eyes[i]);
        lv_anim_set_values(&blink, 88, 12);
        lv_anim_set_duration(&blink, 90);
        lv_anim_set_reverse_duration(&blink, 140);
        lv_anim_set_repeat_delay(&blink, 3200);
        lv_anim_set_repeat_count(&blink, LV_ANIM_REPEAT_INFINITE);
        lv_anim_set_exec_cb(&blink, face_set_obj_height);
        lv_anim_start(&blink);
    }
}

static void face_start_thinking_shift_locked(void)
{
    for (size_t i = 0; i < 2; ++i) {
        lv_anim_t shift;
        lv_anim_init(&shift);
        lv_anim_set_var(&shift, s_face_eyes[i]);
        lv_anim_set_values(&shift, 0, 6);
        lv_anim_set_duration(&shift, 900);
        lv_anim_set_reverse_duration(&shift, 900);
        lv_anim_set_repeat_count(&shift, LV_ANIM_REPEAT_INFINITE);
        lv_anim_set_exec_cb(&shift, face_set_obj_translate_x);
        lv_anim_start(&shift);

        lv_anim_set_var(&shift, s_face_pupils[i]);
        lv_anim_start(&shift);
    }
}

static void face_start_talking_mouth_locked(void)
{
    lv_anim_t mouth;
    lv_anim_init(&mouth);
    lv_anim_set_var(&mouth, s_face_talking_mouth);
    lv_anim_set_values(&mouth, 72, 92);
    lv_anim_set_duration(&mouth, 180);
    lv_anim_set_reverse_duration(&mouth, 180);
    lv_anim_set_repeat_count(&mouth, LV_ANIM_REPEAT_INFINITE);
    lv_anim_set_exec_cb(&mouth, face_set_obj_width);
    lv_anim_start(&mouth);

    lv_anim_set_values(&mouth, 42, 60);
    lv_anim_set_exec_cb(&mouth, face_set_obj_height);
    lv_anim_start(&mouth);
}

static void desk_buddy_apply_face_locked(face_state_t state)
{
    int eye_width = 58;
    int eye_height = 88;
    int left_eye_x = -66;
    int right_eye_x = 66;
    int eye_y = -38;
    int pupil_y = -38;
    int pupil_left_x = -66;
    int pupil_right_x = 66;

    if (state == FACE_THINKING) {
        eye_width = 54;
        eye_height = 76;
        left_eye_x = -54;
        right_eye_x = 78;
        eye_y = -52;
        pupil_left_x = -46;
        pupil_right_x = 86;
        pupil_y = -66;
    } else if (state == FACE_TALKING) {
        eye_width = 64;
        eye_height = 16;
    }

    for (size_t i = 0; i < 2; ++i) {
        lv_obj_set_size(s_face_eyes[i], eye_width, eye_height);
        lv_obj_align(s_face_eyes[i], LV_ALIGN_CENTER, i == 0 ? left_eye_x : right_eye_x, eye_y);
        lv_obj_set_size(s_face_pupils[i], 16, 30);
        lv_obj_align(s_face_pupils[i], LV_ALIGN_CENTER,
                     i == 0 ? pupil_left_x : pupil_right_x, pupil_y);
        lv_obj_set_hidden(s_face_pupils[i], state == FACE_TALKING);
    }

    if (state == FACE_LISTENING) {
        lv_obj_set_hidden(s_face_smile, false);
        lv_obj_set_hidden(s_face_thinking_mouth, true);
        lv_obj_set_hidden(s_face_talking_mouth, true);
    } else if (state == FACE_THINKING) {
        lv_obj_set_hidden(s_face_smile, true);
        lv_obj_set_hidden(s_face_thinking_mouth, false);
        lv_obj_set_hidden(s_face_talking_mouth, true);
    } else {
        lv_obj_set_hidden(s_face_smile, true);
        lv_obj_set_hidden(s_face_thinking_mouth, true);
        lv_obj_set_hidden(s_face_talking_mouth, false);
    }

    if (state == FACE_LISTENING) {
        face_start_blink_locked();
    } else if (state == FACE_THINKING) {
        face_start_thinking_shift_locked();
    } else {
        face_start_talking_mouth_locked();
    }
}

static void desk_buddy_set_face(face_state_t state)
{
    if (!s_face_initialized || !bsp_display_lock(1)) {
        return;
    }

    face_stop_animations_locked();
    desk_buddy_apply_face_locked(state);
    bsp_display_unlock();
}

static void desk_buddy_face_init(void)
{
    if (bsp_display_start() == NULL) {
        ESP_LOGE(TAG, "Display initialization failed");
        return;
    }
    ESP_ERROR_CHECK(bsp_display_backlight_on());

    if (!bsp_display_lock(0)) {
        ESP_LOGE(TAG, "Could not lock display for face initialization");
        return;
    }

    lv_obj_t *screen = lv_screen_active();
    lv_obj_set_style_bg_color(screen, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);

    for (size_t i = 0; i < 2; ++i) {
        s_face_eyes[i] = lv_obj_create(screen);
        lv_obj_set_style_radius(s_face_eyes[i], LV_RADIUS_CIRCLE, 0);
        lv_obj_set_style_bg_color(s_face_eyes[i], lv_color_white(), 0);
        lv_obj_set_style_border_width(s_face_eyes[i], 0, 0);

        s_face_pupils[i] = lv_obj_create(screen);
        lv_obj_set_style_radius(s_face_pupils[i], LV_RADIUS_CIRCLE, 0);
        lv_obj_set_style_bg_color(s_face_pupils[i], lv_color_black(), 0);
        lv_obj_set_style_border_width(s_face_pupils[i], 0, 0);
    }

    s_face_smile = lv_arc_create(screen);
    lv_obj_set_size(s_face_smile, 156, 84);
    lv_obj_align(s_face_smile, LV_ALIGN_CENTER, 0, 56);
    lv_arc_set_angles(s_face_smile, 20, 160);
    lv_obj_set_style_arc_opa(s_face_smile, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_arc_color(s_face_smile, lv_color_white(), LV_PART_INDICATOR);
    lv_obj_set_style_arc_width(s_face_smile, 12, LV_PART_INDICATOR);
    lv_obj_set_style_arc_rounded(s_face_smile, true, LV_PART_INDICATOR);

    s_face_thinking_mouth = lv_obj_create(screen);
    lv_obj_set_size(s_face_thinking_mouth, 42, 8);
    lv_obj_align(s_face_thinking_mouth, LV_ALIGN_CENTER, 8, 60);
    lv_obj_set_style_radius(s_face_thinking_mouth, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(s_face_thinking_mouth, lv_color_white(), 0);
    lv_obj_set_style_border_width(s_face_thinking_mouth, 0, 0);

    s_face_talking_mouth = lv_obj_create(screen);
    lv_obj_set_size(s_face_talking_mouth, 72, 42);
    lv_obj_align(s_face_talking_mouth, LV_ALIGN_CENTER, 0, 54);
    lv_obj_set_style_radius(s_face_talking_mouth, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(s_face_talking_mouth, lv_color_white(), 0);
    lv_obj_set_style_border_width(s_face_talking_mouth, 0, 0);

    s_face_initialized = true;
    desk_buddy_apply_face_locked(FACE_LISTENING);
    bsp_display_unlock();
    ESP_LOGI(TAG, "Desk Buddy face initialized");
}

static void speaker_test_play_tone(void)
{
    esp_codec_dev_handle_t speaker = bsp_audio_codec_speaker_init();
    if (speaker == NULL) {
        ESP_LOGE(TAG, "Speaker initialization failed");
        return;
    }

    esp_codec_dev_sample_info_t format = {
        .sample_rate = SPEAKER_TONE_SAMPLE_RATE,
        .channel = 1,
        .bits_per_sample = 16,
    };
    esp_codec_dev_set_out_vol(speaker, 100.0);
    if (esp_codec_dev_open(speaker, &format) != ESP_CODEC_DEV_OK) {
        ESP_LOGE(TAG, "Could not open speaker stream");
        return;
    }

    /* 800 Hz, 0.2-second, low-amplitude triangle tone at 16 kHz. */
    for (int i = 0; i < SPEAKER_TONE_SAMPLES; ++i) {
        int phase = i % 20;
        int triangle = phase < 10 ? phase : 20 - phase;
        s_speaker_tone[i] = (triangle * 2 - 10) * 150;
    }

    if (esp_codec_dev_write(speaker, s_speaker_tone, sizeof(s_speaker_tone)) != ESP_CODEC_DEV_OK) {
        ESP_LOGE(TAG, "Speaker test tone write failed");
    } else {
        ESP_LOGI(TAG, "Speaker test tone played");
    }
    esp_codec_dev_close(speaker);
}

static bool speaker_play_reply(int socket_fd, uint32_t byte_count)
{
    if (s_speaker == NULL) {
        s_speaker = bsp_audio_codec_speaker_init();
        if (s_speaker == NULL) {
            ESP_LOGE(TAG, "Speaker initialization failed for reply playback");
            return false;
        }
        esp_codec_dev_set_out_vol(s_speaker, 100.0);
    }

    esp_codec_dev_sample_info_t format = {
        .sample_rate = 16000,
        .channel = 1,
        .bits_per_sample = 16,
    };
    if (esp_codec_dev_open(s_speaker, &format) != ESP_CODEC_DEV_OK) {
        ESP_LOGE(TAG, "Could not open speaker for reply playback");
        return false;
    }

    uint8_t playback_buffer[1024];
    while (byte_count > 0) {
        size_t chunk_size = byte_count < sizeof(playback_buffer) ? byte_count : sizeof(playback_buffer);
        if (!audio_stream_recv_all(socket_fd, playback_buffer, chunk_size) ||
            esp_codec_dev_write(s_speaker, playback_buffer, chunk_size) != ESP_CODEC_DEV_OK) {
            esp_codec_dev_close(s_speaker);
            return false;
        }
        byte_count -= chunk_size;
    }

    esp_codec_dev_close(s_speaker);
    return true;
}

static void set_speaker_playing(bool playing)
{
    xSemaphoreTake(s_audio_stream_mutex, portMAX_DELAY);
    s_speaker_playing = playing;
    xSemaphoreGive(s_audio_stream_mutex);
}

static void audio_stream_receive_task(void *arg)
{
    uint8_t header[AUDIO_REPLY_HEADER_SIZE];

    while (true) {
        /* The microphone path owns connection establishment and the DBA1
         * handshake.  Do not let the reply task touch the socket before it. */
        xEventGroupWaitBits(s_audio_stream_event_group, AUDIO_STREAM_CONNECTED_BIT,
                            pdFALSE, pdTRUE, portMAX_DELAY);

        int socket_fd = s_audio_socket;
        if (socket_fd < 0) {
            continue;
        }

        if (!audio_stream_recv_all(socket_fd, header, sizeof(header))) {
            if (s_audio_socket == socket_fd) {
                ESP_LOGW(TAG, "Audio backend connection closed while waiting for a reply");
                audio_stream_disconnect();
            }
            continue;
        }

        uint32_t sample_rate = audio_stream_read_be32(&header[4]);
        uint32_t byte_count = audio_stream_read_be32(&header[12]);
        if (memcmp(header, "DBR1", 4) != 0 || sample_rate != 16000 ||
            header[8] != 1 || header[9] != 16 || byte_count == 0 ||
            byte_count > AUDIO_REPLY_MAX_BYTES) {
            ESP_LOGE(TAG, "Invalid audio reply frame from backend");
            if (s_audio_socket == socket_fd) {
                audio_stream_disconnect();
            }
            continue;
        }

        ESP_LOGI(TAG, "Playing %" PRIu32 " bytes of backend reply audio", byte_count);
        desk_buddy_set_face(FACE_TALKING);
        set_speaker_playing(true);
        bool playback_ok = speaker_play_reply(socket_fd, byte_count);
        set_speaker_playing(false);
        desk_buddy_set_face(FACE_LISTENING);
        if (!playback_ok && s_audio_socket == socket_fd) {
            ESP_LOGW(TAG, "Backend reply playback failed");
            audio_stream_disconnect();
        }
    }
}

void app_main(void)
{
    printf("\n=== DESK BUDDY MICROPHONE TEST ===\n");

    desk_buddy_face_init();

    s_audio_stream_mutex = xSemaphoreCreateMutex();
    configASSERT(s_audio_stream_mutex != NULL);
    s_audio_stream_event_group = xEventGroupCreate();
    configASSERT(s_audio_stream_event_group != NULL);

    if (!wifi_connect()) {
        ESP_LOGW(TAG, "Continuing with microphone test while Wi-Fi is unavailable");
    }

    speaker_test_play_tone();

    // Initialize the BOX-3 microphone
    esp_codec_dev_handle_t mic = bsp_audio_codec_microphone_init();

    if (mic == NULL) {
        printf("ERROR: Microphone initialization failed\n");
        return;
    }

    printf("Microphone initialized!\n");

    // Configure audio for speech
    esp_codec_dev_sample_info_t fs = {
        .sample_rate = 16000,
        .channel = 1,
        .bits_per_sample = 16,
    };

    esp_codec_dev_set_in_gain(mic, 42.0);

    if (esp_codec_dev_open(mic, &fs) != ESP_CODEC_DEV_OK) {
        printf("ERROR: Could not open microphone\n");
        return;
    }

    printf("Microphone stream opened!\n");
    printf("Listening...\n");

    xTaskCreate(audio_stream_receive_task, "audio_reply", 4096, NULL, 5, NULL);

    int16_t recording_buffer[BUFFER_SIZE / sizeof(int16_t)];

    while (1) {

        int ret = esp_codec_dev_read(
            mic,
            recording_buffer,
            BUFFER_SIZE
        );

        if (ret == ESP_CODEC_DEV_OK) {

            /* Half-duplex: keep capturing, but never send the device's own TTS
             * playback back to the backend. */
            xSemaphoreTake(s_audio_stream_mutex, portMAX_DELAY);
            if (!s_speaker_playing) {
                audio_stream_send_pcm(recording_buffer, BUFFER_SIZE);
            }
            xSemaphoreGive(s_audio_stream_mutex);

            // Find the largest microphone sample in this block.
            int16_t peak = 0;

            for (int i = 0; i < BUFFER_SIZE / sizeof(int16_t); i++) {
                int32_t sample = recording_buffer[i];

                if (sample < 0) {
                    sample = -sample;
                }

                if (sample > peak) {
                    peak = sample;
                }
            }

            printf("Mic level: %d\n", peak);
        }

        vTaskDelay(pdMS_TO_TICKS(50));
    }
}
