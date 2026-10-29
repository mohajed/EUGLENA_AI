// ═════════════════════════════════════════════════════════════════════════════
//  LED Control Functions
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Visual self-test: ramps a single LED channel up then down.
 * Used at boot to confirm wiring and PWM output.
 *
 * @param LED  GPIO pin number of the channel to test.
 */
void test_LED(int LED) {
  Serial.printf("Testing channel %d\n", LED);
  for (int i = 0; i < PWMRANGE; i += 20) {
    analogWrite(LED, i);
    delay(5);
  }
  delay(100);
  for (int i = PWMRANGE; i > 0; i -= 20) {
    analogWrite(LED, i);
    delay(5);
  }
  analogWrite(LED, 0);
}

/**
 * Set a single LED channel to a given intensity and store the value
 * so it can be restored after a pulse.
 *
 * @param LED        GPIO pin number of the channel.
 * @param intensity  PWM duty cycle (0 – PWMRANGE).
 */
void set_LED(int LED, int intensity) {
  Serial.printf("Setting channel %d to %d\n", LED, intensity);
  analogWrite(LED, intensity);

  // Remember current intensity for post-pulse restoration
  switch (LED) {
  case Red:
    R_int = intensity;
    break;
  case Green:
    G_int = intensity;
    break;
  case Blue:
    B_int = intensity;
    break;
  case White:
    W_int = intensity;
    break;
  case IR:
    IR_int = intensity;
    break;
  }
}

/**
 * Emit a timed flash (pulse) on RGBW channels, then restore previous values.
 *
 * @param duration     Pulse length in ms (or µs if microsecond == true).
 * @param R, G, B, W   Intensity for each channel during the pulse.
 * @param microsecond  If true, use delayMicroseconds instead of delay.
 */
void pulse_LED(int duration, int R, int G, int B, int W, bool microsecond) {
  Serial.printf("Pulse of %d ms of R : %d G : %d B : %d W : %d\n", duration, R,
                G, B, W);

  // Apply pulse intensities
  analogWrite(Red, R);
  analogWrite(Green, G);
  analogWrite(Blue, B);
  analogWrite(White, W);

  // Wait for the requested duration
  if (microsecond) {
    delayMicroseconds(duration);
  } else {
    delay(duration);
  }

  // Restore previous intensities
  analogWrite(Red, R_int);
  analogWrite(Green, G_int);
  analogWrite(Blue, B_int);
  analogWrite(White, W_int);

  pulse_flag = false;
}

// ═════════════════════════════════════════════════════════════════════════════
//  JSON LED Command Parser
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Parse a JSON payload and apply LED commands.
 *
 * Supported JSON keys:
 *   - "r", "g", "b", "w", "ir"  → set continuous intensity
 *   - "pulse"                    → timed flash duration (ms)
 *   - "microsecond"              → if true, pulse duration is in µs
 *
 * Examples:
 *   {"r":500, "g":0, "b":200, "w":0}
 *   {"pulse":100, "r":1000, "g":0, "b":0, "w":0}
 *
 * @param topic    Source identifier (e.g. "serial", MQTT topic).
 * @param payload  JSON string to parse.
 */
void JSON_LED(String topic, String payload) {
  deserializeJson(CMD, payload);
  Serial.println(payload);

  if (CMD.containsKey("pulse")) {
    // Pulse mode: flash RGBW for the specified duration
    int Pulse_dur = CMD["pulse"];
    int R = CMD["r"];
    int G = CMD["g"];
    int B = CMD["b"];
    int W = CMD["w"];
    bool microsecond =
        CMD.containsKey("microsecond") ? bool(CMD["microsecond"]) : false;
    pulse_LED(Pulse_dur, R, G, B, W, microsecond);
  } else {
    // Continuous mode: set each channel independently
    if (CMD.containsKey("r")) {
      set_LED(Red, CMD["r"]);
    }
    if (CMD.containsKey("g")) {
      set_LED(Green, CMD["g"]);
    }
    if (CMD.containsKey("b")) {
      set_LED(Blue, CMD["b"]);
    }
    if (CMD.containsKey("w")) {
      set_LED(White, CMD["w"]);
    }
    if (CMD.containsKey("ir")) {
      set_LED(IR, CMD["ir"]);
    }
  }
}