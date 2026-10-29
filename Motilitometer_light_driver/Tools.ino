// ═════════════════════════════════════════════════════════════════════════════
//  Persistent Storage
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Load all user settings from non-volatile storage (Preferences).
 * Provides sensible defaults on first boot.
 */
void load_memory() {
  wifi_enabled = preferences.getBool("wifi_enabled", false);
  stored_ssid = preferences.getString("ssid", "SSID");
  stored_pass = preferences.getString("pass", "PASSWORD");
  stored_mqtt_server = preferences.getString("mqtt_server", "192.168.1.10");
  stored_mqtt_user = preferences.getString("mqtt_user", "");
  stored_mqtt_pass = preferences.getString("mqtt_pass", "");
  stored_mqtt_topic_in = preferences.getString("mqtt_topic_in", "light_driver");
  stored_mqtt_topic_out =
      preferences.getString("mqtt_topic_out", "light_driver_feedback");
  mqtt_enabled = preferences.getBool("mqtt_enabled", false);
}

// ═════════════════════════════════════════════════════════════════════════════
//  String Utilities
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Split a string by a separator and return the token at the given index.
 *
 * @param data       Input string to split.
 * @param separator  Delimiter character.
 * @param index      Zero-based index of the desired token.
 * @return           The token at `index`, or "" if not found.
 */
String splitString(String data, char separator, int index) {
  int found = 0;
  int strIndex[] = {0, -1};
  int maxIndex = data.length() - 1;

  for (int i = 0; i <= maxIndex && found <= index; i++) {
    if (data.charAt(i) == separator || i == maxIndex) {
      found++;
      strIndex[0] = strIndex[1] + 1;
      strIndex[1] = (i == maxIndex) ? i + 1 : i;
    }
  }
  return found > index ? data.substring(strIndex[0], strIndex[1]) : "";
}