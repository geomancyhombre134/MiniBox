import speech_recognition as sr
import numpy as np
import pyaudio

print("=== 依赖检测 ===")
print("SpeechRecognition: OK")
print("numpy: OK")
print("pyaudio: OK")

print("\n=== 麦克风设备列表 ===")
p = pyaudio.PyAudio()
mic_count = 0
for i in range(p.get_device_count()):
    dev = p.get_device_info_by_index(i)
    if dev.get("maxInputChannels") > 0:
        mic_count += 1
        print(f"  [{dev['index']}] {dev['name']} (channels={dev['maxInputChannels']}, rate={int(dev['defaultSampleRate'])})")
p.terminate()
print(f"共检测到 {mic_count} 个麦克风设备")

print("\n=== 短录音测试 (2秒) ===")
recognizer = sr.Recognizer()
try:
    with sr.Microphone() as source:
        print("正在录音，请说话...")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.listen(source, timeout=3, phrase_time_limit=2)
    print("录音完成，正在识别...")
    text = recognizer.recognize_google(audio, language="zh-CN")
    print(f"识别结果: {text}")
except sr.WaitTimeoutError:
    print("超时：2秒内没有检测到语音（这不算报错，只是没说话）")
except sr.UnknownValueError:
    print("无法识别语音内容（可能背景噪音太大或没说话）")
except sr.RequestError as e:
    print(f"Google 语音识别服务错误: {e}")
except Exception as e:
    print(f"异常: {type(e).__name__}: {e}")

print("\n测试完毕。")
