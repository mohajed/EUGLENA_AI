/*
 * Wemos ESPUI PWM RGBW+IR LED Controller
 *
 * Firmware for an ESP8266/ESP32-based RGBW+IR LED controller.
 * Control via ESPUI web interface, serial commands, and MQTT.
 * Settings (WiFi, MQTT) are persisted in non-volatile storage (Preferences).
 *
 * Project files:
 *   - Wemos_ESPUI_PWM_RGBW_LED.ino : Setup, loop, and global declarations
 *   - WiFiMQTT.ino                 : WiFi connection and MQTT management
 *   - ESPUI.ino                    : Web UI construction
 *   - Callback.ino                 : UI, MQTT, and serial command callbacks
 *   - LED.ino                      : LED control (set, pulse, JSON parsing)
 *   - Tools.ino                    : Utilities (load_memory, splitString)
 */

// ── Platform ─────────────────────────────────────────────────────────────────
#ifdef ESP8266
#include <ESP8266WiFi.h>
#elif defined ESP32
#include <WiFi.h>
#define LED_BUILTIN 2
#else
#error Architecture unrecognized by this code.
#endif

// ── Persistent storage ──────────────────────────────────────────────────────
#include <Preferences.h>
Preferences preferences;

// ── DNS captive portal ──────────────────────────────────────────────────────
#include <DNSServer.h>
const byte DNS_PORT = 53;
IPAddress apIP(192, 168, 4, 1);
DNSServer dnsServer;
const char *hostname = "Microscope RGBWIR";
bool wificonnected = false;

// ── MQTT ────────────────────────────────────────────────────────────────────
#include <PubSubClient.h>
WiFiClient espClient;
PubSubClient client(espClient);
int mqtt_retry_delay = 10000; // Delay between reconnection attempts (ms)
unsigned long last_millis = 0;

// ── ESPUI – Web interface controls ──────────────────────────────────────────
#include <ESPUI.h>

// Control IDs (assigned during UI initialization)
uint16_t wifi_ssid_text, wifi_pass_text;
uint16_t mqtt_server_text, mqtt_topic_in_text, mqtt_topic_out_text;
uint16_t mqtt_user_text, mqtt_pass_text, mqtt_enabled_switch;
uint16_t statusLabelId, serialLabelId;
uint16_t pulse_r_slider, pulse_g_slider, pulse_b_slider, pulse_w_slider,
    pulse_dur_in;

// Network settings loaded from persistent storage
String stored_ssid, stored_pass;
String stored_mqtt_server, stored_mqtt_user, stored_mqtt_pass;
String stored_mqtt_topic_in, stored_mqtt_topic_out;
bool wifi_enabled = false;
bool mqtt_enabled = false;

// ── LED – Pin mapping and runtime state ─────────────────────────────────────
#define Red 14
#define Green 16
#define Blue 4
#define White 5
#define IR 13
#define PWMRANGE 1000
#define PWMFREQ 1000

// Current intensity of each channel
int R_int = 0;
int G_int = 0;
int B_int = 0;
int W_int = 0;
int IR_int = 0;

// Pulse parameters (set from the UI or MQTT)
int pulse_R = 0;
int pulse_G = 0;
int pulse_B = 0;
int pulse_W = 0;
int pulse_duration = 0;
bool pulse_flag = false;

// JSON buffer for incoming commands
DynamicJsonDocument CMD(2048);

// ═════════════════════════════════════════════════════════════════════════════
//  SETUP
// ═════════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  Serial.println();

  // Configure PWM range and frequency
  analogWriteRange(PWMRANGE);
  analogWriteFreq(PWMFREQ);

  // Initialize LED output pins
  pinMode(Red, OUTPUT);
  pinMode(Green, OUTPUT);
  pinMode(Blue, OUTPUT);
  pinMode(White, OUTPUT);

  // Turn off all LEDs at boot
  analogWrite(Red, 0);
  analogWrite(Green, 0);
  analogWrite(Blue, 0);
  analogWrite(White, 0);
  analogWrite(IR, 0);

  // Load saved settings from flash
  preferences.begin("Settings");
  load_memory();

  // Start WiFi + web UI if enabled
  if (wifi_enabled) {
    wifi_init();
    espui_init();
  }

  // Visual self-test of each LED channel
  test_LED(Red);
  test_LED(Green);
  test_LED(Blue);
  test_LED(White);
  test_LED(IR);
}

// ═════════════════════════════════════════════════════════════════════════════
//  LOOP
// ═════════════════════════════════════════════════════════════════════════════
void loop() {
  dnsServer.processNextRequest();

  // Process incoming serial commands
  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    ESPUI.print(serialLabelId, input);
    SerialSetup(input);
  }

  // Maintain MQTT connection
  mqtt_loop();

  // Execute a pending pulse if requested
  if (pulse_flag) {
    pulse_LED(pulse_duration, pulse_R, pulse_G, pulse_B, pulse_W, false);
  }
}