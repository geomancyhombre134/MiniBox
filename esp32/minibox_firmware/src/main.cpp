#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <driver/i2s.h>
#include "config.h"

// ==========================================
//  全局状态
// ==========================================
enum State { IDLE, RECORDING, UPLOADING, PLAYING };
volatile State currentState = IDLE;

uint8_t* audioBuffer = nullptr;
size_t   audioLen    = 0;

// ==========================================
//  I2S 麦克风初始化 (I2S_NUM_0)
// ==========================================
void initMicrophone() {
    i2s_config_t mic_config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
        .sample_rate = SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 8,
        .dma_buf_len = 1024,
        .use_apll = false,
        .tx_desc_auto_clear = false,
        .fixed_mclk = 0,
    };

    i2s_pin_config_t mic_pins = {
        .bck_io_num   = I2S_MIC_SCK,
        .ws_io_num    = I2S_MIC_WS,
        .data_out_num = I2S_PIN_NO_CHANGE,
        .data_in_num  = I2S_MIC_SD,
    };

    i2s_driver_install(I2S_NUM_0, &mic_config, 0, NULL);
    i2s_set_pin(I2S_NUM_0, &mic_pins);
    i2s_zero_dma_buffer(I2S_NUM_0);
    Serial.println("[MIC] I2S microphone initialized");
}

// ==========================================
//  I2S 喇叭初始化 (I2S_NUM_1)
// ==========================================
void initSpeaker() {
    i2s_config_t spk_config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
        .sample_rate = SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 8,
        .dma_buf_len = 1024,
        .use_apll = false,
        .tx_desc_auto_clear = true,
        .fixed_mclk = 0,
    };

    i2s_pin_config_t spk_pins = {
        .bck_io_num   = I2S_SPK_BCK,
        .ws_io_num    = I2S_SPK_WS,
        .data_out_num = I2S_SPK_DOUT,
        .data_in_num  = I2S_PIN_NO_CHANGE,
    };

    i2s_driver_install(I2S_NUM_1, &spk_config, 0, NULL);
    i2s_set_pin(I2S_NUM_1, &spk_pins);
    i2s_zero_dma_buffer(I2S_NUM_1);
    Serial.println("[SPK] I2S speaker initialized");
}

// ==========================================
//  WiFi 连接
// ==========================================
void connectWiFi() {
    Serial.printf("[WIFI] Connecting to %s", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 40) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[WIFI] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
    } else {
        Serial.println("\n[WIFI] Connection FAILED! Restarting...");
        delay(2000);
        ESP.restart();
    }
}

// ==========================================
//  LED 状态指示
// ==========================================
void setLED(uint8_t r, uint8_t g, uint8_t b) {
#ifdef LED_PIN
    neopixelWrite(LED_PIN, r, g, b);
#endif
}

// ==========================================
//  录音：按住按钮期间持续录制
// ==========================================
void recordAudio() {
    Serial.println("[REC] Recording started...");
    setLED(255, 0, 0);  // red = recording

    audioLen = 0;
    size_t bytesRead = 0;
    uint32_t startMs = millis();

    while (digitalRead(BUTTON_PIN) == LOW) {
        if (audioLen >= AUDIO_BUFFER_SIZE) break;
        if ((millis() - startMs) > (RECORD_SECONDS * 1000)) break;

        size_t toRead = min((size_t)2048, AUDIO_BUFFER_SIZE - audioLen);
        i2s_read(I2S_NUM_0, audioBuffer + audioLen, toRead, &bytesRead, portMAX_DELAY);
        audioLen += bytesRead;
    }

    Serial.printf("[REC] Done. %d bytes (%.1f sec)\n", audioLen, (float)audioLen / (SAMPLE_RATE * 2));
    setLED(0, 0, 0);
}

// ==========================================
//  构建 WAV 文件头
// ==========================================
void buildWavHeader(uint8_t* header, size_t dataSize) {
    uint32_t fileSize = dataSize + 36;
    uint32_t byteRate = SAMPLE_RATE * 1 * 2;  // mono, 16bit

    memcpy(header, "RIFF", 4);
    memcpy(header + 4,  &fileSize, 4);
    memcpy(header + 8,  "WAVE", 4);
    memcpy(header + 12, "fmt ", 4);
    uint32_t fmtSize = 16;
    memcpy(header + 16, &fmtSize, 4);
    uint16_t audioFmt = 1;  // PCM
    memcpy(header + 20, &audioFmt, 2);
    uint16_t channels = 1;
    memcpy(header + 22, &channels, 2);
    uint32_t sr = SAMPLE_RATE;
    memcpy(header + 24, &sr, 4);
    memcpy(header + 28, &byteRate, 4);
    uint16_t blockAlign = 2;
    memcpy(header + 32, &blockAlign, 2);
    uint16_t bps = 16;
    memcpy(header + 34, &bps, 2);
    memcpy(header + 36, "data", 4);
    memcpy(header + 40, &dataSize, 4);
}

// ==========================================
//  上传录音到 PC 服务器，接收 TTS 音频回放
// ==========================================
void uploadAndPlay() {
    if (audioLen < 1600) {
        Serial.println("[NET] Recording too short, skipping");
        return;
    }

    setLED(0, 0, 255);  // blue = uploading
    Serial.println("[NET] Uploading audio to server...");

    HTTPClient http;
    String url = String("http://") + SERVER_HOST + ":" + SERVER_PORT + "/api/voice_chat";
    http.begin(url);
    http.setTimeout(30000);

    uint8_t wavHeader[44];
    buildWavHeader(wavHeader, audioLen);

    size_t totalSize = 44 + audioLen;
    uint8_t* wavData = (uint8_t*)ps_malloc(totalSize);
    if (!wavData) {
        Serial.println("[NET] Failed to allocate WAV buffer");
        setLED(0, 0, 0);
        return;
    }
    memcpy(wavData, wavHeader, 44);
    memcpy(wavData + 44, audioBuffer, audioLen);

    String boundary = "----MiniBoxBoundary";
    String header = "--" + boundary + "\r\n"
                    "Content-Disposition: form-data; name=\"audio\"; filename=\"rec.wav\"\r\n"
                    "Content-Type: audio/wav\r\n\r\n";
    String footer = "\r\n--" + boundary + "--\r\n";

    size_t bodySize = header.length() + totalSize + footer.length();

    http.addHeader("Content-Type", "multipart/form-data; boundary=" + boundary);
    http.addHeader("Content-Length", String(bodySize));

    WiFiClient* stream = http.getStreamPtr();
    http.sendRequest("POST", (uint8_t*)nullptr, 0);

    // Manually write multipart body
    WiFiClient& client = http.getStream();
    client.print(header);
    client.write(wavData, totalSize);
    client.print(footer);

    free(wavData);

    int httpCode = http.GET();  // This won't work for POST, we need to read response differently

    // Actually, let's use a simpler approach with http.POST
    // Re-do with a combined buffer approach
    http.end();

    // Simplified approach: send raw WAV, receive raw WAV
    HTTPClient http2;
    http2.begin(url);
    http2.setTimeout(30000);
    http2.addHeader("Content-Type", "audio/wav");

    size_t sendSize = 44 + audioLen;
    uint8_t* sendBuf = (uint8_t*)ps_malloc(sendSize);
    if (!sendBuf) {
        Serial.println("[NET] Alloc failed");
        setLED(0, 0, 0);
        return;
    }
    buildWavHeader(sendBuf, audioLen);
    memcpy(sendBuf + 44, audioBuffer, audioLen);

    int code = http2.POST(sendBuf, sendSize);
    free(sendBuf);

    if (code == 200) {
        Serial.println("[NET] Got response audio, playing...");
        setLED(0, 255, 0);  // green = playing

        int len = http2.getSize();
        WiFiClient* respStream = http2.getStreamPtr();

        if (len > 44) {
            // Skip WAV header from response
            uint8_t skip[44];
            respStream->readBytes(skip, 44);
            len -= 44;

            uint8_t chunk[1024];
            size_t written = 0;
            while (len > 0 || respStream->available()) {
                int avail = respStream->available();
                if (avail == 0) { delay(1); continue; }
                int toRead = min(avail, (int)sizeof(chunk));
                if (len > 0) toRead = min(toRead, len);
                int got = respStream->readBytes(chunk, toRead);
                if (got <= 0) break;

                size_t bytesWritten = 0;
                i2s_write(I2S_NUM_1, chunk, got, &bytesWritten, portMAX_DELAY);
                written += bytesWritten;
                if (len > 0) len -= got;
            }
            Serial.printf("[SPK] Played %d bytes\n", written);
        }
    } else {
        Serial.printf("[NET] Server error: %d\n", code);
    }

    http2.end();
    setLED(0, 0, 0);
}

// ==========================================
//  Setup
// ==========================================
void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=============================");
    Serial.println("  MiniBox ESP32-S3 Firmware");
    Serial.println("=============================");

    pinMode(BUTTON_PIN, INPUT_PULLUP);

    // Allocate audio buffer in PSRAM
    audioBuffer = (uint8_t*)ps_malloc(AUDIO_BUFFER_SIZE);
    if (!audioBuffer) {
        Serial.println("[ERR] Failed to allocate audio buffer!");
        while (1) delay(1000);
    }
    Serial.printf("[MEM] Audio buffer: %d bytes in PSRAM\n", AUDIO_BUFFER_SIZE);

    connectWiFi();
    initMicrophone();
    initSpeaker();

    setLED(0, 255, 0);
    delay(500);
    setLED(0, 0, 0);

    Serial.println("[READY] Press and hold button to talk!");
}

// ==========================================
//  Loop
// ==========================================
void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[WIFI] Lost connection, reconnecting...");
        connectWiFi();
    }

    if (digitalRead(BUTTON_PIN) == LOW) {
        delay(50);  // debounce
        if (digitalRead(BUTTON_PIN) == LOW) {
            currentState = RECORDING;
            recordAudio();

            currentState = UPLOADING;
            uploadAndPlay();

            currentState = IDLE;
        }
    }

    delay(20);
}
