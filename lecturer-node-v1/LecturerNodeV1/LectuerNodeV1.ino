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

const char *ssid = "insert_SSID";
const char *pass = "insert_Password";

#define LEDPIN 5
#define LEDCHANNEL 1
#define LEDFREQ 5000
#define LEDRESOLUTION 8
#define BUZZER_PIN 15

LiquidCrystal_I2C lcd(0x27, 16, 2);

const char *server = "mqtt://Base_Node_IP:1883";
const char *subscribeTopic = "drowsy/result";

constexpr size_t ID_LIST_CAPACITY = 96;
constexpr uint32_t LCD_SCROLL_INTERVAL_MS = 500;
constexpr uint32_t ALARM_PHASE_MS = 150;

struct DisplayData
{
    int numberStudents = 0;
    char ids[ID_LIST_CAPACITY] = {};
};

DisplayData pendingData;
portMUX_TYPE dataMux = portMUX_INITIALIZER_UNLOCKED;
bool updatePending = false;
ESP32MQTTClient mqttClient;

DisplayData displayData;
size_t scrollOffset = 0;
uint32_t lastScrollAt = 0;
bool alarmActive = false;
uint8_t alarmPhase = 0;
uint32_t alarmPhaseStartedAt = 0;

bool appendId(JsonVariant value, char *destination, size_t capacity, size_t &length)
{
    char numberBuffer[24];
    const char *text = value.as<const char *>();

    if (text == nullptr)
    {
        if (value.is<long>())
        {
            snprintf(numberBuffer, sizeof(numberBuffer), "%ld", value.as<long>());
        }
        else if (value.is<unsigned long>())
        {
            snprintf(numberBuffer, sizeof(numberBuffer), "%lu", value.as<unsigned long>());
        }
        else
        {
            return false;
        }
        text = numberBuffer;
    }

    const size_t textLength = strlen(text);
    const size_t separatorLength = length == 0 ? 0 : 2;
    if (length + separatorLength + textLength >= capacity)
    {
        return false;
    }

    if (separatorLength != 0)
    {
        destination[length++] = ',';
        destination[length++] = ' ';
    }
    memcpy(destination + length, text, textLength);
    length += textLength;
    destination[length] = '\0';
    return true;
}

void renderLcd(const DisplayData &data)
{
    char topLine[17];
    snprintf(topLine, sizeof(topLine), "Drowsy: %d", data.numberStudents);
    lcd.setCursor(0, 0);
    lcd.print(topLine);
    for (size_t i = strlen(topLine); i < 16; ++i)
    {
        lcd.print(' ');
    }

    const char *ids = data.ids[0] == '\0' ? "No IDs reported" : data.ids;
    const size_t idsLength = strlen(ids);
    lcd.setCursor(0, 1);

    if (idsLength <= 16)
    {
        lcd.print(ids);
        for (size_t i = idsLength; i < 16; ++i)
        {
            lcd.print(' ');
        }
        return;
    }

    const size_t cycleLength = idsLength + 3;
    for (size_t i = 0; i < 16; ++i)
    {
        const size_t position = (scrollOffset + i) % cycleLength;
        lcd.print(position < idsLength ? ids[position] : ' ');
    }
}

void startAlarm()
{
    alarmActive = true;
    alarmPhase = 0;
    alarmPhaseStartedAt = millis();
    ledcWriteChannel(LEDCHANNEL, 15);
    tone(BUZZER_PIN, 392);
}

void updateAlarm()
{
    if (!alarmActive || millis() - alarmPhaseStartedAt < ALARM_PHASE_MS)
    {
        return;
    }

    alarmPhaseStartedAt = millis();
    ++alarmPhase;
    if (alarmPhase >= 6)
    {
        alarmActive = false;
        ledcWriteChannel(LEDCHANNEL, 0);
        noTone(BUZZER_PIN);
        return;
    }

    if (alarmPhase % 2 == 0)
    {
        ledcWriteChannel(LEDCHANNEL, 15);
        tone(BUZZER_PIN, 392);
    }
    else
    {
        ledcWriteChannel(LEDCHANNEL, 0);
        noTone(BUZZER_PIN);
    }
}

void setup()
{
    Serial.begin(115200);

    mqttClient.enableDebuggingMessages();
    mqttClient.setURI(server);
    mqttClient.enableLastWillMessage("lwt", "I am going offline");
    mqttClient.setKeepAlive(30);

    WiFi.begin(ssid, pass);
    WiFi.setHostname("c3test");
    mqttClient.loopStart();

    ledcAttachChannel(LEDPIN, LEDFREQ, LEDRESOLUTION, LEDCHANNEL);
    ledcWriteChannel(LEDCHANNEL, 0);
    Wire.begin(21, 22);
    lcd.init();
    lcd.backlight();
    renderLcd(displayData);
}

void loop()
{
    bool hasNewData = false;

    portENTER_CRITICAL(&dataMux);
    if (updatePending)
    {
        displayData = pendingData;
        updatePending = false;
        hasNewData = true;
    }
    portEXIT_CRITICAL(&dataMux);

    if (hasNewData)
    {
        scrollOffset = 0;
        renderLcd(displayData);
        startAlarm();
    }

    const uint32_t now = millis();
    if (strlen(displayData.ids) > 16 && now - lastScrollAt >= LCD_SCROLL_INTERVAL_MS)
    {
        lastScrollAt = now;
        ++scrollOffset;
        renderLcd(displayData);
    }

    updateAlarm();
    delay(1);
}

void onMqttConnect(esp_mqtt_client_handle_t client)
{
    if (mqttClient.isMyTurn(client))
    {
        mqttClient.subscribe(subscribeTopic, [](const std::string &payload)
        {
            StaticJsonDocument<512> doc;
            const DeserializationError error = deserializeJson(doc, payload.c_str());
            if (error)
            {
                log_i("Invalid JSON: %s", error.c_str());
                return;
            }

            if (!doc["number_students"].is<int>() || doc["number_students"].as<int>() < 0)
            {
                log_i("JSON must contain a non-negative integer 'number_students'");
                return;
            }
            if (doc["id"].isNull())
            {
                log_i("JSON does not contain 'id'");
                return;
            }

            DisplayData newData;
            newData.numberStudents = doc["number_students"].as<int>();
            size_t idsLength = 0;
            bool validIds = true;

            if (doc["id"].is<JsonArray>())
            {
                for (JsonVariant id : doc["id"].as<JsonArray>())
                {
                    if (!appendId(id, newData.ids, sizeof(newData.ids), idsLength))
                    {
                        validIds = false;
                        break;
                    }
                }
            }
            else
            {
                validIds = appendId(doc["id"], newData.ids, sizeof(newData.ids), idsLength);
            }

            if (!validIds)
            {
                log_i("'id' must be a string, number, or an array of strings/numbers that fits the display buffer");
                return;
            }

            portENTER_CRITICAL(&dataMux);
            pendingData = newData;
            updatePending = true;
            portEXIT_CRITICAL(&dataMux);
        });
    }
}

#if ESP_IDF_VERSION < ESP_IDF_VERSION_VAL(5, 0, 0)
esp_err_t handleMQTT(esp_mqtt_event_handle_t event)
{
    mqttClient.onEventCallback(event);
    return ESP_OK;
}
#else
void handleMQTT(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    auto *event = static_cast<esp_mqtt_event_handle_t>(event_data);
    mqttClient.onEventCallback(event);
}
#endif
