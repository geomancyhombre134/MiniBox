#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <driver/i2s.h>
#include <driver/gpio.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "config.h"

// ==========================================
//  状态 & 表情
// ==========================================
enum State   { ST_SLEEPING, ST_WAKING, ST_IDLE, ST_LISTENING, ST_RECORDING, ST_UPLOADING, ST_SPEAKING };
enum Expr    { EX_SLEEP, EX_IDLE, EX_BLINK, EX_LISTEN, EX_RECORD, EX_THINK, EX_SPEAK_OPEN, EX_SPEAK_SHUT };

volatile State state = ST_SLEEPING;

// ==========================================
//  全局
// ==========================================
Adafruit_SSD1306 oled(SCREEN_W, SCREEN_H, &Wire, -1);
uint8_t* audioBuffer = nullptr;
size_t   audioLen     = 0;
uint8_t  volume       = VOL_DEFAULT;

uint32_t lastVoiceMs  = 0;
uint32_t lastAnimMs   = 0;
uint32_t lastBlinkMs  = 0;
uint8_t  animFrame    = 0;
bool     blinkNow     = false;

// 唤醒键中断标志
volatile bool wakeFlag = false;
void IRAM_ATTR onWakeISR() { wakeFlag = true; }

// 前向声明
void handleVolumeButtons();
void drawCharacter(Expr ex);
void drawScene(Expr ex, const char* l1, const char* l2 = nullptr);
void showVolOverlay();

// ==========================================
//  绘制角色（程序化像素风兔耳）
//  左侧 32×32 区域
// ==========================================
void drawCharacter(Expr ex) {
    // -- 脸 (填充白圆) --
    oled.fillCircle(15, 19, 11, SSD1306_WHITE);

    // -- 兔耳 (填充三角 + 内耳线) --
    oled.fillTriangle(2, 13, 7, 0, 12, 13, SSD1306_WHITE);
    oled.fillTriangle(18, 13, 23, 0, 28, 13, SSD1306_WHITE);
    oled.drawLine(5, 11, 7, 3, SSD1306_BLACK);
    oled.drawLine(9, 11, 7, 3, SSD1306_BLACK);
    oled.drawLine(21, 11, 23, 3, SSD1306_BLACK);
    oled.drawLine(25, 11, 23, 3, SSD1306_BLACK);

    // -- 眼睛 --
    switch (ex) {
    case EX_SLEEP:
    case EX_BLINK:
        oled.drawFastHLine(8, 17, 6, SSD1306_BLACK);
        oled.drawFastHLine(17, 17, 6, SSD1306_BLACK);
        break;
    case EX_LISTEN:
    case EX_RECORD:
        // 大闪亮眼
        oled.fillCircle(11, 16, 4, SSD1306_BLACK);
        oled.fillCircle(20, 16, 4, SSD1306_BLACK);
        oled.fillCircle(12, 15, 1, SSD1306_WHITE);
        oled.fillCircle(21, 15, 1, SSD1306_WHITE);
        oled.drawPixel(10, 14, SSD1306_WHITE);
        oled.drawPixel(19, 14, SSD1306_WHITE);
        break;
    case EX_THINK:
        // 眼睛看右上
        oled.fillCircle(11, 16, 3, SSD1306_BLACK);
        oled.fillCircle(20, 16, 3, SSD1306_BLACK);
        oled.fillCircle(13, 15, 1, SSD1306_WHITE);
        oled.fillCircle(22, 15, 1, SSD1306_WHITE);
        break;
    default: // IDLE, SPEAK_OPEN, SPEAK_SHUT
        oled.fillCircle(11, 16, 3, SSD1306_BLACK);
        oled.fillCircle(20, 16, 3, SSD1306_BLACK);
        oled.fillCircle(12, 15, 1, SSD1306_WHITE);
        oled.fillCircle(21, 15, 1, SSD1306_WHITE);
        break;
    }

    // -- 腮红 --
    if (ex != EX_SLEEP) {
        oled.drawFastHLine(5, 21, 3, SSD1306_BLACK);
        oled.drawFastHLine(23, 21, 3, SSD1306_BLACK);
    }

    // -- 嘴巴 --
    switch (ex) {
    case EX_SLEEP:
        oled.drawFastHLine(14, 24, 3, SSD1306_BLACK);
        break;
    case EX_SPEAK_OPEN:
        oled.fillCircle(15, 24, 2, SSD1306_BLACK);
        break;
    case EX_SPEAK_SHUT:
        oled.drawFastHLine(13, 24, 5, SSD1306_BLACK);
        break;
    case EX_LISTEN:
    case EX_RECORD:
        oled.drawCircle(15, 24, 1, SSD1306_BLACK);
        break;
    case EX_THINK:
        oled.drawPixel(13, 23, SSD1306_BLACK);
        oled.drawFastHLine(14, 24, 3, SSD1306_BLACK);
        oled.drawPixel(17, 25, SSD1306_BLACK);
        break;
    default: // IDLE, BLINK — 微笑
        oled.drawPixel(12, 23, SSD1306_BLACK);
        oled.drawFastHLine(13, 24, 5, SSD1306_BLACK);
        oled.drawPixel(18, 23, SSD1306_BLACK);
        break;
    }
}

// ==========================================
//  绘制整个场景：左角色 + 右状态
// ==========================================
void drawScene(Expr ex, const char* l1, const char* l2) {
    oled.clearDisplay();
    drawCharacter(ex);
    oled.setTextColor(SSD1306_WHITE);
    if (l1) {
        oled.setTextSize(1);
        oled.setCursor(36, 4);
        oled.print(l1);
    }
    if (l2) {
        oled.setTextSize(1);
        oled.setCursor(36, 18);
        oled.print(l2);
    }
    oled.display();
}

// ==========================================
//  各状态显示
// ==========================================
void showSleeping() {
    const char* zzz[] = {"z", "zZ", "zZz"};
    Expr ex = EX_SLEEP;
    oled.clearDisplay();
    drawCharacter(ex);
    oled.setTextSize(2);
    oled.setTextColor(SSD1306_WHITE);
    int xOff = 48 + (animFrame % 3) * 6;
    int yOff = 2 + (animFrame % 3) * 4;
    oled.setCursor(xOff, yOff);
    oled.print(zzz[animFrame % 3]);
    oled.display();
}

void showIdle() {
    bool blink = blinkNow && (millis() - lastBlinkMs < 150);
    oled.clearDisplay();
    drawCharacter(blink ? EX_BLINK : EX_IDLE);
    oled.setTextSize(1);
    oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(36, 2);
    oled.print("MiniBox");
    oled.setCursor(36, 14);
    oled.print("Ready~");
    // 小音量条
    char buf[10];
    snprintf(buf, sizeof(buf), "Vol:%d%%", volume);
    oled.setCursor(36, 25);
    oled.print(buf);
    oled.display();
}

void showListening() {
    oled.clearDisplay();
    drawCharacter(EX_LISTEN);
    oled.setTextSize(1);
    oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(36, 4);
    oled.print("Listening..");
    // 声波动画
    for (int i = 0; i < 5; i++) {
        int h = 3 + ((i + animFrame) % 4) * 3;
        oled.fillRect(38 + i * 11, 28 - h, 7, h, SSD1306_WHITE);
    }
    oled.display();
}

void showRecording() {
    oled.clearDisplay();
    drawCharacter(EX_RECORD);
    oled.setTextSize(1);
    oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(36, 2);
    oled.print("Recording");
    // 录音红点闪烁
    if (animFrame % 2 == 0)
        oled.fillCircle(100, 6, 3, SSD1306_WHITE);
    // 时长
    float sec = (float)audioLen / (SAMPLE_RATE * 2);
    char buf[12];
    snprintf(buf, sizeof(buf), "%.1fs", sec);
    oled.setCursor(36, 20);
    oled.print(buf);
    oled.display();
}

void showThinking() {
    oled.clearDisplay();
    drawCharacter(EX_THINK);
    oled.setTextSize(1);
    oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(36, 6);
    oled.print("Thinking");
    // 旋转点
    int dots = (animFrame % 4) + 1;
    oled.setCursor(36, 20);
    for (int i = 0; i < dots; i++) oled.print(". ");
    oled.display();
}

void showSpeaking() {
    bool open = (animFrame % 2 == 0);
    oled.clearDisplay();
    drawCharacter(open ? EX_SPEAK_OPEN : EX_SPEAK_SHUT);
    oled.setTextSize(1);
    oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(36, 4);
    oled.print("Speaking");
    // 音波
    for (int i = 0; i < 4; i++) {
        int h = open ? (6 + i * 3) : (3 + i * 2);
        oled.fillRect(40 + i * 14, 28 - h, 8, h, SSD1306_WHITE);
    }
    oled.display();
}

// ==========================================
//  音量覆盖层（短暂显示）
// ==========================================
void showVolOverlay() {
    oled.clearDisplay();
    drawCharacter(EX_IDLE);
    // 右侧大字音量
    oled.setTextSize(2);
    oled.setTextColor(SSD1306_WHITE);
    char buf[8];
    snprintf(buf, sizeof(buf), "%d%%", volume);
    oled.setCursor(40, 2);
    oled.print(buf);
    // 进度条
    oled.drawRect(36, 22, 88, 8, SSD1306_WHITE);
    int barW = map(volume, 0, 100, 0, 84);
    oled.fillRect(38, 24, barW, 4, SSD1306_WHITE);
    oled.display();
}

// ==========================================
//  LED
// ==========================================
void setLED(uint8_t r, uint8_t g, uint8_t b) {
    neopixelWrite(LED_PIN, r, g, b);
}

// ==========================================
//  I2S
// ==========================================
void initMicrophone() {
    i2s_config_t cfg = {
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
    i2s_pin_config_t pins = {
        .bck_io_num   = I2S_MIC_SCK,
        .ws_io_num    = I2S_MIC_WS,
        .data_out_num = I2S_PIN_NO_CHANGE,
        .data_in_num  = I2S_MIC_SD,
    };
    i2s_driver_install(I2S_NUM_0, &cfg, 0, NULL);
    i2s_set_pin(I2S_NUM_0, &pins);
    i2s_zero_dma_buffer(I2S_NUM_0);
}

void initSpeaker() {
    i2s_config_t cfg = {
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
    i2s_pin_config_t pins = {
        .bck_io_num   = I2S_SPK_BCK,
        .ws_io_num    = I2S_SPK_WS,
        .data_out_num = I2S_SPK_DOUT,
        .data_in_num  = I2S_PIN_NO_CHANGE,
    };
    i2s_driver_install(I2S_NUM_1, &cfg, 0, NULL);
    i2s_set_pin(I2S_NUM_1, &pins);
    i2s_zero_dma_buffer(I2S_NUM_1);
}

// ==========================================
//  WiFi
// ==========================================
void connectWiFi() {
    Serial.printf("[WIFI] Connecting to %s", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    int att = 0;
    while (WiFi.status() != WL_CONNECTED && att < 40) { delay(500); Serial.print("."); att++; }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[WIFI] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
    } else {
        Serial.println("\n[WIFI] FAILED! Restarting...");
        delay(2000);
        ESP.restart();
    }
}

// ==========================================
//  VAD: RMS 能量
// ==========================================
uint16_t calcRMS(int16_t* s, size_t n) {
    if (n == 0) return 0;
    uint64_t sum = 0;
    for (size_t i = 0; i < n; i++) { int32_t v = s[i]; sum += v * v; }
    return (uint16_t)sqrt((double)sum / n);
}

// ==========================================
//  麦克风增益放大
// ==========================================
void applyMicGain() {
    int16_t* samples = (int16_t*)audioBuffer;
    size_t n = audioLen / 2;
    for (size_t i = 0; i < n; i++) {
        int32_t val = (int32_t)samples[i] * MIC_GAIN;
        if (val > 32767) val = 32767;
        if (val < -32768) val = -32768;
        samples[i] = (int16_t)val;
    }
    Serial.printf("[GAIN] Applied x%d to %d samples\n", MIC_GAIN, n);
}

// ==========================================
//  WAV 头
// ==========================================
void buildWavHeader(uint8_t* h, size_t dataSize) {
    uint32_t fileSize = dataSize + 36;
    uint32_t byteRate = SAMPLE_RATE * 2;
    memcpy(h, "RIFF", 4);       memcpy(h+4, &fileSize, 4);
    memcpy(h+8, "WAVE", 4);     memcpy(h+12, "fmt ", 4);
    uint32_t fs=16;              memcpy(h+16, &fs, 4);
    uint16_t af=1;               memcpy(h+20, &af, 2);
    uint16_t ch=1;               memcpy(h+22, &ch, 2);
    uint32_t sr=SAMPLE_RATE;     memcpy(h+24, &sr, 4);
    memcpy(h+28, &byteRate, 4);
    uint16_t ba=2;               memcpy(h+32, &ba, 2);
    uint16_t bp=16;              memcpy(h+34, &bp, 2);
    memcpy(h+36, "data", 4);    memcpy(h+40, &dataSize, 4);
}

// ==========================================
//  上传 + 播放
// ==========================================
bool uploadAndPlay() {
    if (audioLen < 1600) { Serial.println("[NET] Too short"); return false; }
    state = ST_UPLOADING;
    setLED(0, 0, 255);
    showThinking();
    Serial.printf("[NET] Uploading %d bytes\n", audioLen);

    String url = String("http://") + SERVER_HOST + ":" + SERVER_PORT + "/esp32/voice_chat";
    size_t sendSize = 44 + audioLen;
    uint8_t* buf = (uint8_t*)ps_malloc(sendSize);
    if (!buf) { Serial.println("[NET] Alloc fail"); return false; }
    buildWavHeader(buf, audioLen);
    memcpy(buf + 44, audioBuffer, audioLen);

    HTTPClient http;
    http.begin(url);
    http.setTimeout(30000);
    http.addHeader("Content-Type", "audio/wav");
    int code = http.POST(buf, sendSize);
    free(buf);

    if (code == 200) {
        state = ST_SPEAKING;
        setLED(0, 255, 0);
        Serial.println("[NET] Playing...");
        int len = http.getSize();
        WiFiClient* stream = http.getStreamPtr();
        if (len > 44) {
            uint8_t skip[44]; stream->readBytes(skip, 44); len -= 44;
            uint8_t chunk[1024];
            size_t written = 0;
            uint32_t aMs = millis();
            while (len > 0 || stream->available()) {
                int avail = stream->available();
                if (avail == 0) { delay(1); continue; }
                int toRead = min(avail, (int)sizeof(chunk));
                if (len > 0) toRead = min(toRead, len);
                int got = stream->readBytes(chunk, toRead);
                if (got <= 0) break;
                if (volume < 100) {
                    int16_t* sam = (int16_t*)chunk;
                    for (int i = 0; i < got / 2; i++)
                        sam[i] = (int16_t)((int32_t)sam[i] * volume / 100);
                }
                size_t bw = 0;
                i2s_write(I2S_NUM_1, chunk, got, &bw, portMAX_DELAY);
                written += bw;
                if (len > 0) len -= got;
                if (millis() - aMs > 200) { animFrame++; showSpeaking(); aMs = millis(); }
            }
            Serial.printf("[SPK] %d bytes\n", written);
        }
        http.end(); setLED(0, 0, 0); return true;
    }
    Serial.printf("[NET] Error %d\n", code);
    http.end(); setLED(0, 0, 0); return false;
}

// ==========================================
//  检测唤醒键（中断 + 轮询双保险）
// ==========================================
bool checkWakeButton() {
    if (wakeFlag) {
        wakeFlag = false;
        delay(50);
        if (digitalRead(BTN_WAKE) == LOW) {
            while (digitalRead(BTN_WAKE) == LOW) delay(10);
            return true;
        }
    }
    if (digitalRead(BTN_WAKE) == LOW) {
        delay(50);
        if (digitalRead(BTN_WAKE) == LOW) {
            while (digitalRead(BTN_WAKE) == LOW) delay(10);
            return true;
        }
    }
    return false;
}

// ==========================================
//  音量按键
// ==========================================
void handleVolumeButtons() {
    bool changed = false;
    if (digitalRead(BTN_VOL_UP) == LOW) {
        delay(60);
        if (digitalRead(BTN_VOL_UP) == LOW) {
            volume = min((int)volume + VOL_STEP, VOL_MAX);
            changed = true;
            while (digitalRead(BTN_VOL_UP) == LOW) delay(10);
        }
    }
    if (digitalRead(BTN_VOL_DOWN) == LOW) {
        delay(60);
        if (digitalRead(BTN_VOL_DOWN) == LOW) {
            volume = max((int)volume - VOL_STEP, VOL_MIN);
            changed = true;
            while (digitalRead(BTN_VOL_DOWN) == LOW) delay(10);
        }
    }
    if (changed) {
        Serial.printf("[VOL] %d%%\n", volume);
        showVolOverlay();
        delay(500);
    }
}

// ==========================================
//  持续监听 + VAD
//  true = 录到语音, false = 超时/手动休眠
// ==========================================
bool listenAndRecord() {
    state = ST_LISTENING;
    setLED(0, 50, 50);
    lastVoiceMs = millis();
    audioLen = 0;
    bool recording = false;
    uint32_t silenceStart = 0;
    int16_t readBuf[512];
    size_t bytesRead;
    Serial.println("[VAD] Listening...");

    while (true) {
        if (checkWakeButton()) { Serial.println("[BTN] Manual sleep"); return false; }
        handleVolumeButtons();

        i2s_read(I2S_NUM_0, readBuf, sizeof(readBuf), &bytesRead, 100 / portTICK_PERIOD_MS);
        size_t nSamp = bytesRead / 2;
        if (nSamp == 0) continue;
        uint16_t rms = calcRMS(readBuf, nSamp);

        if (rms > VAD_THRESHOLD) {
            lastVoiceMs = millis();
            if (!recording) {
                recording = true;
                audioLen = 0;
                state = ST_RECORDING;
                setLED(255, 0, 0);
                Serial.printf("[VAD] Voice! RMS=%d\n", rms);
            }
            silenceStart = 0;
            size_t space = AUDIO_BUFFER_SIZE - audioLen;
            size_t w = min(bytesRead, space);
            if (w > 0) { memcpy(audioBuffer + audioLen, readBuf, w); audioLen += w; }
            if (audioLen >= AUDIO_BUFFER_SIZE) { Serial.println("[VAD] Full"); return true; }
        } else {
            if (recording) {
                size_t space = AUDIO_BUFFER_SIZE - audioLen;
                size_t w = min(bytesRead, space);
                if (w > 0) { memcpy(audioBuffer + audioLen, readBuf, w); audioLen += w; }
                if (silenceStart == 0) silenceStart = millis();
                else if (millis() - silenceStart > VAD_SILENCE_MS) {
                    Serial.printf("[VAD] Done %d bytes\n", audioLen);
                    return true;
                }
            } else {
                if (millis() - lastVoiceMs > VAD_SLEEP_TIMEOUT) {
                    Serial.println("[VAD] Timeout->sleep");
                    return false;
                }
            }
        }

        if (millis() - lastAnimMs > 300) {
            animFrame++;
            if (recording) showRecording(); else showListening();
            lastAnimMs = millis();
        }
    }
}

// ==========================================
//  唤醒/休眠动画
// ==========================================
void playWakeAnim() {
    oled.clearDisplay(); oled.display(); delay(80);
    for (int r = 1; r <= 14; r += 2) {
        oled.clearDisplay();
        oled.drawCircle(15, 16, r, SSD1306_WHITE);
        oled.display(); delay(25);
    }
    drawScene(EX_IDLE, "Hello~!");
    delay(500);
}

void playSleepAnim() {
    drawScene(EX_BLINK, "Bye~");
    delay(500);
    for (int r = 14; r >= 1; r -= 2) {
        oled.clearDisplay();
        oled.drawCircle(15, 16, r, SSD1306_WHITE);
        oled.display(); delay(25);
    }
    oled.clearDisplay(); oled.display();
}

// ==========================================
//  重新配置 GPIO0（I2S 初始化后调用）
// ==========================================
void reconfigWakePin() {
    gpio_reset_pin(GPIO_NUM_0);
    gpio_set_direction(GPIO_NUM_0, GPIO_MODE_INPUT);
    gpio_set_pull_mode(GPIO_NUM_0, GPIO_PULLUP_ONLY);
    attachInterrupt(BTN_WAKE, onWakeISR, FALLING);
    Serial.printf("[GPIO] BTN_WAKE(GPIO%d) reconfigured, state=%d\n", BTN_WAKE, digitalRead(BTN_WAKE));
}

// ==========================================
//  Setup
// ==========================================
void setup() {
    Serial.begin(115200);
    delay(300);
    Serial.println("\n=============================");
    Serial.println("  MiniBox ESP32-S3 v2.1");
    Serial.println("=============================");
    Serial.printf("  MAC: %s\n", WiFi.macAddress().c_str());

    pinMode(BTN_VOL_UP, INPUT_PULLUP);
    pinMode(BTN_VOL_DOWN, INPUT_PULLUP);

    Wire.begin(OLED_SDA, OLED_SCL);
    if (!oled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR))
        Serial.println("[OLED] FAIL");
    else
        Serial.println("[OLED] 128x32 OK");

    oled.clearDisplay();
    oled.setTextSize(1); oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(16, 12); oled.print("MiniBox Booting...");
    oled.display();

    audioBuffer = (uint8_t*)ps_malloc(AUDIO_BUFFER_SIZE);
    if (!audioBuffer) {
        Serial.println("[ERR] PSRAM fail!");
        oled.clearDisplay(); oled.setCursor(0,0); oled.print("PSRAM ERR"); oled.display();
        while (1) delay(1000);
    }
    Serial.printf("[MEM] %d bytes\n", AUDIO_BUFFER_SIZE);

    oled.clearDisplay(); oled.setCursor(16,12); oled.print("WiFi..."); oled.display();
    connectWiFi();

    initMicrophone();
    initSpeaker();

    // I2S 初始化后重新配置 GPIO0
    reconfigWakePin();

    setLED(0, 50, 0); delay(300); setLED(0, 0, 0);
    state = ST_SLEEPING;
    Serial.println("[READY] Press WAKE to start!");
}

// ==========================================
//  Loop
// ==========================================
void loop() {
    if (WiFi.status() != WL_CONNECTED) { connectWiFi(); }

    switch (state) {
    case ST_SLEEPING: {
        if (millis() - lastAnimMs > 1000) { animFrame++; showSleeping(); lastAnimMs = millis(); }

        // 呼吸灯
        uint8_t br = (uint8_t)(20 * (0.5 + 0.5 * sin(millis() / 2000.0 * PI)));
        setLED(0, 0, br);

        // 随机眨眼处理（虽然睡眠时不需要，但为代码一致性保留）
        handleVolumeButtons();

        if (checkWakeButton()) {
            Serial.println("[BTN] WAKE!");
            state = ST_WAKING;
        }
        delay(50);
        break;
    }

    case ST_WAKING: {
        setLED(0, 255, 0);
        playWakeAnim();
        setLED(0, 0, 0);

        while (true) {
            bool got = listenAndRecord();
            if (!got) break;
            applyMicGain();
            bool ok = uploadAndPlay();
            if (!ok) {
                drawScene(EX_THINK, "Error :(", "Retry...");
                delay(1500);
            }
        }

        setLED(0, 0, 50);
        playSleepAnim();
        setLED(0, 0, 0);
        state = ST_SLEEPING;
        lastAnimMs = millis();
        break;
    }

    default: delay(20); break;
    }
}
