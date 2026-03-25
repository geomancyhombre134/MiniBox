#ifndef MINIBOX_CONFIG_H
#define MINIBOX_CONFIG_H

// ==========================================
//  WiFi 配置 — 修改为你的实际网络
// ==========================================
#define WIFI_SSID     "your_wifi_ssid"
#define WIFI_PASSWORD "your_wifi_password"

// ==========================================
//  MiniBox PC 服务器地址
//  改为运行 webui.py 的电脑的局域网 IP
//  例: "192.168.1.100"
// ==========================================
#define SERVER_HOST   "192.168.1.100"
#define SERVER_PORT   7860

// ==========================================
//  I2S 麦克风引脚 (INMP441)
// ==========================================
#define I2S_MIC_SCK   4    // BCLK / SCK
#define I2S_MIC_WS    5    // LRCLK / WS
#define I2S_MIC_SD    6    // DOUT / SD

// ==========================================
//  I2S 喇叭引脚 (MAX98357A)
// ==========================================
#define I2S_SPK_BCK   15   // BCLK
#define I2S_SPK_WS    16   // LRCLK
#define I2S_SPK_DOUT  17   // DIN

// ==========================================
//  按钮引脚 (按住说话)
// ==========================================
#define BUTTON_PIN    0    // 板载 BOOT 按钮，也可接外部按钮

// ==========================================
//  LED 指示灯 (可选)
// ==========================================
#define LED_PIN       48   // ESP32-S3 DevKitC 板载 RGB LED

// ==========================================
//  音频参数
// ==========================================
#define SAMPLE_RATE       16000
#define BITS_PER_SAMPLE   16
#define RECORD_SECONDS    8    // 单次最大录音时长
#define AUDIO_BUFFER_SIZE (SAMPLE_RATE * RECORD_SECONDS * 2)  // 16bit = 2 bytes

#endif
