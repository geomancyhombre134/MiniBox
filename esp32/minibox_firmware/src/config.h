#ifndef MINIBOX_CONFIG_H
#define MINIBOX_CONFIG_H

// ==========================================
//  WiFi — 修改为你的实际网络
// ==========================================
#define WIFI_SSID     "your-wifi-ssid"
#define WIFI_PASSWORD "your-wifi-password"

// ==========================================
//  PC 服务器 — 改为运行 webui.py 的电脑局域网 IP
//  cmd 输入 ipconfig 查看
// ==========================================
#define SERVER_HOST   "192.168.1.100"
#define SERVER_PORT   7860

// ==========================================
//  I2S 麦克风 (INMP441) — 鹿小班小智AI扩展板
// ==========================================
#define I2S_MIC_SCK   5
#define I2S_MIC_WS    4
#define I2S_MIC_SD    6

// ==========================================
//  I2S 喇叭 (MAX98357A) — 鹿小班小智AI扩展板
// ==========================================
#define I2S_SPK_BCK   15
#define I2S_SPK_WS    16
#define I2S_SPK_DOUT  7

// ==========================================
//  按键 GPIO — 鹿小班小智AI扩展板
//  左上=音量+  左下=音量-  右上=硬件复位  右下=唤醒
// ==========================================
#define BTN_WAKE      0     // 右下 唤醒/休眠 (BOOT)
#define BTN_VOL_UP    40    // 左上 音量+
#define BTN_VOL_DOWN  39    // 左下 音量-

// ==========================================
//  OLED 屏幕 (SSD1306 I2C 128x32)
// ==========================================
#define OLED_SDA      41
#define OLED_SCL      42
#define OLED_ADDR     0x3C
#define SCREEN_W      128
#define SCREEN_H      32

// ==========================================
//  LED (WS2812 RGB)
// ==========================================
#define LED_PIN       48

// ==========================================
//  音频参数
// ==========================================
#define SAMPLE_RATE       16000
#define RECORD_SECONDS    10
#define AUDIO_BUFFER_SIZE (SAMPLE_RATE * RECORD_SECONDS * 2)

// ==========================================
//  VAD 参数
// ==========================================
#define VAD_THRESHOLD       120     // RMS 阈值
#define VAD_SILENCE_MS      800     // 语音结束判定 (ms)
#define VAD_SLEEP_TIMEOUT   10000   // 无人说话超时休眠 (ms)

// ==========================================
//  麦克风软件增益 (INMP441 原始信号较弱)
// ==========================================
#define MIC_GAIN          8

// ==========================================
//  音量
// ==========================================
#define VOL_DEFAULT   70
#define VOL_STEP      10
#define VOL_MAX       100
#define VOL_MIN       0

#endif
