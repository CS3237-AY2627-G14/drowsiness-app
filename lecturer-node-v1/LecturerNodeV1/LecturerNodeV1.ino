#include <Arduino.h>
#include <ArduinoJson.h>

#include <WiFiMulti.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <cstring>

#include "ESP32MQTTClient.h"
#include "esp_idf_version.h"

#include "config.h"

WiFiMulti wifiMulti;


//Insert SSID and Password
const char *ssid = WIFI_SSID;
const char *pass = WIFI_PASSWORD;

#define LEDPIN 5
#define LEDCHANNEL 1
#define LEDFREQ 5000
#define LEDRESOLUTION 8
#define BUZZER_PIN 15 // The Arduino pin connected to the buzzer


// Replace 0x27 with your detected address
LiquidCrystal_I2C lcd(0x27, 16, 2);

uint32_t delayMS;

const char *server = MQTT_URI; //Set to your Base's IP address

const char *subscribeTopic = "drowsy/lect/result"; //Topic Name (Important!)

volatile bool alarmRequested = false;

char pendingId[1280] = {};
int pendingCount = 0;
bool displayRequested = false;
bool firstSnapshot = true;
portMUX_TYPE idMux = portMUX_INITIALIZER_UNLOCKED;
ESP32MQTTClient mqttClient; 

void setup() {

  log_i();
  log_i("setup, ESP.getSdkVersion(): ");
  log_i("%s", ESP.getSdkVersion());

  mqttClient.enableDebuggingMessages();

  mqttClient.setURI(server);
  mqttClient.enableLastWillMessage("lwt", "I am going offline");
  mqttClient.setKeepAlive(30);
  mqttClient.setOnMessageCallback([](const std::string &topic, const std::string &payload) {
        log_i("Global callback: %s: %s", topic.c_str(), payload.c_str());
    });
  WiFi.begin(ssid, pass);
  WiFi.setHostname("c3test");
  mqttClient.loopStart();

  ledcAttachChannel(LEDPIN,LEDFREQ,LEDRESOLUTION,LEDCHANNEL);
  Wire.begin(21, 22);
  lcd.init();

}

void loop() {
  

    char idToDisplay[1280];
    int seatCount = 0;
    bool refreshDisplay = false;
    bool showAlarm = false;

    portENTER_CRITICAL(&idMux);
    if (displayRequested)
    {
    displayRequested = false;
    refreshDisplay = true;
    seatCount = pendingCount;
    memcpy(idToDisplay, pendingId, sizeof(idToDisplay));
    showAlarm = alarmRequested;
    alarmRequested = false;
    }
    portEXIT_CRITICAL(&idMux);

    static char displayedSeats[1280] = {};
    static int displayedCount = 0;
    static unsigned long lastPage = 0;
    static size_t page = 0;
    if (refreshDisplay) {
      snprintf(displayedSeats, sizeof(displayedSeats), "%s", idToDisplay);
      displayedCount = seatCount;
      page = 0;
      lastPage = 0;
    }
    if (refreshDisplay || millis() - lastPage >= 2000) {
      lastPage = millis();
      lcd.backlight();
      lcd.clear();
      lcd.setCursor(0, 0);
      if (!displayedCount) lcd.print("No drowsy seats");
      else {
        lcd.print("Drowsy: "); lcd.print(displayedCount);
        lcd.setCursor(0, 1);
        char line[17] = {};
        snprintf(line, sizeof(line), "%.16s", displayedSeats + page);
        lcd.print(line);
        page = page + 16 < strlen(displayedSeats) ? page + 16 : 0;
      }
    }
    if (showAlarm)
    {
      ledcWriteChannel(LEDCHANNEL, 15);
      tone(BUZZER_PIN, 392, 500);
      delay(100);
      ledcWriteChannel(LEDCHANNEL, 0);
      delay(100);
      ledcWriteChannel(LEDCHANNEL, 15);
      delay(100);
      ledcWriteChannel(LEDCHANNEL, 0);
      delay(100);
      ledcWriteChannel(LEDCHANNEL, 15);
      delay(100);
      ledcWriteChannel(LEDCHANNEL, 0);
      delay(500);


    }
   
}


void onMqttConnect(esp_mqtt_client_handle_t client)
{
    if (mqttClient.isMyTurn(client))
    {
        firstSnapshot = true;
        mqttClient.subscribe(subscribeTopic, [](const std::string &payload)
        {
            StaticJsonDocument<4096> doc;
            DeserializationError error = deserializeJson(doc, payload.c_str());

            if (error)
            {
                log_i("Invalid JSON: %s", error.c_str());
                return;
            }

            if (!doc["drowsy_seats"].is<JsonArray>()) return;
            static int previousSeats[250] = {};
            static size_t previousCount = 0;
            int seats[250] = {};
            size_t count = 0;
            bool added = false;
            char labels[1280] = {};
            for (JsonVariant value : doc["drowsy_seats"].as<JsonArray>()) {
              if (!value.is<int>() || value.as<int>() <= 0 || count >= 250) return;
              int seat = value.as<int>();
              bool found = false;
              for (size_t i = 0; i < previousCount; ++i) if (previousSeats[i] == seat) found = true;
              added = added || !found;
              seats[count++] = seat;
              size_t used = strlen(labels);
              snprintf(labels + used, sizeof(labels) - used, "%s%d", used ? "," : "", seat);
            }
            portENTER_CRITICAL(&idMux);
            snprintf(pendingId, sizeof(pendingId), "%s", labels);
            pendingCount = count;
            alarmRequested = alarmRequested || (added && !firstSnapshot);
            displayRequested = true;
            portEXIT_CRITICAL(&idMux);
            memcpy(previousSeats, seats, sizeof(seats));
            previousCount = count;
            firstSnapshot = false;
        });
    }
}

#if ESP_IDF_VERSION < ESP_IDF_VERSION_VAL(5, 0, 0)
esp_err_t handleMQTT(esp_mqtt_event_handle_t event)
{
    mqttClient.onEventCallback(event);
    return ESP_OK;
}
#else  // IDF CHECK
void handleMQTT(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    auto *event = static_cast<esp_mqtt_event_handle_t>(event_data);
    mqttClient.onEventCallback(event);
}
#endif 

//Buzzer code adapted from: https://arduinogetstarted.com/tutorials/arduino-piezo-buzzer
