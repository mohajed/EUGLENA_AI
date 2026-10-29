// ═════════════════════════════════════════════════════════════════════════════
//  WiFi Initialization
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Attempt to connect to the stored WiFi network.
 * Falls back to Access Point mode if the connection fails within 15 seconds.
 * When connected, initializes the MQTT client.
 */
void wifi_init() {
  Serial.println("Connecting to : " + stored_ssid);
  WiFi.begin(stored_ssid.c_str(), stored_pass.c_str());

  // Wait up to 15 s for connection (30 × 500 ms)
  uint8_t timeout = 30;
  while (timeout && WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    timeout--;
  }

  if (WiFi.status() != WL_CONNECTED) {
    // Connection failed → create a local hotspot
    wificonnected = false;
    Serial.print("\n\nCreating Hotspot");
    WiFi.mode(WIFI_AP);
    delay(100);
    WiFi.softAPConfig(apIP, apIP, IPAddress(255, 255, 255, 0));
    WiFi.softAP(hostname);
  } else {
    // Connected → configure MQTT
    wificonnected = true;
    client.setServer(stored_mqtt_server.c_str(), 1883);
    client.setCallback(mqtt_callback);
  }

  // Start DNS server (captive portal redirect)
  dnsServer.start(DNS_PORT, "*", apIP);

  Serial.print("\nIP address : ");
  Serial.println(WiFi.getMode() == WIFI_AP ? WiFi.softAPIP() : WiFi.localIP());
}

// ═════════════════════════════════════════════════════════════════════════════
//  MQTT Loop
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Called every loop iteration.
 * Maintains the MQTT connection and processes incoming messages.
 */
void mqtt_loop() {
  if (wificonnected && mqtt_enabled) {
    if (!client.connected()) {
      reconnect();
      return;
    }
    client.loop();
  }
}

// ═════════════════════════════════════════════════════════════════════════════
//  MQTT Reconnect
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Non-blocking reconnection to the MQTT broker.
 * Retries every `mqtt_retry_delay` milliseconds to avoid blocking the loop.
 */
void reconnect() {
  if (millis() - last_millis > mqtt_retry_delay) {
    Serial.println("MQTT connection to : " + stored_mqtt_server);
    ESPUI.print(statusLabelId, "MQTT connection to : " + stored_mqtt_server);

    if (client.connect(hostname, stored_mqtt_user.c_str(),
                       stored_mqtt_pass.c_str())) {
      Serial.println("MQTT connected !");
      ESPUI.print(statusLabelId, "MQTT connected !");

      // Subscribe to the configured input topic
      client.subscribe(stored_mqtt_topic_in.c_str());
    } else {
      Serial.print("MQTT connection failed : ");
      Serial.println(client.state());
      Serial.println("Retry in 10 sec");
      ESPUI.print(statusLabelId, "MQTT connection failed !");
      last_millis = millis();
    }
  }
}