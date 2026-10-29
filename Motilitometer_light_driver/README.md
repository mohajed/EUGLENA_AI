# Wemos ESPUI PWM RGBW+IR LED Controller

ESP8266/ESP32 firmware for driving RGBW + IR LEDs via PWM.  
Controllable through a **web interface** (ESPUI), **serial commands**, and **MQTT**.

## Features

- **5-channel PWM** — Red, Green, Blue, White, IR (0–1000 range)
- **Web UI** — ESPUI-based dashboard with sliders for each channel
- **Pulse mode** — Timed flash with configurable RGBW intensities and duration (ms or µs)
- **MQTT integration** — Subscribe to a topic and control LEDs remotely via JSON
- **Serial CLI** — Configure WiFi, MQTT, and LED values over serial (115200 baud)
- **Persistent settings** — WiFi credentials & MQTT config saved in flash (Preferences)
- **Access Point fallback** — Creates a hotspot if WiFi connection fails
- **Captive portal** — DNS redirect for easy setup when in AP mode
- **Boot self-test** — Each LED channel ramps up/down on startup to verify wiring

## Hardware

| Channel | GPIO |
|---------|------|
| Red     | 14   |
| Green   | 16   |
| Blue    | 4    |
| White   | 5    |
| IR      | 13   |

## Project Structure

| File | Description |
|------|-------------|
| `Wemos_ESPUI_PWM_RGBW_LED.ino` | Setup, loop, and global declarations |
| `WiFiMQTT.ino` | WiFi connection and MQTT management |
| `ESPUI.ino` | Web UI construction (LED, Pulse, WiFi, Debug tabs) |
| `Callback.ino` | UI callbacks, MQTT handler, and serial command parser |
| `LED.ino` | LED control functions (set, pulse, JSON parsing) |
| `Tools.ino` | Utilities (load settings from flash, string splitting) |

## Serial Commands

Type `help` in the serial monitor to see all commands:

```
info              — Print saved settings
restart           — Reboot the ESP
wifi [0-1]        — Enable / disable WiFi
ssid [text]       — Set WiFi SSID
password [text]   — Set WiFi password
mqtten [0-1]      — Enable / disable MQTT
mqttserver [text] — Set MQTT broker IP
mqttuser [text]   — Set MQTT username
mqttpass [text]   — Set MQTT password
topicin [text]    — Set MQTT input topic
topicout [text]   — Set MQTT output topic
```

## JSON LED Commands

Send JSON via serial or MQTT to control LEDs:

```json
{"r": 500, "g": 0, "b": 200, "w": 0}
{"pulse": 100, "r": 1000, "g": 0, "b": 0, "w": 0}
{"pulse": 50, "r": 800, "g": 0, "b": 0, "w": 0, "microsecond": true}
```

## Dependencies

- [ESPUI](https://github.com/s00500/ESPUI)
- [PubSubClient](https://github.com/knolleary/pubsubclient)
- [ArduinoJson](https://github.com/bblanchon/ArduinoJson)
- ESP8266 or ESP32 Arduino Core
