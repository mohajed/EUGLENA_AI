// ═════════════════════════════════════════════════════════════════════════════
//  ESPUI Slider Callback
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Called when any LED-tab slider value changes.
 * Routes the new value to the correct LED channel based on the control ID.
 */
void SliderCallback(Control *sender, int type) {
  switch (sender->id) {
  case 2:
    R_int = sender->value.toInt();
    set_LED(Red, R_int);
    break;
  case 5:
    G_int = sender->value.toInt();
    set_LED(Green, G_int);
    break;
  case 8:
    B_int = sender->value.toInt();
    set_LED(Blue, B_int);
    break;
  case 11:
    W_int = sender->value.toInt();
    set_LED(White, W_int);
    break;
  case 14:
    IR_int = sender->value.toInt();
    set_LED(IR, IR_int);
    break;
  }
}

// ═════════════════════════════════════════════════════════════════════════════
//  Pulse Button Callback
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Triggered when the Pulse button is pressed (B_DOWN).
 * Reads the current pulse slider values and duration, then sets the pulse flag
 * so the main loop executes the timed pulse.
 */
void PulseCallback(Control *sender, int type) {
  if (type == B_DOWN) {
    pulse_duration = ESPUI.getControl(pulse_dur_in)->value.toInt();
    pulse_R = ESPUI.getControl(pulse_r_slider)->value.toInt();
    pulse_G = ESPUI.getControl(pulse_g_slider)->value.toInt();
    pulse_B = ESPUI.getControl(pulse_b_slider)->value.toInt();
    pulse_W = ESPUI.getControl(pulse_w_slider)->value.toInt();
    pulse_flag = true;
    Serial.printf("R %d,G %d,B %d,W %d,Dur %d,\n", pulse_R, pulse_G, pulse_B,
                  pulse_W, pulse_duration);
  }
}

// ═════════════════════════════════════════════════════════════════════════════
//  MQTT Message Callback
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Called when a message arrives on a subscribed MQTT topic.
 * Converts the payload to a String and forwards it to the serial command
 * parser.
 */
void mqtt_callback(String topic, byte *message, unsigned int length) {
  String payload;
  for (int i = 0; i < length; i++) {
    payload += (char)message[i];
  }
  SerialSetup(payload);
}

// ═════════════════════════════════════════════════════════════════════════════
//  Default / No-op Callback
// ═════════════════════════════════════════════════════════════════════════════

/** Empty callback used for ESPUI controls that don't need immediate action. */
void textCallback(Control *sender, int type) {}

// ═════════════════════════════════════════════════════════════════════════════
//  Save WiFi / MQTT Settings Callback
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Reads all WiFi and MQTT fields from the web UI and writes them
 * to persistent storage. Triggered on button release (B_UP).
 */
void SaveWifiDetailsCallback(Control *sender, int type) {
  if (type == B_UP) {
    // Read current values from the UI
    stored_ssid = ESPUI.getControl(wifi_ssid_text)->value;
    stored_pass = ESPUI.getControl(wifi_pass_text)->value;
    stored_mqtt_server = String(ESPUI.getControl(mqtt_server_text)->value);
    stored_mqtt_user = String(ESPUI.getControl(mqtt_user_text)->value);
    stored_mqtt_pass = String(ESPUI.getControl(mqtt_pass_text)->value);
    stored_mqtt_topic_in = ESPUI.getControl(mqtt_topic_in_text)->value;
    stored_mqtt_topic_out = ESPUI.getControl(mqtt_topic_out_text)->value;
    mqtt_enabled =
        ESPUI.getControl(mqtt_enabled_switch)->value.toInt() ? true : false;

    // Persist to flash
    preferences.putString("ssid", stored_ssid);
    preferences.putString("pass", stored_pass);
    preferences.putString("mqtt_server", stored_mqtt_server);
    preferences.putString("mqtt_user", stored_mqtt_user);
    preferences.putString("mqtt_pass", stored_mqtt_pass);
    preferences.putString("mqtt_topic_in", stored_mqtt_topic_in);
    preferences.putString("mqtt_topic_out", stored_mqtt_topic_out);
    preferences.putBool("mqtt_enabled", mqtt_enabled);

    // Debug output
    Serial.println("Saving settings");
    Serial.println(stored_ssid);
    Serial.println(stored_pass);
    Serial.println(stored_mqtt_server);
    Serial.println(stored_mqtt_user);
    Serial.println(stored_mqtt_pass);
    Serial.println(stored_mqtt_topic_in);
    Serial.println(stored_mqtt_topic_out);
    Serial.println(mqtt_enabled);
  }
}

// ═════════════════════════════════════════════════════════════════════════════
//  ESP Reboot Callback
// ═════════════════════════════════════════════════════════════════════════════

/** Reboots the ESP on button release. */
void ESPReset(Control *sender, int type) {
  if (type == B_UP) {
    ESP.restart();
  }
}

// ═════════════════════════════════════════════════════════════════════════════
//  Serial Command Parser
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Parses a text command received from the serial port or MQTT.
 * Supported commands (type "help" for the full list):
 *   wifi, ssid, password, mqtten, mqttserver, mqttuser, mqttpass,
 *   topicin, topicout, restart, info, help, and JSON LED commands.
 */
void SerialSetup(String input) {

  if (input.indexOf("wifi") > -1) {
    wifi_enabled = splitString(input, ' ', 1).toInt() ? true : false;
    preferences.putBool("wifi_enabled", wifi_enabled);
    Serial.println("WiFi : " + String(wifi_enabled));
  }

  else if (input.indexOf("ssid") > -1) {
    stored_ssid = splitString(input, ' ', 1);
    preferences.putString("ssid", stored_ssid);
    Serial.println("New SSID : " + stored_ssid);
  }

  else if (input.indexOf("password") > -1) {
    stored_pass = splitString(input, ' ', 1);
    preferences.putString("pass", stored_pass);
    Serial.println("New password : " + stored_pass);
  }

  else if (input.indexOf("mqtten") > -1) {
    mqtt_enabled = splitString(input, ' ', 1).toInt() ? true : false;
    preferences.putBool("mqtt_enabled", mqtt_enabled);
    Serial.println("MQTT enabled : " + String(mqtt_enabled));
  }

  else if (input.indexOf("mqttserver") > -1) {
    stored_mqtt_server = splitString(input, ' ', 1);
    preferences.putString("mqtt_server", stored_mqtt_server);
    Serial.println("New MQTT server : " + stored_mqtt_server);
  }

  else if (input.indexOf("mqttuser") > -1) {
    stored_mqtt_user = splitString(input, ' ', 1);
    preferences.putString("mqtt_user", stored_mqtt_user);
    Serial.println("New MQTT user : " + stored_mqtt_user);
  }

  else if (input.indexOf("mqttpass") > -1) {
    stored_mqtt_pass = splitString(input, ' ', 1);
    preferences.putString("mqtt_pass", stored_mqtt_pass);
    Serial.println("New MQTT pass : " + stored_mqtt_pass);
  }

  else if (input.indexOf("topicin") > -1) {
    stored_mqtt_topic_in = splitString(input, ' ', 1);
    preferences.putString("mqtt_topic_in", stored_mqtt_topic_in);
    Serial.println("New Topic IN : " + stored_mqtt_topic_in);
  }

  else if (input.indexOf("topicout") > -1) {
    stored_mqtt_topic_out = splitString(input, ' ', 1);
    preferences.putString("mqtt_topic_out", stored_mqtt_topic_out);
    Serial.println("New Topic OUT : " + stored_mqtt_topic_out);
  }

  else if (input.indexOf("restart") > -1) {
    ESP.restart();
  }

  else if (input.indexOf("info") > -1) {
    Serial.println("Wifi enabled : " + String(wifi_enabled));
    Serial.println("SSID " + stored_ssid);
    Serial.println("MQTT server " + stored_mqtt_server);
    Serial.println("MQTT user " + stored_mqtt_user);
    Serial.println("MQTT enabled " + String(mqtt_enabled));
    Serial.println("Topic IN " + stored_mqtt_topic_in);
    Serial.println("Topic OUT " + stored_mqtt_topic_out);
    Serial.print("IP :");
    Serial.println(WiFi.getMode() == WIFI_AP ? WiFi.softAPIP()
                                             : WiFi.localIP());
  }

  else if (input.indexOf("help") > -1) {
    Serial.println("List of commands");
    Serial.println("- info              : print the saved variables");
    Serial.println("- restart           : restart the ESP");
    Serial.println("- wifi [0-1]        : enable/disable the WiFi");
    Serial.println("- ssid [text]       : SSID of the WiFi");
    Serial.println("- password [text]   : password of the WiFi");
    Serial.println("- mqtten [0-1]      : enable/disable the MQTT");
    Serial.println("- mqttserver [text]  : MQTT server IP");
    Serial.println("- mqttuser [text]    : MQTT username");
    Serial.println("- mqttpass [text]    : MQTT password");
    Serial.println("- topicin [text]     : MQTT input topic");
    Serial.println("- topicout [text]    : MQTT output topic");
    Serial.println("- {color [r-g-b-ir] : intensity [0-100]}");
  }

  // JSON LED command (starts with '{')
  else if (input.indexOf("{") > -1) {
    JSON_LED("serial", input);
  }
}