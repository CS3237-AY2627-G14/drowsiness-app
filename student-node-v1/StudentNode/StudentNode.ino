// Libraries (Library Manager): ESP32MQTTClient, Adafruit_VL53L0X, ArduinoJson
// Board: DOIT ESP32 DEVKIT V1
//
// Wiring:
//   LED            long leg -> 220 ohm -> GPIO 14, short leg -> GND
//   Buzzer module  S -> GPIO 25, middle -> 3.3 V, - -> GND   (kit Active Buzzer)
//   Ultrasonic     VCC -> VIN (5 V), GND -> GND, Trig -> GPIO 26,
//   HC-SR04        Echo -> 1k -> GPIO 27, and GPIO 27 -> 2k -> GND
//   ToF VL53L0X    VIN -> 3.3 V, GND -> GND, SDA -> GPIO 21, SCL -> GPIO 22
//   FSR backrest   one leg -> 3.3 V, other leg -> GPIO 34 AND 10k -> GND
//   FSR desk       one leg -> 3.3 V, other leg -> GPIO 35 AND 10k -> GND

#include <ArduinoJson.h>
#include <WiFi.h>
#include <Wire.h>
#include <Adafruit_VL53L0X.h>
#include "ESP32MQTTClient.h"
#include "esp_idf_version.h"

// ---------- Settings to change ----------
#include "config.h"
#include <esp_random.h>
const char *ssid = WIFI_SSID;
const char *pass = WIFI_PASSWORD;
const char *server = MQTT_URI;
char bootId[33];
uint32_t rawSequence = 0, previousUptime = 0;
uint64_t uptimeEpoch = 0;

#define BUZZER_PASSIVE 0  // 0 = kit "Active Buzzer", 1 = kit "Passive Buzzer"
#define DEBUG 1           // 1 = print all sensor readings to Serial Monitor every 0.5 s, 0 = off

// ---------- Pins ----------
const int LED_PIN = 14;
const int BUZZER_PIN = 25;
const int US_TRIG_PIN = 26;
const int US_ECHO_PIN = 27;
const int FSR_BACK_PIN = 34;   // ADC1 pins only (32-39): ADC2 stops working with WiFi
const int FSR_DESK_PIN = 35;

// ---------- Alert timing ----------
const unsigned long ALERT_MS = 5000;   // alert lasts 5 s
const unsigned long BLINK_MS = 1000;   // LED + buzzer switch every 1 s

// ---------- Timing ----------
const unsigned long SENSOR_MS = 200;    // read sensors every 200 ms
const unsigned long PUBLISH_MS = 200;
const unsigned long DEBUG_MS = 500;     // debug print every 0.5 s

// ---------- Sleep mode ----------
// present = ToF sees something closer than PRESENT_MM (same 300 mm the API uses).
// After nobody is present for SLEEP_AFTER_MS, the node stops reading the other
// sensors and stops sending to MQTT. It only checks the ToF until someone sits
// down again, then wakes up and sends immediately.
const int PRESENT_MM = 300;
const unsigned long SLEEP_AFTER_MS = 15000;   // 15 s

const char alertTopic[] = "drowsy/stud/" SEAT_ID "/result";
const char dataTopic[] = "drowsy/stud/" SEAT_ID "/data";

ESP32MQTTClient mqttClient;
Adafruit_VL53L0X tof;
bool tofOk = false;

// Alert state. Flags set by the MQTT task are read by loop().
// Never drive pins from the MQTT callback itself: it runs on a different task.
volatile bool alertRequested = false;
bool alerting = false;
bool blinkOn = false;
unsigned long alertStart = 0;
unsigned long lastBlink = 0;

// Sensor readings
int upperCm = -1;    // ultrasonic, -1 = no echo
int lowerMm = -1;    // ToF, -1 = out of range
int backValue = 0;
int deskValue = 0;
unsigned long ultrasonicPulseUs = 0;

unsigned long lastSensor = 0;
unsigned long lastPublish = 0;
unsigned long lastDebug = 0;

bool sleeping = false;
unsigned long lastPresentMs = 0;   // last time present = 1

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

// ================= Sensors =================

int readUltrasonicCm() {
  digitalWrite(US_TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(US_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(US_TRIG_PIN, LOW);
  ultrasonicPulseUs = pulseIn(US_ECHO_PIN, HIGH, 30000);  // give up after 30 ms
  if (ultrasonicPulseUs == 0) return -1;
  return (int)(ultrasonicPulseUs * 0.0343 / 2);
}

int readTofMm() {
  if (!tofOk) return -1;
  VL53L0X_RangingMeasurementData_t m;
  tof.rangingTest(&m, false);
  // Only trust status 0 (valid). 8190/8191 mean "nothing in range".
  if (m.RangeStatus == 0 && m.RangeMilliMeter > 0 && m.RangeMilliMeter < 8000) {
    return m.RangeMilliMeter;
  }
  return -1;
}

void printDebug() {
  if (sleeping) {
    Serial.printf("SLEEPING (no MQTT) | lower=%4d mm\n", lowerMm);
    return;
  }
  Serial.printf("upper=%4d cm (echo=%5lu us) | lower=%4d mm | back=%4d | desk=%4d\n",
                upperCm, ultrasonicPulseUs, lowerMm, backValue, deskValue);
}

void publishData() {
  if (!mqttClient.isConnected()) return;
  uint32_t currentUptime = millis();
  if (currentUptime < previousUptime) uptimeEpoch += (1ULL << 32);
  previousUptime = currentUptime;
  char upper[16], lower[16], json[320];
  if (upperCm < 0) snprintf(upper, sizeof(upper), "null");
  else snprintf(upper, sizeof(upper), "%d", upperCm);
  if (lowerMm < 0) snprintf(lower, sizeof(lower), "null");
  else snprintf(lower, sizeof(lower), "%d", lowerMm);
  snprintf(json, sizeof(json),
    "{\"schema_version\":1,\"boot_id\":\"%s\",\"sequence\":%lu,\"uptime_ms\":%llu,"
    "\"upper_cm\":%s,\"lower_mm\":%s,\"back_adc\":%d,\"desk_adc\":%d}",
    bootId, (unsigned long)rawSequence++,
    (unsigned long long)(uptimeEpoch + currentUptime), upper, lower, backValue, deskValue);
  mqttClient.publish(dataTopic, json, 0, false);
}

bool isPresent() {
  return lowerMm >= 0 && lowerMm < PRESENT_MM;
}

void readSensors() {
  lowerMm = readTofMm();   // ToF is always read: it decides sleep / wake
  if (sleeping) return;    // asleep: skip the other sensors
  upperCm = readUltrasonicCm();
  backValue = analogRead(FSR_BACK_PIN);
  deskValue = analogRead(FSR_DESK_PIN);
}

void updateSleep(unsigned long now) {
  if (isPresent()) {
    lastPresentMs = now;
    if (sleeping) {
      sleeping = false;
      Serial.println("Present again: waking up, sending data");
      readSensors();       // fresh readings of all sensors
      publishData();       // send straight away
      lastPublish = now;
    }
  } else if (!sleeping && now - lastPresentMs >= SLEEP_AFTER_MS) {
    sleeping = true;
    Serial.println("Not present for 15 s: sleep mode, MQTT sending stopped");
  }
}

// ================= setup / loop =================

void setup() {
  Serial.begin(115200);
  snprintf(bootId, sizeof(bootId), "%08lx%08lx", (unsigned long)esp_random(), (unsigned long)esp_random());
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(US_TRIG_PIN, OUTPUT);
  pinMode(US_ECHO_PIN, INPUT);
  pinMode(FSR_BACK_PIN, INPUT);
  pinMode(FSR_DESK_PIN, INPUT);
  setOutputs(false);
  lastPresentMs = millis();   // start awake, sleep only after 15 s with nobody

  Wire.begin(21, 22);
  tofOk = tof.begin();
  if (!tofOk) Serial.println("VL53L0X not found: publishing invalid ToF readings");

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

  // Job 2: sensors and state
  if (now - lastSensor >= SENSOR_MS) {
    lastSensor = now;
    readSensors();
    updateSleep(now);
  }
  if (!sleeping && now - lastPublish >= PUBLISH_MS) {
    lastPublish = now;
    publishData();
  }

#if DEBUG
  if (now - lastDebug >= DEBUG_MS) {
    lastDebug = now;
    printDebug();
  }
#endif
}

// Called by the library when it connects (and reconnects) to the broker.
void onMqttConnect(esp_mqtt_client_handle_t client) {
  if (mqttClient.isMyTurn(client)) {
    mqttClient.subscribe(alertTopic, [](const std::string &payload) {
      Serial.printf("%s: %s\n", alertTopic, payload.c_str());
      StaticJsonDocument<256> doc;
      DeserializationError error = deserializeJson(doc, payload.c_str());
      if (error || !doc["drowsy"].is<bool>()) return;

      static bool previousDrowsy = false;
      bool drowsy = doc["drowsy"].as<bool>();
      if (drowsy && !previousDrowsy) alertRequested = true;
      previousDrowsy = drowsy;
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
