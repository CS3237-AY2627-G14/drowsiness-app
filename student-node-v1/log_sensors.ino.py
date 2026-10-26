// CS3237 Team 14 "Wakey Wakey" - ESP32 student node
//
// Does two jobs at the same time, using millis() timers (no delay()):
//   1. ALERT:    listens on wakey/<NODE_ID>/alert. When the laptop's drowsiness
//                detector publishes "1", the LED blinks and the buzzer beeps
//                for 5 seconds. Otherwise silent.
//   2. PRESENCE: reads the VL53L0X ToF and the FSR every 200 ms, decides whether
//                a student is in the seat, and publishes
//                {"tof":85,"fsr":2310,"present":1} to wakey/<NODE_ID>/sensors
//                every second and straight away when "present" changes.
//
// Libraries (Library Manager): ESP32MQTTClient, Adafruit_VL53L0X
// Board: DOIT ESP32 DEVKIT V1
//
// Wiring:
//   LED            long leg -> 220 ohm -> GPIO 14, short leg -> GND
//   Buzzer module  S -> GPIO 25, middle -> 3.3 V, - -> GND   (kit Active Buzzer)
//   VL53L0X        VIN -> 3.3 V, GND -> GND, SDA -> GPIO 21, SCL -> GPIO 22
//   FSR            one leg -> 3.3 V, other leg -> GPIO 34 AND 10k resistor -> GND

#include <WiFi.h>
#include <Wire.h>
#include <Adafruit_VL53L0X.h>
#include "ESP32MQTTClient.h"
#include "esp_idf_version.h"

// ---------- Settings to change ----------
const char *ssid = "gajin";
const char *pass = "jin123456";
// Laptop running Mosquitto (ipconfig -> IPv4 Address). Same WiFi as the ESP32.
const char *server = "mqtt://192.168.137.1:1883";
#define NODE_ID "student1"

#define BUZZER_PASSIVE 0  // 0 = kit "Active Buzzer", 1 = kit "Passive Buzzer"
#define FSR_INVERT 0      // 1 if the FSR reads HIGH when nobody sits (wired reversed)

// ---------- Pins ----------
const int LED_PIN = 14;
const int BUZZER_PIN = 25;
const int FSR_PIN = 34;     // ADC1 pin: ADC2 pins do not work while WiFi is on

// ---------- Alert timing ----------
const unsigned long ALERT_MS = 5000;   // alert lasts 5 s
const unsigned long BLINK_MS = 1000;   // LED + buzzer switch every 1 s

// ---------- Presence settings ----------
const int TOF_NEAR_MM = 50;                // ToF closer than this = someone there
const int FSR_PRESSED = 2000;              // FSR above this = someone sitting
const unsigned long PRESENT_ON_MS = 2000;  // must look present for 2 s to switch on
const unsigned long PRESENT_OFF_MS = 2000; // must look empty for 2 s to switch off
const unsigned long SENSOR_MS = 200;       // read sensors every 200 ms
const unsigned long PUBLISH_MS = 1000;     // publish every 1 s

const char alertTopic[] = "wakey/" NODE_ID "/alert";
const char sensorsTopic[] = "wakey/" NODE_ID "/sensors";

ESP32MQTTClient mqttClient;
Adafruit_VL53L0X tof;
bool tofOk = false;

// Alert state. alertRequested is set by the MQTT task and read by loop().
// Never drive pins from the MQTT callback itself: it runs on a different task.
volatile bool alertRequested = false;
bool alerting = false;
bool blinkOn = false;
unsigned long alertStart = 0;
unsigned long lastBlink = 0;

// Presence state
int tofMm = -1;            // -1 = no valid reading
int fsrValue = 0;
bool present = false;
bool lastRaw = false;
unsigned long rawSince = 0;
unsigned long lastSensor = 0;
unsigned long lastPublish = 0;

// ================= Alert (LED + buzzer) =================

void buzzer(bool on) {
#if BUZZER_PASSIVE
  if (on) tone(BUZZER_PIN, 2000);
  else noTone(BUZZER_PIN);
#else
  digitalWrite(BUZZER_PIN, on ? HIGH : LOW);
#endif
}

void setOutputs(bool on) {
  digitalWrite(LED_PIN, on ? HIGH : LOW);
  buzzer(on);
}

void startAlert() {
  // A new alert while one is running restarts the 5 s window.
  alerting = true;
  alertStart = millis();
  lastBlink = alertStart;
  blinkOn = true;
  setOutputs(true);
  Serial.println("Drowsiness alert: blinking for 5 s");
}

void updateAlert() {
  if (!alerting) return;
  unsigned long now = millis();
  if (now - alertStart >= ALERT_MS) {
    alerting = false;
    blinkOn = false;
    setOutputs(false);
    Serial.println("Alert finished");
    return;
  }
  if (now - lastBlink >= BLINK_MS) {
    lastBlink = now;
    blinkOn = !blinkOn;
    setOutputs(blinkOn);
  }
}

// ================= Presence (ToF + FSR) =================

void publishSensors() {
  if (!mqttClient.isConnected()) return;
  char json[64];
  snprintf(json, sizeof(json), "{\"tof\":%d,\"fsr\":%d,\"present\":%d}",
           tofMm, fsrValue, present ? 1 : 0);
  mqttClient.publish(sensorsTopic, json, 0, false);
}

void readSensors() {
  // ToF: distance in mm, or -1 if out of range / not connected
  tofMm = -1;
  if (tofOk) {
    VL53L0X_RangingMeasurementData_t m;
    tof.rangingTest(&m, false);
    // Only trust status 0 (valid). 8190/8191 mean "nothing in range".
    if (m.RangeStatus == 0 && m.RangeMilliMeter > 0 && m.RangeMilliMeter < 8000) {
      tofMm = m.RangeMilliMeter;
    }
  }

  // FSR: 0..4095
  fsrValue = analogRead(FSR_PIN);
#if FSR_INVERT
  fsrValue = 4095 - fsrValue;
#endif

  // "raw" = what the sensors say right now
  bool raw = (tofMm >= 0 && tofMm < TOF_NEAR_MM) && fsrValue > FSR_PRESSED;
  unsigned long now = millis();
  if (raw != lastRaw) {
    lastRaw = raw;
    rawSince = now;
  }

  // Only change "present" once the raw reading has held long enough,
  // so a quick shuffle or a hand passing the ToF doesn't flip it.
  bool changed = false;
  if (raw && !present && now - rawSince >= PRESENT_ON_MS) {
    present = true;
    changed = true;
  } else if (!raw && present && now - rawSince >= PRESENT_OFF_MS) {
    present = false;
    changed = true;
  }

  if (changed) {
    Serial.printf("Present: %s (tof=%d mm, fsr=%d)\n", present ? "YES" : "no", tofMm, fsrValue);
    publishSensors();          // tell the laptop straight away
    lastPublish = now;
  }
}

// ================= setup / loop =================

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(FSR_PIN, INPUT);
  setOutputs(false);

  Wire.begin(21, 22);
  tofOk = tof.begin();
  if (!tofOk) Serial.println("VL53L0X not found, using FSR only");

  mqttClient.enableDebuggingMessages();
  mqttClient.setURI(server);
  mqttClient.setKeepAlive(30);
  WiFi.begin(ssid, pass);
  mqttClient.loopStart();
}

void loop() {
  unsigned long now = millis();

  // Job 1: alert
  if (alertRequested) {
    alertRequested = false;
    startAlert();
  }
  updateAlert();

  // Job 2: presence
  if (now - lastSensor >= SENSOR_MS) {
    lastSensor = now;
    readSensors();
  }
  if (now - lastPublish >= PUBLISH_MS) {
    lastPublish = now;
    publishSensors();
  }
}

// Called by the library when it connects (and reconnects) to the broker.
void onMqttConnect(esp_mqtt_client_handle_t client) {
  if (mqttClient.isMyTurn(client)) {
    mqttClient.subscribe(alertTopic, [](const std::string &payload) {
      Serial.printf("%s: %s\n", alertTopic, payload.c_str());
      if (payload == "1") alertRequested = true;
    });
  }
}

#if ESP_IDF_VERSION < ESP_IDF_VERSION_VAL(5, 0, 0)
esp_err_t handleMQTT(esp_mqtt_event_handle_t event) {
  mqttClient.onEventCallback(event);
  return ESP_OK;
}
#else
void handleMQTT(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data) {
  (void)base;
  (void)event_id;
  auto *client = static_cast<ESP32MQTTClient *>(handler_args);
  auto *event = static_cast<esp_mqtt_event_handle_t>(event_data);
  client->onEventCallback(event);
}
#endif
