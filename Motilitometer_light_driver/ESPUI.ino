// ═════════════════════════════════════════════════════════════════════════════
//  ESPUI – Web Interface Initialization
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Build and start the ESPUI web interface.
 * Creates three tabs: LED (continuous), Pulse (timed), and WiFi (settings).
 * A hidden DEBUG tab shows serial traffic and MQTT status.
 */
void espui_init() {
  ESPUI.setVerbosity(Verbosity::Quiet);

  // ── LED tab ── Continuous intensity sliders for each channel ───────────
  auto ledtab = ESPUI.addControl(Tab, "", "LED");

  auto r_slider =
      ESPUI.addControl(Slider, "Red", "0", Alizarin, ledtab, SliderCallback);
  ESPUI.addControl(Min, "", "0", None, r_slider);
  ESPUI.addControl(Max, "", String(PWMRANGE), None, r_slider);

  auto g_slider =
      ESPUI.addControl(Slider, "Green", "0", Emerald, ledtab, SliderCallback);
  ESPUI.addControl(Min, "", "0", None, g_slider);
  ESPUI.addControl(Max, "", String(PWMRANGE), None, g_slider);

  auto b_slider =
      ESPUI.addControl(Slider, "Blue", "0", Peterriver, ledtab, SliderCallback);
  ESPUI.addControl(Min, "", "0", None, b_slider);
  ESPUI.addControl(Max, "", String(PWMRANGE), None, b_slider);

  auto w_slider =
      ESPUI.addControl(Slider, "White", "0", Sunflower, ledtab, SliderCallback);
  ESPUI.addControl(Min, "", "0", None, w_slider);
  ESPUI.addControl(Max, "", String(PWMRANGE), None, w_slider);

  auto ir_slider =
      ESPUI.addControl(Slider, "IR", "0", Dark, ledtab, SliderCallback);
  ESPUI.addControl(Min, "", "0", None, ir_slider);
  ESPUI.addControl(Max, "", String(PWMRANGE), None, ir_slider);

  // ── Pulse tab ── Timed flash with configurable RGBW intensity ─────────
  auto pulsetab = ESPUI.addControl(Tab, "", "Pulse");

  pulse_r_slider =
      ESPUI.addControl(Slider, "Red", "0", Alizarin, pulsetab, textCallback);
  ESPUI.addControl(Min, "", "0", None, pulse_r_slider);
  ESPUI.addControl(Max, "", String(PWMRANGE), None, pulse_r_slider);

  pulse_g_slider =
      ESPUI.addControl(Slider, "Green", "0", Emerald, pulsetab, textCallback);
  ESPUI.addControl(Min, "", "0", None, pulse_g_slider);
  ESPUI.addControl(Max, "", String(PWMRANGE), None, pulse_g_slider);

  pulse_b_slider =
      ESPUI.addControl(Slider, "Blue", "0", Peterriver, pulsetab, textCallback);
  ESPUI.addControl(Min, "", "0", None, pulse_b_slider);
  ESPUI.addControl(Max, "", String(PWMRANGE), None, pulse_b_slider);

  pulse_w_slider =
      ESPUI.addControl(Slider, "White", "0", Sunflower, pulsetab, textCallback);
  ESPUI.addControl(Min, "", "0", None, pulse_w_slider);
  ESPUI.addControl(Max, "", String(PWMRANGE), None, pulse_w_slider);

  pulse_dur_in = ESPUI.addControl(Number, "Duration (ms)", "100", Dark,
                                  pulsetab, textCallback);
  ESPUI.addControl(Min, "", "0", None, pulse_dur_in);

  ESPUI.addControl(Button, "Pulse", "Pulse", Dark, pulsetab, PulseCallback);

  // ── WiFi / MQTT settings tab ──────────────────────────────────────────
  auto wifitab = ESPUI.addControl(Tab, "", "WiFi");

  wifi_ssid_text = ESPUI.addControl(Text, "SSID", stored_ssid, Alizarin,
                                    wifitab, textCallback);
  ESPUI.addControl(Max, "", "32", None, wifi_ssid_text);

  wifi_pass_text = ESPUI.addControl(Text, "Password", stored_pass, Alizarin,
                                    wifitab, textCallback);
  ESPUI.setInputType(wifi_pass_text, "password");
  ESPUI.addControl(Max, "", "64", None, wifi_pass_text);

  mqtt_server_text = ESPUI.addControl(Text, "MQTT server", stored_mqtt_server,
                                      Alizarin, wifitab, textCallback);
  mqtt_user_text = ESPUI.addControl(Text, "MQTT user", stored_mqtt_user,
                                    Alizarin, wifitab, textCallback);
  mqtt_pass_text = ESPUI.addControl(Text, "MQTT password", stored_mqtt_pass,
                                    Alizarin, wifitab, textCallback);
  ESPUI.setInputType(mqtt_pass_text, "password");
  mqtt_enabled_switch =
      ESPUI.addControl(Switcher, "Enable MQTT", String(mqtt_enabled), Alizarin,
                       wifitab, textCallback);
  mqtt_topic_in_text =
      ESPUI.addControl(Text, "MQTT topic IN", stored_mqtt_topic_in, Alizarin,
                       wifitab, textCallback);
  mqtt_topic_out_text =
      ESPUI.addControl(Text, "MQTT topic OUT", stored_mqtt_topic_out, Alizarin,
                       wifitab, textCallback);

  auto wifisave = ESPUI.addControl(Button, "Save", "Save", Peterriver, wifitab,
                                   SaveWifiDetailsCallback);
  auto espreset =
      ESPUI.addControl(Button, "", "Reboot ESP", None, wifisave, ESPReset);

  // Enable all settings controls
  ESPUI.setEnabled(wifi_ssid_text, true);
  ESPUI.setEnabled(wifi_pass_text, true);
  ESPUI.setEnabled(mqtt_server_text, true);
  ESPUI.setEnabled(mqtt_user_text, true);
  ESPUI.setEnabled(mqtt_pass_text, true);
  ESPUI.setEnabled(mqtt_topic_in_text, true);
  ESPUI.setEnabled(mqtt_topic_out_text, true);
  ESPUI.setEnabled(mqtt_enabled_switch, true);
  ESPUI.setEnabled(wifisave, true);
  ESPUI.setEnabled(espreset, true);

  // ── Debug tab ── Shows serial and MQTT status ─────────────────────────
  auto debugtab = ESPUI.addControl(Tab, "", "DEBUG");
  serialLabelId = ESPUI.addControl(Label, "Serial", "Serial IN", Peterriver,
                                   debugtab, textCallback);
  statusLabelId = ESPUI.addControl(Label, "", "Serial OUT", Peterriver,
                                   serialLabelId, textCallback);

  // Start the web server
  ESPUI.begin(hostname);
}