/* Thin BLE transport for Lil Vro. AI and network work stays on the gateway. */

#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(lilvro, LOG_LEVEL_INF);

#define LILVRO_SERVICE_UUID \
	BT_UUID_128_ENCODE(0x6f8d0000, 0x6c69, 0x6c76, 0x726f, 0x000000000001)
#define LILVRO_EVENTS_UUID \
	BT_UUID_128_ENCODE(0x6f8d0001, 0x6c69, 0x6c76, 0x726f, 0x000000000001)
#define LILVRO_COMMANDS_UUID \
	BT_UUID_128_ENCODE(0x6f8d0002, 0x6c69, 0x6c76, 0x726f, 0x000000000001)

#define LILVRO_EVENT_BUTTON_PRESSED "BUTTON_PRESSED"
#define LILVRO_COMMAND_REPLY_READY "REPLY_READY"

static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(DT_ALIAS(sw0), gpios);
static const struct gpio_dt_spec connected_led = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);
static const struct gpio_dt_spec activity_led = GPIO_DT_SPEC_GET(DT_ALIAS(led1), gpios);
static struct gpio_callback button_callback;
static struct k_work button_work;
static struct k_work_delayable activity_off_work;
static struct bt_conn *active_connection;
static bool events_notify_enabled;

static struct bt_uuid_128 service_uuid = BT_UUID_INIT_128(LILVRO_SERVICE_UUID);
static struct bt_uuid_128 events_uuid = BT_UUID_INIT_128(LILVRO_EVENTS_UUID);
static struct bt_uuid_128 commands_uuid = BT_UUID_INIT_128(LILVRO_COMMANDS_UUID);

static void set_activity(void)
{
	(void)gpio_pin_set_dt(&activity_led, 1);
	(void)k_work_reschedule(&activity_off_work, K_MSEC(250));
}

static void activity_off_handler(struct k_work *work)
{
	ARG_UNUSED(work);
	(void)gpio_pin_set_dt(&activity_led, 0);
}

static ssize_t write_command(struct bt_conn *conn, const struct bt_gatt_attr *attr,
				     const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{
	ARG_UNUSED(conn);
	ARG_UNUSED(attr);
	ARG_UNUSED(flags);

	if (offset != 0 || len == 0) {
		return -EINVAL;
	}

	if (len == (sizeof(LILVRO_COMMAND_REPLY_READY) - 1) &&
	    memcmp(buf, LILVRO_COMMAND_REPLY_READY, len) == 0) {
		LOG_INF("Received command: %s", LILVRO_COMMAND_REPLY_READY);
		set_activity();
		return len;
	}

	LOG_WRN("Unknown gateway command, length %u", len);
	return len;
}

static void event_ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
	ARG_UNUSED(attr);
	events_notify_enabled = (value == BT_GATT_CCC_NOTIFY);
	LOG_INF("Gateway event notifications %s", events_notify_enabled ? "enabled" : "disabled");
}

BT_GATT_SERVICE_DEFINE(lilvro_service,
	BT_GATT_PRIMARY_SERVICE(&service_uuid),
	BT_GATT_CHARACTERISTIC(&events_uuid.uuid,
		BT_GATT_CHRC_NOTIFY,
		BT_GATT_PERM_NONE,
		NULL, NULL, NULL),
	BT_GATT_CCC(event_ccc_changed,
		BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
	BT_GATT_CHARACTERISTIC(&commands_uuid.uuid,
		BT_GATT_CHRC_WRITE | BT_GATT_CHRC_WRITE_WITHOUT_RESP,
		BT_GATT_PERM_WRITE,
		NULL, write_command, NULL),
);

static void send_event(const char *event)
{
	int err;

	if (active_connection == NULL || !events_notify_enabled) {
		LOG_WRN("Cannot send event; gateway is not subscribed");
		return;
	}

	err = bt_gatt_notify(active_connection, &lilvro_service.attrs[2],
			    event, strlen(event));
	if (err) {
		LOG_WRN("Event notification failed: %d", err);
		return;
	}

	LOG_INF("Sent event: %s", event);
	set_activity();
}

static void button_work_handler(struct k_work *work)
{
	ARG_UNUSED(work);
	send_event(LILVRO_EVENT_BUTTON_PRESSED);
}

static void button_pressed(const struct device *port, struct gpio_callback *callback,
			   uint32_t pins)
{
	ARG_UNUSED(port);
	ARG_UNUSED(callback);
	ARG_UNUSED(pins);
	(void)k_work_submit(&button_work);
}

static void connected(struct bt_conn *conn, uint8_t err)
{
	if (err) {
		LOG_ERR("Connection failed: %u", err);
		return;
	}

	active_connection = bt_conn_ref(conn);
	(void)gpio_pin_set_dt(&connected_led, 1);
	LOG_INF("Gateway connected");
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	LOG_INF("Gateway disconnected: reason %u", reason);
	(void)gpio_pin_set_dt(&connected_led, 0);
	events_notify_enabled = false;

	if (active_connection != NULL) {
		bt_conn_unref(active_connection);
		active_connection = NULL;
	}

	ARG_UNUSED(conn);
}

BT_CONN_CB_DEFINE(connection_callbacks) = {
	.connected = connected,
	.disconnected = disconnected,
};

static void bt_ready(int err)
{
	if (err) {
		LOG_ERR("Bluetooth init failed: %d", err);
		return;
	}

	err = bt_le_adv_start(BT_LE_ADV_CONN_NAME, NULL, 0, NULL, 0);
	if (err) {
		LOG_ERR("Advertising start failed: %d", err);
		return;
	}

	LOG_INF("Advertising as Lil Vro");
}

int main(void)
{
	int err;

	if (!gpio_is_ready_dt(&button) || !gpio_is_ready_dt(&connected_led) ||
	    !gpio_is_ready_dt(&activity_led)) {
		LOG_ERR("DK GPIO devices are not ready");
		return 0;
	}

	err = gpio_pin_configure_dt(&button, GPIO_INPUT);
	if (err) {
		LOG_ERR("Button GPIO configuration failed: %d", err);
		return 0;
	}
	err = gpio_pin_configure_dt(&connected_led, GPIO_OUTPUT_INACTIVE);
	if (err) {
		LOG_ERR("Connected LED configuration failed: %d", err);
		return 0;
	}
	err = gpio_pin_configure_dt(&activity_led, GPIO_OUTPUT_INACTIVE);
	if (err) {
		LOG_ERR("Activity LED configuration failed: %d", err);
		return 0;
	}

	k_work_init(&button_work, button_work_handler);
	k_work_init_delayable(&activity_off_work, activity_off_handler);
	gpio_init_callback(&button_callback, button_pressed, BIT(button.pin));
	err = gpio_add_callback(button.port, &button_callback);
	if (err) {
		LOG_ERR("Button callback registration failed: %d", err);
		return 0;
	}
	err = gpio_pin_interrupt_configure_dt(&button, GPIO_INT_EDGE_TO_ACTIVE);
	if (err) {
		LOG_ERR("Button interrupt configuration failed: %d", err);
		return 0;
	}

	err = bt_enable(bt_ready);
	if (err) {
		LOG_ERR("Bluetooth enable failed: %d", err);
		return 0;
	}

	return 0;
}
