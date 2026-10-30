// CS3237 Team 14 "Wakey Wakey" - ESP32 student node (4 sensors)
//
// Does two jobs at the same time, using millis() timers:
//   1. ALERT:  listens on drowsy/<NODE_ID>/alert. When the laptop publishes "1",
//              the LED blinks and the buzzer beeps for 5 seconds.
//   2. STATE:  reads 4 sensors every 200 ms, works out "present" and "drowsy"
//              from the team's truth table, and publishes to drowsy/<NODE_ID>/data:
//              {"present":1,"drowsy":0}     drowsy: 1 = drowsy, 0 = not drowsy, -1 = no result
//              every second, and straight away when present or drowsy changes.
//
// The team's truth table is written out row by row in ROW_RESULT below (rows 1-28).
//
// Desk levels are measured against a fixed base (DESK_BASE = 1500).
//
// Libraries (Library Manager): ESP32MQTTClient, Adafruit_VL53L0X
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

// ---------- Placeholder thresholds: tune with sensor_test_4 ----------
const int US_LOW_MAX_CM = 5;       // upper distance below 6 cm (0-5)  -> Low (head near the chair top)
const int US_MED_MAX_CM = 9;       // upper distance 6-9 cm            -> Medium, 10 cm and up -> High
const int TOF_DETECT_MM = 300;     // lower distance < 300 mm  -> Detected (someone in the seat)
const int BACK_LOW_MAX = 0;        // backrest FSR = 0         -> Low (not leaning)
const int BACK_MED_MAX = 3000;     // backrest FSR 1-3000      -> Medium, above 3000 -> High
const int DESK_BASE = 1500;        // desk FSR base value
const int DESK_TOLERANCE = 500;    // 1000-2000 -> Close (light press), below 1000 -> Lower (not pressed),
                                   // above 2000 -> Higher (heavy press)

// ---------- Timing ----------
const unsigned long SENSOR_MS = 200;    // read sensors every 200 ms
const unsigned long PUBLISH_MS = 1000;  // publish every 1 s
const unsigned long DEBUG_MS = 500;     // debug print every 0.5 s

const char alertTopic[] = "drowsy/result";
const char dataTopic[] = "drowsy/" NODE_ID "/data";

enum Level { LOW_L, MED_L, HIGH_L };
enum DeskLevel { DESK_LOWER, DESK_CLOSE, DESK_HIGHER };
enum State { NO_RESULT, NOT_DROWSY, DROWSY };

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

// Outputs
bool present = false;
int row = 1;          // current truth-table row (1-28)
unsigned long lastSensor = 0;
unsigned long lastPublish = 0;
unsigned long lastDebug = 0;

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
  unsigned long us = pulseIn(US_ECHO_PIN, HIGH, 30000);  // give up after 30 ms
  if (us == 0) return -1;
  return (int)(us * 0.0343 / 2);
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

Level threeLevels(int value, int lowMax, int medMax) {
  if (value <= lowMax) return LOW_L;
  if (value <= medMax) return MED_L;
  return HIGH_L;
}

// ================= Truth table =================
//
//  #  | upper  | lower        | backrest | desk    | result
// ----+--------+--------------+----------+---------+-----------
//  1  | any    | Out-Of-Range | any      | any     | no result
//  2  | Low    | Detected     | Low      | Lower   | no result
//  3  | Medium | Detected     | Low      | Lower   | no result
//  4  | High   | Detected     | Low      | Lower   | no result
//  5  | Low    | Detected     | Medium   | Lower   | no result
//  6  | Medium | Detected     | Medium   | Lower   | no result
//  7  | High   | Detected     | Medium   | Lower   | no result
//  8  | Low    | Detected     | High     | Lower   | no result
//  9  | Medium | Detected     | High     | Lower   | no result
//  10 | High   | Detected     | High     | Lower   | no result
//  11 | Low    | Detected     | Low      | Close   | drowsy
//  12 | Medium | Detected     | Low      | Close   | drowsy
//  13 | High   | Detected     | Low      | Close   | drowsy
//  14 | Low    | Detected     | Medium   | Close   | not drowsy
//  15 | Medium | Detected     | Medium   | Close   | drowsy
//  16 | High   | Detected     | Medium   | Close   | drowsy
//  17 | Low    | Detected     | High     | Close   | not drowsy
//  18 | Medium | Detected     | High     | Close   | drowsy
//  19 | High   | Detected     | High     | Close   | drowsy
//  20 | Low    | Detected     | Low      | Higher  | not drowsy
//  21 | Medium | Detected     | Low      | Higher  | drowsy
//  22 | High   | Detected     | Low      | Higher  | drowsy
//  23 | Low    | Detected     | Medium   | Higher  | not drowsy
//  24 | Medium | Detected     | Medium   | Higher  | drowsy
//  25 | High   | Detected     | Medium   | Higher  | drowsyx
//  26 | Low    | Detected     | High     | Higher  | not drowsy
//  27 | Medium | Detected     | High     | Higher  | drowsy
//  28 | High   | Detected     | High     | Higher  | drowsy
//
// Change a result here if the team changes the table.
const State ROW_RESULT[29] = {
  NO_RESULT,                              // (index 0 unused)
  NO_RESULT,                              // 1
  NO_RESULT, NO_RESULT, NO_RESULT,        // 2, 3, 4
  NO_RESULT, NO_RESULT, NO_RESULT,        // 5, 6, 7
  NO_RESULT, NO_RESULT, NO_RESULT,        // 8, 9, 10
  DROWSY,     DROWSY, DROWSY,             // 11, 12, 13
  NOT_DROWSY, DROWSY, DROWSY,             // 14, 15, 16
  NOT_DROWSY, DROWSY, DROWSY,             // 17, 18, 19
  NOT_DROWSY, DROWSY, DROWSY,             // 20, 21, 22
  NOT_DROWSY, DROWSY, DROWSY,             // 23, 24, 25
  NOT_DROWSY, DROWSY, DROWSY,             // 26, 27, 28
};

Level upperLevel() {
  if (upperCm < 0) return LOW_L;  // no echo (-1) = Low
  return threeLevels(upperCm, US_LOW_MAX_CM, US_MED_MAX_CM);
}

Level backLevel() {
  return threeLevels(backValue, BACK_LOW_MAX, BACK_MED_MAX);
}

DeskLevel deskLevel() {
  int change = deskValue - DESK_BASE;
  if (change < -DESK_TOLERANCE) return DESK_LOWER;
  if (change > DESK_TOLERANCE) return DESK_HIGHER;
  return DESK_CLOSE;
}

bool tofDetected() {
  return lowerMm >= 0 && lowerMm < TOF_DETECT_MM;
}

// Which row of the table the current readings match (1-28)
int currentRow() {
  if (!tofDetected()) return 1;
  // Rows 2-28 go: desk (Lower, Close, Higher) -> backrest (Low, Medium, High) -> upper (Low, Medium, High)
  return 2 + deskLevel() * 9 + backLevel() * 3 + upperLevel();
}

// 1 = drowsy, 0 = not drowsy, -1 = no result
int drowsyValue(int r) {
  State st = ROW_RESULT[r];
  if (st == DROWSY) return 1;
  if (st == NOT_DROWSY) return 0;
  return -1;
}

// Same line as the sensor_test_4 sketch, plus the final present/drowsy
void printDebug() {
  const char *levelNames[] = {"Low", "Medium", "High"};
  const char *deskNames[] = {"Lower", "Close", "Higher"};
  Serial.printf("upper=%4d cm (%-6s) | lower=%4d mm (%-12s) | back=%4d (%-6s) | desk=%4d (%-6s) | row %2d -> present=%d drowsy=%d\n",
                upperCm, levelNames[upperLevel()], lowerMm, tofDetected() ? "Detected" : "Out-Of-Range",
                backValue, levelNames[backLevel()], deskValue, deskNames[deskLevel()],
                row, present ? 1 : 0, drowsyValue(row));
}

void publishData() {
  if (!mqttClient.isConnected()) return;
  char json[32];
  snprintf(json, sizeof(json), "{\"present\":%d,\"drowsy\":%d}",
           present ? 1 : 0, drowsyValue(row));
  mqttClient.publish(dataTopic, json, 0, false);
}

void readSensors() {
  upperCm = readUltrasonicCm();
  lowerMm = readTofMm();
  backValue = analogRead(FSR_BACK_PIN);
  deskValue = analogRead(FSR_DESK_PIN);

  // No delay: present and drowsy update on every reading (every 200 ms)
  int newRow = currentRow();
  bool newPresent = tofDetected();
  bool changed = (newPresent != present) || (drowsyValue(newRow) != drowsyValue(row));
  present = newPresent;
  row = newRow;

  if (changed) {
    publishData();          // tell the laptop straight away
    lastPublish = millis();
  }
}

// ================= setup / loop =================

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(US_TRIG_PIN, OUTPUT);
  pinMode(US_ECHO_PIN, INPUT);
  pinMode(FSR_BACK_PIN, INPUT);
  pinMode(FSR_DESK_PIN, INPUT);
  setOutputs(false);

  Wire.begin(21, 22);
  tofOk = tof.begin();
  if (!tofOk) Serial.println("VL53L0X not found: present will stay 0");

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
  }
  if (now - lastPublish >= PUBLISH_MS) {
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

    std::string compact = payload;
    compact.erase(
        std::remove_if(compact.begin(), compact.end(), [](unsigned char c) {
          return std::isspace(c);
        }),
        compact.end()
    );

    if (compact == "{\"id\":\"A1\"}") {
      alertRequested = true;
    }
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