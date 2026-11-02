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

WiFiMulti wifiMulti;


//Insert SSID and Password
const char *ssid = "Insert_SSID_here";
const char *pass = "Insert_Password_here";

#define LEDPIN 5
#define LEDCHANNEL 1
#define LEDFREQ 5000
#define LEDRESOLUTION 8
#define BUZZER_PIN 15 // The Arduino pin connected to the buzzer


// Replace 0x27 with your detected address
LiquidCrystal_I2C lcd(0x27, 16, 2);

uint32_t delayMS;

const char *server = "mqtt://IP_address_of_base:1883"; //Set to your Base's IP address

const char *subscribeTopic = "drowsy/result"; //Topic Name (Important!)

volatile bool alarmRequested = false;

char pendingId[10] = {};
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
  

    char idToDisplay[10];
    bool showAlarm = false;

    portENTER_CRITICAL(&idMux);
    if (alarmRequested)
    {
    memcpy(idToDisplay, pendingId, sizeof(idToDisplay));
    alarmRequested = false;
    showAlarm = true;
    }
    portEXIT_CRITICAL(&idMux);

    if (showAlarm)
    {
      lcd.backlight();  
      lcd.clear();                 // Replace lcd with your LCD object's name
      lcd.setCursor(0, 0);
      lcd.print("Seat Number:");
      lcd.setCursor(0, 1);
      lcd.print(idToDisplay);

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
      lcd.noBacklight();

    }
   
}


void onMqttConnect(esp_mqtt_client_handle_t client)
{
    if (mqttClient.isMyTurn(client))
    {
        mqttClient.subscribe(subscribeTopic, [](const std::string &payload)
        {
            StaticJsonDocument<128> doc;
            DeserializationError error = deserializeJson(doc, payload.c_str());

            if (error)
            {
                log_i("Invalid JSON: %s", error.c_str());
                return;
            }

            const char *id = doc["id"];
            if (id == nullptr || strlen(id) == 0 || strlen(id) > 5)
            {
                log_i("JSON does not accept char more than 5");
                return;
            }

            portENTER_CRITICAL(&idMux);
            snprintf(pendingId, sizeof(pendingId), "%s", id);
            alarmRequested = true;
            portEXIT_CRITICAL(&idMux);
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
