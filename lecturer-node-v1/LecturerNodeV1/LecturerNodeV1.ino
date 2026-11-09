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

const char *ssid = WIFI_SSID;
const char *pass = WIFI_PASSWORD;

#define LEDPIN 5
#define LEDCHANNEL 1
#define LEDFREQ 5000
#define LEDRESOLUTION 8
#define BUZZER_PIN 15

LiquidCrystal_I2C lcd(0x27, 16, 2);

const char *server = MQTT_URI;
const char *subscribeTopic = "lect/result";

constexpr size_t ID_LIST_CAPACITY = 1280;
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
bool alarmPending = false;
// Owned by the MQTT callback; invalid messages do not establish a baseline.
bool initialSnapshotPending = true;
ESP32MQTTClient mqttClient;

DisplayData displayData;
size_t scrollOffset = 0;
uint32_t lastScrollAt = 0;
bool alarmActive = false;
uint8_t alarmPhase = 0;
uint32_t alarmPhaseStartedAt = 0;

bool appendId(JsonVariant value, char *destination, size_t capacity, size_t &length)
{
    const char *text = value.as<const char *>();
    if (text == nullptr || *text == '\0') return false;
    for (const char *character = text; *character; ++character)
    {
        if (!((*character >= 'A' && *character <= 'Z') ||
              (*character >= 'a' && *character <= 'z') ||
              (*character >= '0' && *character <= '9'))) return false;
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

bool hasAddedSeats(const DisplayData &previousData, const DisplayData &newData)
{
    const char *newId = newData.ids;
    while (*newId != '\0')
    {
        const size_t newLength = strcspn(newId, ",");
        const char *previousId = previousData.ids;
        bool found = false;
        while (*previousId != '\0')
        {
            const size_t previousLength = strcspn(previousId, ",");
            if (newLength == previousLength && strncmp(newId, previousId, newLength) == 0)
            {
                found = true;
                break;
            }
            previousId += previousLength;
            if (*previousId != '\0')
            {
                previousId += 2;
            }
        }
        if (!found)
        {
            return true;
        }
        newId += newLength;
        if (*newId != '\0')
        {
            newId += 2;
        }
    }
    return false;
}

void queueDisplayData(const DisplayData &newData)
{
    // Only the MQTT callback writes pendingData; loop() only copies it.
    const bool shouldAlarm = !initialSnapshotPending && hasAddedSeats(pendingData, newData);
    initialSnapshotPending = false;
    if (newData.numberStudents == pendingData.numberStudents && strcmp(newData.ids, pendingData.ids) == 0)
    {
        return;
    }

    portENTER_CRITICAL(&dataMux);
    pendingData = newData;
    updatePending = true;
    alarmPending = alarmPending || shouldAlarm;
    portEXIT_CRITICAL(&dataMux);
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
    bool shouldAlarm = false;

    portENTER_CRITICAL(&dataMux);
    if (updatePending)
    {
        displayData = pendingData;
        updatePending = false;
        hasNewData = true;
        shouldAlarm = alarmPending;
        alarmPending = false;
    }
    portEXIT_CRITICAL(&dataMux);

    if (hasNewData)
    {
        scrollOffset = 0;
        lastScrollAt = millis();
        renderLcd(displayData);
        if (shouldAlarm)
        {
            startAlarm();
        }
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
        initialSnapshotPending = true;
        portENTER_CRITICAL(&dataMux);
        alarmPending = false;
        portEXIT_CRITICAL(&dataMux);
        mqttClient.subscribe(subscribeTopic, [](const std::string &payload)
        {
            StaticJsonDocument<4096> doc;
            const DeserializationError error = deserializeJson(doc, payload.c_str());
            if (error)
            {
                log_i("Invalid JSON: %s", error.c_str());
                return;
            }

            if (!doc["drowsy_seats"].is<JsonArray>())
            {
                log_i("JSON must contain a 'drowsy_seats' array");
                return;
            }

            DisplayData newData;
            size_t idsLength = 0;
            for (JsonVariant id : doc["drowsy_seats"].as<JsonArray>())
            {
                if (!appendId(id, newData.ids, sizeof(newData.ids), idsLength))
                {
                    log_i("Invalid seat ID or display buffer exceeded");
                    return;
                }
                ++newData.numberStudents;
            }

            queueDisplayData(newData);
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
