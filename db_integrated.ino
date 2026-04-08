#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_TSL2561_U.h>

/* ================= PIN DEFINITIONS ================= */
#define ACS_PIN 34
#define VOLTAGE_PIN 35
#define SMOKE_PIN 32
#define BUZZER_PIN 27

/* I2C pins */
#define SDA_PIN 21
#define SCL_PIN 22

/* ================= CONSTANTS ================= */
#define ADC_RESOLUTION 4095.0
#define VREF 3.3

// ACS712 20A
#define SENSITIVITY 0.100

// Voltage sensor (0–25V module)
#define VOLTAGE_DIVIDER_RATIO 5.0

#define LOW_VOLTAGE_THRESHOLD 8.0

// Connection retry settings
#define MAX_RETRIES 3
#define RETRY_DELAY_MS 1000
#define WIFI_TIMEOUT_MS 10000

/* ================= WIFI CONFIG ================= */
const char* WIFI_SSID = "Ragav";
const char* WIFI_PASS = "Ragava2005";

/* ================= INFLUXDB CLOUD CONFIG ================= */
const char* INFLUX_URL    = "https://us-east-1-1.aws.cloud2.influxdata.com";
const char* INFLUX_TOKEN  = "hYZBGB-mapCPMBK79c65hGsf6TSnKy_Eb-4WhQhI0GzZ5VCIWjKJkG7FZkSwWn5xdnV5AESz_Zdd_5ZEX60qqQ==";
const char* INFLUX_ORG    = "Dev%20Team";
const char* INFLUX_BUCKET = "electrolyser";
const char* MEASUREMENT   = "power_monitor";

/* ================= GLOBALS ================= */
float zeroOffset = 0;
Adafruit_TSL2561_Unified tsl = Adafruit_TSL2561_Unified(TSL2561_ADDR_FLOAT, 12345);

// Persistent connection objects (prevent memory leak)
WiFiClientSecure secureClient;
unsigned long lastSuccessfulSend = 0;
int consecutiveFailures = 0;

/* ================= SETUP ================= */
void setup() {
  Serial.begin(115200);
  delay(1000);

  analogReadResolution(12);

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  /* WiFi */
  connectWiFi();

  /* I2C */
  Wire.begin(SDA_PIN, SCL_PIN);

  /* TSL2561 */
  if (!tsl.begin()) {
    Serial.println("❌ TSL2561 not detected");
    while (1);
  }

  tsl.enableAutoRange(true);
  tsl.setIntegrationTime(TSL2561_INTEGRATIONTIME_402MS);
  Serial.println("✅ TSL2561 initialized");

  /* ACS712 calibration */
  Serial.println("Calibrating ACS712... Ensure NO current flow");
  delay(2000);
  zeroOffset = calibrateZeroOffset();
  Serial.print("Zero Offset: ");
  Serial.println(zeroOffset, 4);

  /* Setup secure client */
  secureClient.setInsecure();  // Skip SSL verification
  secureClient.setTimeout(10);  // 10 second timeout

  Serial.println("✅ Setup complete - Starting data collection...\n");
}

/* ================= WIFI CONNECTION ================= */
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.print("Connecting to WiFi");
  WiFi.disconnect(true);
  delay(100);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long startTime = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startTime < WIFI_TIMEOUT_MS) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi connected");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n❌ WiFi connection failed");
  }
}

/* ================= LOOP ================= */
void loop() {
  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi disconnected, reconnecting...");
    connectWiFi();
  }

  float voltage = readDCVoltage();
  float current = readDCCurrent();
  int smokeADC = readSmokeADC();
  float smokeVoltage = (smokeADC / ADC_RESOLUTION) * VREF;

  /* Read Lux */
  sensors_event_t event;
  tsl.getEvent(&event);

  float lux = 0;
  if (event.light) {
    lux = event.light;
  }

  /* Serial output */
  Serial.print("V: "); Serial.print(voltage, 2); Serial.print("V | ");
  Serial.print("I: "); Serial.print(current, 3); Serial.print("A | ");
  Serial.print("Smoke: "); Serial.print(smokeADC);
  Serial.print(" | Lux: "); Serial.print(lux, 1);
  Serial.print(" | Heap: "); Serial.print(ESP.getFreeHeap());
  Serial.println();

  /* Buzzer alert */
  if (voltage < LOW_VOLTAGE_THRESHOLD) {
    beepBuzzer(2, 150);
  }

  /* Send to InfluxDB Cloud with retry */
  bool success = sendToInfluxWithRetry(voltage, current, smokeADC, smokeVoltage, lux);
  
  if (success) {
    consecutiveFailures = 0;
    lastSuccessfulSend = millis();
  } else {
    consecutiveFailures++;
    
    // If too many failures, reset the connection
    if (consecutiveFailures >= 5) {
      Serial.println("⚠️ Too many failures, resetting connection...");
      secureClient.stop();
      delay(1000);
      consecutiveFailures = 0;
    }
  }

  delay(1000);
}

/* ================= INFLUXDB WITH RETRY ================= */
bool sendToInfluxWithRetry(float voltage, float current,
                            int smokeADC, float smokeVoltage,
                            float lux) {
  
  for (int attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    if (sendToInflux(voltage, current, smokeADC, smokeVoltage, lux)) {
      return true;
    }
    
    if (attempt < MAX_RETRIES) {
      Serial.printf("⏳ Retry %d/%d in %dms...\n", attempt, MAX_RETRIES, RETRY_DELAY_MS);
      delay(RETRY_DELAY_MS);
    }
  }
  
  return false;
}

/* ================= INFLUXDB CLOUD ================= */
bool sendToInflux(float voltage, float current,
                  int smokeADC, float smokeVoltage,
                  float lux) {

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("❌ WiFi not connected!");
    return false;
  }

  HTTPClient http;

  // Build URL
  String url = String(INFLUX_URL) +
               "/api/v2/write?org=" + INFLUX_ORG +
               "&bucket=" + INFLUX_BUCKET +
               "&precision=s";

  // Use persistent secure client
  if (!http.begin(secureClient, url)) {
    Serial.println("❌ HTTP begin failed");
    return false;
  }

  http.addHeader("Authorization", String("Token ") + INFLUX_TOKEN);
  http.addHeader("Content-Type", "text/plain");
  http.addHeader("Connection", "keep-alive");  // Reuse connection
  http.setTimeout(10000);

  // InfluxDB Line Protocol format
  String data =
    String(MEASUREMENT) + ",device=esp32_1 " +
    "voltage=" + String(voltage, 2) + "," +
    "current=" + String(current, 3) + "," +
    "smoke_adc=" + String(smokeADC) + "," +
    "smoke_voltage=" + String(smokeVoltage, 2) + "," +
    "lux=" + String(lux, 1);

  int code = http.POST(data);
  
  // Important: Always end the connection properly
  http.end();

  if (code == 204) {
    Serial.println("✅ InfluxDB: OK");
    return true;
  } else if (code > 0) {
    Serial.printf("❌ HTTP error: %d\n", code);
    return false;
  } else {
    Serial.printf("❌ Connection error: %s\n", http.errorToString(code).c_str());
    
    // Force close on connection errors
    secureClient.stop();
    delay(100);
    
    return false;
  }
}

/* ================= ACS712 ================= */
float calibrateZeroOffset() {
  int samples = 1000;
  float sum = 0;

  for (int i = 0; i < samples; i++) {
    int adc = analogRead(ACS_PIN);
    float v = (adc / ADC_RESOLUTION) * VREF;
    sum += v;
    delay(2);
  }
  return sum / samples;
}

float readDCCurrent() {
  int samples = 200;
  float sum = 0;

  for (int i = 0; i < samples; i++) {
    int adc = analogRead(ACS_PIN);
    float v = (adc / ADC_RESOLUTION) * VREF;
    sum += v;
    delay(2);
  }

  float avgV = sum / samples;
  float current = (avgV - zeroOffset) / SENSITIVITY;
  if (abs(current) < 0.03) current = 0;
  return current;
}

/* ================= VOLTAGE ================= */
float readDCVoltage() {
  int samples = 200;
  float sum = 0;

  for (int i = 0; i < samples; i++) {
    int adc = analogRead(VOLTAGE_PIN);
    float v = (adc / ADC_RESOLUTION) * VREF;
    sum += v;
    delay(2);
  }
  return (sum / samples) * VOLTAGE_DIVIDER_RATIO;
}

/* ================= SMOKE ================= */
int readSmokeADC() {
  int samples = 100;
  long sum = 0;

  for (int i = 0; i < samples; i++) {
    sum += analogRead(SMOKE_PIN);
    delay(2);
  }
  return sum / samples;
}

/* ================= BUZZER ================= */
void beepBuzzer(int times, int durationMs) {
  for (int i = 0; i < times; i++) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(durationMs);
    digitalWrite(BUZZER_PIN, LOW);
    delay(durationMs);
  }
}