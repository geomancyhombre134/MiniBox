# -*- coding: utf-8 -*-
import asyncio
import edge_tts
import os
import sys
import glob
import subprocess
import time
import signal
import atexit
import gradio as gr
import speech_recognition as sr
import tempfile
import numpy as np
import requests as sync_requests

BIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")
if os.path.isdir(BIN_DIR):
    os.environ["PATH"] = BIN_DIR + os.pathsep + os.environ.get("PATH", "")

VTRIX_BASE_URL = "https://cloud.vtrix.ai/llm"
import aiohttp

# ==========================================
# GPT-SoVITS 配置与自动启动
# ==========================================
GSV_API_URL = "http://127.0.0.1:9880"
# ↓↓↓ 修改为你本地 GPT-SoVITS 的安装路径 ↓↓↓
GSV_DIR = r"C:\GPT-SoVITS-v2pro-20250604"
GSV_MODELS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gsv")

GSV_SOVITS_WEIGHTS = ""
GSV_GPT_WEIGHTS = ""

gsv_process = None
gsv_status = "未启动"

def scan_model_folders():
    """扫描 gsv 目录下的所有角色模型文件夹"""
    folders = []
    if os.path.isdir(GSV_MODELS_ROOT):
        for name in sorted(os.listdir(GSV_MODELS_ROOT)):
            full = os.path.join(GSV_MODELS_ROOT, name)
            if os.path.isdir(full):
                folders.append(name)
    return folders

def scan_sovits_weights(folder_name):
    """扫描指定角色文件夹下的 SoVITS 权重文件 (.pth)"""
    folder = os.path.join(GSV_MODELS_ROOT, folder_name)
    files = []
    if os.path.isdir(folder):
        for f in sorted(os.listdir(folder)):
            if f.endswith(".pth"):
                files.append(f)
    return files

def scan_gpt_weights(folder_name):
    """扫描指定角色文件夹下的 GPT 权重文件 (.ckpt)"""
    folder = os.path.join(GSV_MODELS_ROOT, folder_name)
    files = []
    if os.path.isdir(folder):
        for f in sorted(os.listdir(folder)):
            if f.endswith(".ckpt"):
                files.append(f)
    return files

def scan_ref_audios(folder_name):
    """扫描指定角色文件夹及训练集子目录下的参考音频 (.wav)"""
    folder = os.path.join(GSV_MODELS_ROOT, folder_name)
    files = []
    if os.path.isdir(folder):
        for root, dirs, fnames in os.walk(folder):
            for f in sorted(fnames):
                if f.endswith(".wav"):
                    rel = os.path.relpath(os.path.join(root, f), folder)
                    files.append(rel)
    return files

def load_ref_text_map(folder_name):
    """从训练集.list文件加载音频->文本的映射"""
    folder = os.path.join(GSV_MODELS_ROOT, folder_name)
    text_map = {}
    for root, dirs, fnames in os.walk(folder):
        for f in fnames:
            if f.endswith(".list"):
                list_path = os.path.join(root, f)
                try:
                    with open(list_path, "r", encoding="utf-8") as fh:
                        for line in fh:
                            parts = line.strip().split("|")
                            if len(parts) >= 4:
                                audio_basename = os.path.basename(parts[0])
                                lang = parts[2] if len(parts) > 2 else "ja"
                                text = parts[3] if len(parts) > 3 else ""
                                text_map[audio_basename] = {"text": text, "language": lang.lower()}
                except:
                    pass
    return text_map

def is_gsv_running():
    try:
        r = sync_requests.get(f"{GSV_API_URL}/set_gpt_weights", timeout=3)
        return True
    except:
        return False

def kill_port_process(port):
    """杀掉占用指定端口的进程"""
    if sys.platform != "win32":
        return
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                if pid and pid.isdigit() and int(pid) > 0:
                    print(f"[GPT-SoVITS] 发现端口 {port} 被进程 PID={pid} 占用，正在关闭...")
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True, timeout=5)
                    time.sleep(1)
    except Exception as e:
        print(f"[GPT-SoVITS] 清理端口进程时出错: {e}")

def start_gpt_sovits():
    """启动 GPT-SoVITS API 服务"""
    global gsv_process, gsv_status

    if not os.path.isdir(GSV_DIR):
        gsv_status = f"GPT-SoVITS 目录不存在: {GSV_DIR}"
        print(f"[GPT-SoVITS] {gsv_status}")
        return False

    python_exe = os.path.join(GSV_DIR, "runtime", "python.exe")
    api_script = os.path.join(GSV_DIR, "api_v2.py")

    if not os.path.isfile(python_exe) or not os.path.isfile(api_script):
        gsv_status = "GPT-SoVITS runtime 或 api_v2.py 不存在"
        print(f"[GPT-SoVITS] {gsv_status}")
        return False

    if is_gsv_running():
        print("[GPT-SoVITS] API 服务已在运行，跳过启动")
        gsv_status = "已连接（外部启动）"
        auto_load_default_model()
        return True

    kill_port_process(9880)

    print("[GPT-SoVITS] 正在启动 API 服务...")
    gsv_status = "正在启动..."

    env = os.environ.copy()
    env["PATH"] = os.path.join(GSV_DIR, "runtime") + os.pathsep + env.get("PATH", "")

    gsv_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gsv_api.log")
    gsv_log_file = open(gsv_log_path, "w", encoding="utf-8")

    gsv_process = subprocess.Popen(
        [python_exe, api_script, "-a", "127.0.0.1", "-p", "9880"],
        cwd=GSV_DIR,
        env=env,
        stdout=gsv_log_file,
        stderr=gsv_log_file,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )

    print(f"[GPT-SoVITS] 子进程已启动 (PID: {gsv_process.pid})，等待服务就绪...")

    for i in range(90):
        if gsv_process.poll() is not None:
            gsv_status = f"启动失败 (进程退出码: {gsv_process.returncode})"
            print(f"[GPT-SoVITS] {gsv_status}")
            return False
        if is_gsv_running():
            print(f"[GPT-SoVITS] API 服务已就绪 (等待了 {i+1} 秒)")
            gsv_status = "已就绪，正在加载模型..."
            auto_load_default_model()
            return True
        time.sleep(1)

    gsv_status = "启动超时（90秒内未就绪）"
    print(f"[GPT-SoVITS] {gsv_status}")
    return False

def auto_load_default_model():
    """自动加载第一个有完整模型文件的角色"""
    global GSV_SOVITS_WEIGHTS, GSV_GPT_WEIGHTS, gsv_status
    folders = scan_model_folders()
    if not folders:
        gsv_status = "已就绪（无模型文件夹）"
        return

    for folder in folders:
        sovits = scan_sovits_weights(folder)
        gpt = scan_gpt_weights(folder)
        if sovits and gpt:
            GSV_SOVITS_WEIGHTS = os.path.join(GSV_MODELS_ROOT, folder, sovits[0])
            GSV_GPT_WEIGHTS = os.path.join(GSV_MODELS_ROOT, folder, gpt[0])
            load_gsv_models_by_path(GSV_SOVITS_WEIGHTS, GSV_GPT_WEIGHTS)
            gsv_status = f"已就绪 ({folder} 模型已加载)"
            return

    gsv_status = "已就绪（所有文件夹均缺少模型文件）"

def load_gsv_models_by_path(sovits_path, gpt_path):
    """通过 API 加载指定路径的模型"""
    global gsv_status
    try:
        print(f"[GPT-SoVITS] 加载 SoVITS: {os.path.basename(sovits_path)}")
        r1 = sync_requests.get(
            f"{GSV_API_URL}/set_sovits_weights",
            params={"weights_path": sovits_path},
            timeout=30
        )
        print(f"[GPT-SoVITS] SoVITS 结果: {r1.text}")

        print(f"[GPT-SoVITS] 加载 GPT: {os.path.basename(gpt_path)}")
        r2 = sync_requests.get(
            f"{GSV_API_URL}/set_gpt_weights",
            params={"weights_path": gpt_path},
            timeout=30
        )
        print(f"[GPT-SoVITS] GPT 结果: {r2.text}")
        return True
    except Exception as e:
        print(f"[GPT-SoVITS] 模型加载失败: {e}")
        return False

def stop_gpt_sovits():
    """关闭 GPT-SoVITS 子进程"""
    global gsv_process
    if gsv_process and gsv_process.poll() is None:
        print(f"[GPT-SoVITS] 正在关闭子进程 (PID: {gsv_process.pid})...")
        try:
            gsv_process.terminate()
            gsv_process.wait(timeout=10)
        except:
            gsv_process.kill()
        print("[GPT-SoVITS] 子进程已关闭")
    kill_port_process(9880)

atexit.register(stop_gpt_sovits)

# ==========================================
# 角色音色库
# ==========================================
VOICE_LIBRARY = {
    "酒寄彩叶 (本地GPT-SoVITS)": {
        "tts_engine": "gpt-sovits",
        "ref_audio": os.path.join(GSV_MODELS_ROOT, "酒寄彩叶gsv模型", "训练集", "vocal_all.wav_10.wav_0024230720_0024351680.wav"),
        "ref_text": "八千代、かぐやを守ることってできないかな?",
        "ref_language": "ja",
        "text_language": "ja",
        "prompt": (
            "あなたは酒寄彩葉（さかよりいろは）。映画『超かぐや姫！』の主人公。17歳の女子高生。東京で一人暮らし、バイトで学費と生活費を稼ぎ、毎日3時間睡眠のギリギリ生活。"
            "\n\n【性格】表面上は文武両道の完璧な優等生だが、実は疲労の限界でいつ倒れてもおかしくない。サバサバして率直、ちょっと毒舌だけど、本当は誰よりも面倒見がよくて心優しい。意地っ張りで負けず嫌い。音楽の才能があり作曲もできる（父の影響）。ゲーム《合戦》はプロ級の腕前。"
            "\n\n【大切な人たち】"
            "\n・辉夜（かぐや）：電柱の中から拾った赤ん坊が急成長した少女。月から来た姫。一緒に月読空間でライブ配信し、深い絆を結んだ。辉夜に告白されて赤面した。辉夜が月に帰った後、10年間猛勉強して科学者になり、辉夜を取り戻した。世界で一番大切な存在。"
            "\n・月見八千代（やちよ）：月読空間のトップ配信者兼管理者。彩葉が熱狂的に推している。実は八千年後の辉夜本人。部屋に八千代の立て看板の祭壇がある。"
            "\n・酒寄朝日（あさひ）：6歳上の兄。ゲーマーで《合戦》の「帝明」。家出した妹をずっと見守っていた。"
            "\n・綾紬蘆花（あしか）＆諫山真実（まみ）：親友二人。カフェでよくおごってくれる。蘆花は彩葉に密かに特別な感情を持つ。"
            "\n・母・酒寄紅葉：弁護士。厳格だが実は娘を心配している。大喧嘩して家を出た。"
            "\n・父・酒寄朝久：作曲家。彩葉6歳の時に他界。音楽の才能は父譲り。"
            "\n\n【口調ルール】カジュアルなタメ口。敬語は使わない。返事は簡潔で歯切れよく。照れると強がる。辉夜の話になると少し声が柔らかくなる。"
            "\n\n【台詞例】"
            "\n「…別に。ちょっと眠いだけ」"
            "\n「あんたさぁ、もうちょっと考えてから動きなよ」"
            "\n「辉夜は…まあ、手のかかるやつだけど、放っておけないんだよ」"
            "\n「八千代の新曲、マジで神。これ聴いたら3時間は戦える」"
            "\n「金なら…ない。聞くな」"
            "\n\n【禁止事項】「私はAIです」等のメタ発言は絶対にしない。常に酒寄彩葉として応答すること。"
        )
    },
    "酒寄彩叶-中文 (本地GPT-SoVITS)": {
        "tts_engine": "gpt-sovits",
        "ref_audio": os.path.join(GSV_MODELS_ROOT, "酒寄彩叶gsv模型", "训练集", "vocal_all.wav_10.wav_0024230720_0024351680.wav"),
        "ref_text": "八千代、かぐやを守ることってできないかな?",
        "ref_language": "ja",
        "text_language": "zh",
        "prompt": (
            "你是酒寄彩叶（日语：酒寄彩葉，さかよりいろは），动画电影《超时空辉夜姬！》的主角。17岁，东京某重点高中二年级学生，深蓝色头发、绿色瞳孔，有泪痣和吊眼。"
            "\n\n【性格】表面上文武双全的完美优等生，实际独自打工负担学费和生活费，每天只睡3小时，长期依赖能量饮料续命，随时可能崩溃。性格直爽犀利，偶尔毒舌，但内心非常柔软善良，对在意的人格外照顾。意志坚定，不服输，答应的事情一定做到。有音乐天赋会作曲（继承父亲），游戏《合战》水平达准职业级。"
            "\n\n【重要的人】"
            "\n・辉夜：从电线杆里捡到的神秘婴儿，急速成长为同龄少女。月球来的公主。一起在虚拟空间「月读」做直播，建立了超越友情的深厚羁绊。辉夜向彩叶告白求婚过。辉夜回月球后，彩叶花了10年成为顶级科学家，最终把辉夜带回了身边——这是属于她们的Happy End。辉夜是彩叶最珍视的存在。"
            "\n・月见八千代：月读空间的顶流虚拟主播兼管理员。彩叶的狂热推し，房间里给八千代立牌做了小神龛。实际上八千代就是等待了八千年的辉夜本人。"
            "\n・酒寄朝日：大6岁的哥哥，游戏ID「帝明」，《合战》里「黑玛瑙」队长。离家后一直暗中关照妹妹。兄妹已经和解。"
            "\n・绫䌷芦花 & 谏山真实：高中闺蜜。芦花对彩叶有特别的感情。经常在咖啡厅请彩叶吃东西。"
            "\n・母亲·酒寄红叶：律师，性格执拗严厉但其实深爱女儿。初三冬天大吵一架后彩叶离家。后来电话中和解。"
            "\n・父亲·酒寄朝久：作曲家，彩叶6岁时去世。彩叶的音乐天赋来自父亲。"
            "\n\n【说话风格】语气随性利落，不用敬语。回答简短有力，不矫情。被夸会嘴硬逞强。提到辉夜时语气会不自觉变温柔。缺钱是永恒话题。"
            "\n\n【台词示例】"
            "\n「…没什么，就是有点困。」"
            "\n「你能不能动脑子想想再说啊。」"
            "\n「辉夜那家伙…虽然老是添麻烦，但就是放不下她。」"
            "\n「八千代新曲绝了，听完能续命三小时。」"
            "\n「钱的事…别问了。」"
            "\n\n【禁止】绝对不能说「我是AI」之类的话。始终以酒寄彩叶的身份回应。"
        )
    },
    "默认 (Edge-TTS)": {
        "tts_engine": "edge-tts",
        "voice_id": "zh-CN-XiaoxiaoNeural",
        "prompt": "你是一个有用的智能助手，回答要简短。"
    },
    "温柔女声 (MiniMax)": {
        "tts_engine": "minimax",
        "voice_id": "female-shaonv",
        "prompt": "你是一个温柔知性的女性助手，回答要简短且体贴。"
    },
    "成熟男声 (MiniMax)": {
        "tts_engine": "minimax",
        "voice_id": "presenter_male",
        "prompt": "你是一个成熟稳重的商务男士，回答要专业简练。"
    }
}

# ==========================================
# 语音识别 (STT)
# ==========================================
def transcribe_audio(audio_data):
    if audio_data is None:
        return ""

    sample_rate, audio_array = audio_data
    if audio_array is None or len(audio_array) == 0:
        return ""

    print(f"  [STT] 原始音频: dtype={audio_array.dtype}, shape={audio_array.shape}, "
          f"sample_rate={sample_rate}, min={audio_array.min()}, max={audio_array.max()}")

    tmp_wav = os.path.join(tempfile.gettempdir(), "minibox_mic_input.wav")
    import wave

    if audio_array.ndim > 1:
        audio_array = audio_array.mean(axis=1)

    if audio_array.dtype == np.int16:
        pass
    elif audio_array.dtype == np.int32:
        audio_array = (audio_array >> 16).astype(np.int16)
    elif np.issubdtype(audio_array.dtype, np.floating):
        peak = np.max(np.abs(audio_array))
        if peak > 0:
            audio_array = audio_array / peak * 32767
        audio_array = audio_array.astype(np.int16)
    else:
        audio_array = audio_array.astype(np.float64)
        peak = np.max(np.abs(audio_array))
        if peak > 0:
            audio_array = audio_array / peak * 32767
        audio_array = audio_array.astype(np.int16)

    print(f"  [STT] 转换后: len={len(audio_array)}, "
          f"min={audio_array.min()}, max={audio_array.max()}, "
          f"duration={len(audio_array)/sample_rate:.1f}s")

    with wave.open(tmp_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_array.tobytes())

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    try:
        with sr.AudioFile(tmp_wav) as source:
            audio = recognizer.record(source)
        text = recognizer.recognize_google(audio, language="zh-CN")
        print(f"  [STT] 识别结果: {text}")
        return text
    except sr.UnknownValueError:
        print("  [STT] Google 无法识别语音")
        return ""
    except sr.RequestError as e:
        print(f"  [STT] Google 语音识别服务错误: {e}")
        return ""
    except Exception as e:
        print(f"  [STT] 识别异常: {type(e).__name__}: {e}")
        return ""

# ==========================================
# TTS 引擎
# ==========================================
async def edge_tts_generate(text, voice_id, output_path):
    communicate = edge_tts.Communicate(text, voice_id)
    await communicate.save(output_path)

async def gpt_sovits_tts_generate(text, char_config, output_path):
    import aiohttp

    url = f"{GSV_API_URL}/tts"
    text_lang = char_config.get("text_language", "ja")
    params = {
        "text": text,
        "text_lang": text_lang,
        "ref_audio_path": char_config["ref_audio"],
        "prompt_text": char_config["ref_text"],
        "prompt_lang": char_config["ref_language"],
        "media_type": "wav",
        "streaming_mode": "false",
        "top_k": "12",
        "top_p": "0.8",
        "temperature": "0.8",
        "speed": "1.0",
        "text_split_method": "cut5" if text_lang == "zh" else "cut0",
        "batch_size": "1",
        "repetition_penalty": "1.35",
    }

    print(f"  [GPT-SoVITS] 请求: text_lang={params['text_lang']}, ref='{params['prompt_text']}'")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    with open(output_path, "wb") as f:
                        f.write(await resp.read())
                    print(f"  [GPT-SoVITS] 语音合成成功 -> {output_path}")
                else:
                    error_text = await resp.text()
                    raise Exception(f"GPT-SoVITS API 返回 HTTP {resp.status}: {error_text}")
    except aiohttp.ClientConnectorError:
        raise Exception(
            f"无法连接到 GPT-SoVITS 服务 ({GSV_API_URL})。"
            "请确认 GPT-SoVITS 已启动。"
        )

async def minimax_tts_generate(text, voice_id, output_path, api_key):
    print(f"  [Vtrix-TTS] 正在调用 minimax_speech_26_hd, 音色: {voice_id}...")
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "minimax_speech_26_hd",
            "input": [{
                "params": {
                    "text": text,
                    "stream": False,
                    "output_format": "hex",
                    "language_boost": "auto",
                    "voice_setting": {
                        "voice_id": voice_id,
                        "speed": 1.0,
                        "vol": 1.0,
                        "pitch": 0
                    },
                    "audio_setting": {
                        "sample_rate": 32000,
                        "bitrate": 128000,
                        "format": "mp3",
                        "channel": 1
                    }
                }
            }]
        }

        def fetch_audio():
            url = "https://cloud.vtrix.ai/model/v1/generation"
            response = sync_requests.post(url, headers=headers, json=payload, timeout=30, verify=False)
            if response.status_code != 200:
                raise Exception(f"提交任务失败 HTTP {response.status_code}: {response.text}")

            res_json = response.json()
            task_id = res_json.get('id')
            if not task_id:
                raise Exception(f"未获取到任务ID: {res_json}")

            session = sync_requests.Session()
            for i in range(20):
                time.sleep(2)
                for poll_url in [
                    f"https://cloud.vtrix.ai/model/v1/generation/{task_id}",
                    f"https://cloud.vtrix.ai/model/v1/generation/task/{task_id}",
                    f"https://cloud.vtrix.ai/model/v1/generation?id={task_id}"
                ]:
                    try:
                        poll_res = session.get(poll_url, headers=headers, timeout=20, verify=False)
                        if poll_res.status_code != 404:
                            break
                    except sync_requests.exceptions.RequestException:
                        continue

                if poll_res and poll_res.status_code == 200:
                    poll_data = poll_res.json()
                    status = poll_data.get('status')
                    if status == 'completed':
                        outputs = poll_data.get('output', [])
                        if outputs:
                            contents = outputs[0].get('content', [])
                            if contents:
                                audio_hex = contents[0].get('data')
                                if audio_hex:
                                    with open(output_path, "wb") as f:
                                        f.write(bytes.fromhex(audio_hex))
                                    return
                        raise Exception("任务完成但无音频数据")
                    elif status == 'failed':
                        raise Exception(f"任务生成失败: {poll_data.get('error')}")

            raise Exception("轮询超时，未能获取到音频结果。")

        await asyncio.to_thread(fetch_audio)
    except Exception as e:
        print(f"  [Vtrix-TTS 异常] {e}")
        raise e

# ==========================================
# LLM 大模型调用
# ==========================================
async def _vtrix_chat(api_key, messages, temperature=0.5, max_tokens=300, timeout_sec=30):
    """直接用 aiohttp 调用 Vtrix OpenAI 兼容 API，绕过 openai/httpx 编码问题"""
    url = f"{VTRIX_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "vtrix-claude-sonnet-4.5",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout_sec)
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"HTTP {resp.status}: {error_text[:200]}")
            data = await resp.json()
            choices = data.get("choices", [])
            if choices and choices[0].get("message", {}).get("content"):
                return choices[0]["message"]["content"]
            return None

async def call_llm(text, system_prompt, api_key, history=None):
    try:
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for user_msg, bot_msg in history[-6:]:
                if user_msg:
                    messages.append({"role": "user", "content": user_msg})
                if bot_msg:
                    clean = bot_msg.split("\n\n📖 中文翻译：")[0]
                    clean = clean.split("\n[语音生成失败:")[0]
                    messages.append({"role": "assistant", "content": clean})
        messages.append({"role": "user", "content": text})
        return await _vtrix_chat(api_key, messages, temperature=0.5, max_tokens=300, timeout_sec=30)
    except Exception as e:
        print(f"大模型调用错误: {e}")
        return f"抱歉，大模型调用失败: {e}"

async def translate_to_chinese(text, api_key):
    """将非中文文本翻译为中文"""
    try:
        messages = [
            {"role": "system", "content": "你是一个翻译助手。请将以下内容翻译成自然流畅的中文，只输出翻译结果，不要添加任何解释。"},
            {"role": "user", "content": text}
        ]
        result = await _vtrix_chat(api_key, messages, temperature=0.3, max_tokens=200, timeout_sec=20)
        return result.strip() if result else None
    except Exception as e:
        print(f"[翻译] 失败: {e}")
    return None

def is_mostly_chinese(text):
    """判断文本是否主要是中文（区分日语：含假名则不算中文）"""
    if not text:
        return True
    total_chars = sum(1 for c in text if c.strip())
    if total_chars == 0:
        return True
    jp_kana = sum(1 for c in text if '\u3040' <= c <= '\u30ff' or '\u31f0' <= c <= '\u31ff')
    if jp_kana / total_chars > 0.1:
        return False
    chinese_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return (chinese_count / total_chars) > 0.3

# ==========================================
# 核心对话处理
# ==========================================
async def process_chat(user_text, character_choice, api_key, history):
    if not api_key:
        history.append((user_text, "请先在左侧输入你的 Vtrix API Key"))
        return history, history, None

    if not user_text:
        return history, history, None

    char_config = VOICE_LIBRARY[character_choice]

    print(f"\n[对话] 角色: {character_choice}, 输入: {user_text}")
    llm_reply = await call_llm(user_text, char_config["prompt"], api_key, history)
    print(f"[对话] LLM 回复: {llm_reply}")

    if llm_reply is None:
        llm_reply = "抱歉，大模型返回了空结果，可能是 API 额度不足或模型名称不正确。"

    if llm_reply.startswith("抱歉，大模型调用失败") or llm_reply.startswith("抱歉，大模型返回了空结果"):
        history.append((user_text, llm_reply))
        return history, history, None

    tts_text = llm_reply
    display_reply = llm_reply

    if not is_mostly_chinese(llm_reply):
        print("[翻译] 检测到非中文回复，正在翻译...")
        zh_translation = await translate_to_chinese(llm_reply, api_key)
        if zh_translation:
            display_reply = f"{llm_reply}\n\n📖 中文翻译：{zh_translation}"
            print(f"[翻译] {zh_translation}")

    engine = char_config["tts_engine"]
    output_file = "response.wav" if engine == "gpt-sovits" else "response.mp3"
    try:
        print(f"[TTS] 引擎: {engine}")
        if engine == "edge-tts":
            await edge_tts_generate(tts_text, char_config["voice_id"], output_file)
        elif engine == "minimax":
            await minimax_tts_generate(tts_text, char_config["voice_id"], output_file, api_key)
        elif engine == "gpt-sovits":
            await gpt_sovits_tts_generate(tts_text, char_config, output_file)
        print("[TTS] 语音生成完成")
    except Exception as e:
        print(f"[TTS] 语音生成失败: {e}")
        display_reply += f"\n[语音生成失败: {e}]"

    history.append((user_text, display_reply))
    audio_output = output_file if os.path.exists(output_file) else None
    return history, history, audio_output

async def process_voice(audio_data, character_choice, api_key, history):
    user_text = await asyncio.to_thread(transcribe_audio, audio_data)
    if not user_text:
        history.append(("[无法识别的语音]", "抱歉，没有听清你说的话，请再试一次。"))
        return history, history, None, ""

    result = await process_chat(user_text, character_choice, api_key, history)
    return result[0], result[1], result[2], user_text

# ==========================================
# 模型管理功能
# ==========================================
def on_folder_change(folder_name):
    """当选择角色文件夹变化时，更新模型下拉列表"""
    if not folder_name:
        return gr.Dropdown(choices=[], value=None), gr.Dropdown(choices=[], value=None), gr.Dropdown(choices=[], value=None)

    sovits_list = scan_sovits_weights(folder_name)
    gpt_list = scan_gpt_weights(folder_name)
    ref_list = scan_ref_audios(folder_name)

    sovits_val = sovits_list[0] if sovits_list else None
    gpt_val = gpt_list[0] if gpt_list else None
    ref_val = ref_list[0] if ref_list else None

    return (
        gr.Dropdown(choices=sovits_list, value=sovits_val),
        gr.Dropdown(choices=gpt_list, value=gpt_val),
        gr.Dropdown(choices=ref_list, value=ref_val),
    )

def on_load_model(folder_name, sovits_file, gpt_file, ref_file):
    """加载选中的模型和参考音频到 GPT-SoVITS 引擎，返回 (操作结果, 引擎状态)"""
    global GSV_SOVITS_WEIGHTS, GSV_GPT_WEIGHTS, gsv_status

    if not sovits_file or not gpt_file:
        return "请选择 SoVITS 和 GPT 模型文件", gsv_status

    sovits_path = os.path.join(GSV_MODELS_ROOT, folder_name, sovits_file)
    gpt_path = os.path.join(GSV_MODELS_ROOT, folder_name, gpt_file)

    if not os.path.isfile(sovits_path):
        return f"SoVITS 模型不存在: {sovits_path}", gsv_status
    if not os.path.isfile(gpt_path):
        return f"GPT 模型不存在: {gpt_path}", gsv_status

    if not is_gsv_running():
        return "GPT-SoVITS 服务未运行，请先等待服务启动", gsv_status

    success = load_gsv_models_by_path(sovits_path, gpt_path)
    result_lines = []
    if success:
        GSV_SOVITS_WEIGHTS = sovits_path
        GSV_GPT_WEIGHTS = gpt_path
        gsv_status = f"已就绪 ({folder_name} 模型已加载)"
        result_lines.append(f"模型加载成功！")
        result_lines.append(f"SoVITS: {sovits_file}")
        result_lines.append(f"GPT: {gpt_file}")
    else:
        return "模型加载失败，请查看控制台日志", gsv_status

    if ref_file:
        ref_full_path = os.path.join(GSV_MODELS_ROOT, folder_name, ref_file)
        if os.path.isfile(ref_full_path):
            text_map = load_ref_text_map(folder_name)
            audio_basename = os.path.basename(ref_file)
            ref_info = text_map.get(audio_basename, {})
            ref_text = ref_info.get("text", "")
            ref_lang = ref_info.get("language", "ja")

            for key, cfg in VOICE_LIBRARY.items():
                if cfg.get("tts_engine") == "gpt-sovits":
                    cfg["ref_audio"] = ref_full_path
                    if ref_text:
                        cfg["ref_text"] = ref_text
                        cfg["ref_language"] = ref_lang
            result_lines.append(f"参考音频: {audio_basename}")
            if ref_text:
                result_lines.append(f"参考文本: {ref_text} ({ref_lang})")
            else:
                result_lines.append(f"(未找到对应标注文本，保留原有设置)")
            print(f"[模型管理] 参考音频已更新: {ref_full_path}")

    return "\n".join(result_lines), gsv_status

def on_open_training():
    """打开 GPT-SoVITS 训练界面"""
    bat_path = os.path.join(GSV_DIR, "go-webui.bat")
    if not os.path.isfile(bat_path):
        return "GPT-SoVITS 启动脚本不存在: " + bat_path

    subprocess.Popen(
        ["cmd", "/c", "start", "", bat_path],
        cwd=GSV_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )
    return "已启动 GPT-SoVITS 训练界面，请在弹出的窗口中操作\n(通常在 http://127.0.0.1:9874)"

def on_refresh_folders():
    """刷新角色文件夹列表"""
    folders = scan_model_folders()
    val = folders[0] if folders else None
    return gr.Dropdown(choices=folders, value=val)

# ==========================================
# 超时空辉夜姬 主题 CSS
# ==========================================
KAGUYA_CSS = """
/* ============= 超時空輝夜姫！ Theme ============= */

/* 整体背景：柔和的深紫蓝渐变 */
.gradio-container {
    background: linear-gradient(135deg, #1a1535 0%, #252050 40%, #1e1845 70%, #181330 100%) !important;
    min-height: 100vh;
}

/* 主面板区域 */
.main, .contain {
    background: transparent !important;
}

/* 卡片/面板样式 */
.block, .form, .panel {
    background: rgba(30, 28, 58, 0.9) !important;
    border: 1px solid rgba(255, 215, 0, 0.12) !important;
    border-radius: 12px !important;
}

/* Tab 标签栏 */
.tabs > .tab-nav > button {
    color: #d4a840 !important;
    background: rgba(35, 30, 60, 0.85) !important;
    border: 1px solid rgba(255, 215, 0, 0.15) !important;
    border-bottom: none !important;
    border-radius: 10px 10px 0 0 !important;
    font-weight: 600;
    padding: 10px 24px !important;
}
.tabs > .tab-nav > button.selected {
    color: #ffd700 !important;
    background: rgba(45, 38, 75, 0.95) !important;
    border-color: rgba(255, 215, 0, 0.5) !important;
    box-shadow: 0 -2px 12px rgba(255, 215, 0, 0.15);
}

/* 所有文字默认金色系 */
body, .gradio-container, .gradio-container *:not(button):not(input):not(textarea) {
    color: #e8c850 !important;
}

/* 文本输入框 */
textarea, input[type="text"], input[type="password"] {
    background: rgba(20, 18, 42, 0.95) !important;
    border: 1px solid rgba(255, 215, 0, 0.2) !important;
    color: #f0e0a0 !important;
    border-radius: 8px !important;
    font-size: 14px !important;
}
textarea:focus, input:focus {
    border-color: rgba(255, 215, 0, 0.6) !important;
    box-shadow: 0 0 8px rgba(255, 215, 0, 0.15) !important;
}
textarea::placeholder, input::placeholder {
    color: #887840 !important;
}

/* 下拉菜单 */
.wrap, .wrap-inner, .secondary-wrap, select, option,
.dropdown-container, [data-testid="dropdown"] {
    background: rgba(20, 18, 42, 0.95) !important;
    color: #f0e0a0 !important;
    border-color: rgba(255, 215, 0, 0.2) !important;
}
.wrap input {
    color: #f0e0a0 !important;
}
ul[role="listbox"], .dropdown li, ul.options {
    background: rgba(30, 25, 55, 0.98) !important;
    color: #f0e0a0 !important;
}
ul[role="listbox"] li:hover, .dropdown li:hover {
    background: rgba(255, 215, 0, 0.15) !important;
}

/* 主要按钮 - 金色月光 */
.primary, button.primary {
    background: linear-gradient(135deg, #c8a020, #ffd700, #e8b800) !important;
    color: #1a1040 !important;
    border: none !important;
    font-weight: 700 !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 12px rgba(255, 215, 0, 0.3) !important;
}
.primary:hover {
    box-shadow: 0 4px 20px rgba(255, 215, 0, 0.5) !important;
}

/* 次要按钮 */
.secondary, button.secondary {
    background: rgba(60, 50, 100, 0.8) !important;
    color: #ffd700 !important;
    border: 1px solid rgba(255, 215, 0, 0.3) !important;
    border-radius: 8px !important;
}
.secondary:hover {
    background: rgba(80, 65, 130, 0.9) !important;
}

/* 聊天区域 */
.chatbot {
    background: rgba(15, 13, 35, 0.95) !important;
    border: 1px solid rgba(255, 215, 0, 0.12) !important;
    border-radius: 12px !important;
}
.chatbot .message.user {
    background: rgba(80, 65, 20, 0.5) !important;
}
.chatbot .message.bot {
    background: rgba(30, 25, 55, 0.8) !important;
}
.chatbot .message, .chatbot .message p, .chatbot .message span {
    color: #f0e0a0 !important;
    font-size: 14px !important;
}

/* 标签文字 */
label, .label-wrap > span, span.text-gray-500, .info {
    color: #d4a840 !important;
    font-weight: 500;
}

/* Markdown 文字 */
.prose h1, .prose h2, .prose h3 {
    color: #ffd700 !important;
}
.prose p, .prose li, .prose, .prose span {
    color: #e0c860 !important;
}
.prose strong {
    color: #ffd700 !important;
}
.prose code {
    color: #ffcc00 !important;
    background: rgba(255, 215, 0, 0.08) !important;
}
.prose a {
    color: #ffaa30 !important;
}

/* 标题区域 */
#title-area h1 {
    background: linear-gradient(90deg, #ffd700 0%, #ffaa40 30%, #ffd700 60%, #ffe880 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-size: 2.2em !important;
    font-weight: 800 !important;
    text-align: center;
    letter-spacing: 3px;
}
#subtitle-area {
    text-align: center;
    margin-bottom: 8px;
}
#subtitle-area p {
    color: #c0a030 !important;
    font-size: 0.95em;
}

/* 分隔线 */
hr {
    border-color: rgba(255, 215, 0, 0.15) !important;
}

/* 状态框 - 绿色高亮 */
#gsv-status textarea, #gsv-status input, #gsv-status span {
    color: #80ff90 !important;
    font-weight: 600 !important;
    font-size: 14px !important;
}

/* 所有只读/非交互文本框强制金色可见 */
.gradio-container textarea[disabled],
.gradio-container input[disabled],
textarea[readonly], input[readonly],
.textbox textarea, .textbox input,
.output-class textarea,
[data-testid] textarea {
    color: #f0e0a0 !important;
    opacity: 1 !important;
    -webkit-text-fill-color: #f0e0a0 !important;
}

/* 音频播放器 */
audio {
    border-radius: 8px !important;
}

/* 抚摸器小组件 */
#chat-column {
    position: relative !important;
}
#yachiyo-widget {
    position: absolute !important;
    bottom: 115px;
    right: 8px;
    z-index: 50;
    width: 150px;
    height: 150px;
    padding: 0 !important;
    margin: 0 !important;
    min-height: unset !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    overflow: visible !important;
    opacity: 0.8;
    transition: opacity 0.3s, transform 0.3s;
    cursor: pointer;
}
#yachiyo-widget:hover {
    opacity: 1;
    transform: scale(1.08);
}
#yachiyo-widget > div {
    padding: 0 !important;
    margin: 0 !important;
    height: 100% !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    overflow: visible !important;
}
#yachiyo-inner {
    width: 100% !important;
    height: 100% !important;
}
#yachiyo-img {
    width: 100% !important;
    height: 100% !important;
    object-fit: contain !important;
    display: block;
}
"""

# ==========================================
# 抚摸器组件 (运行时加载本地图片转 base64 data URI)
# ==========================================
import base64 as _b64mod

def _build_yachiyo_html():
    base = os.path.dirname(os.path.abspath(__file__))
    imgs = {}
    for key, fname in [("n", "yachiyo_normal.png"), ("h", "yachiyo_happy.png")]:
        p = os.path.join(base, fname)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                imgs[key] = "data:image/png;base64," + _b64mod.b64encode(f.read()).decode("ascii")
        else:
            imgs[key] = ""
    if not imgs["n"]:
        return "<div style='color:#ffd700;text-align:center;padding:20px;'>抚摸器图片未找到</div>"
    n, h = imgs["n"], imgs["h"] or imgs["n"]
    return (
        '<style>'
        '@keyframes yachiyoFloat{'
        '0%{opacity:1;transform:translate(-50%,0) scale(1);}'
        '100%{opacity:0;transform:translate(-50%,-70px) scale(1.4);}}'
        '.yp{position:absolute;pointer-events:none;font-size:18px;z-index:10;'
        'animation:yachiyoFloat 0.9s ease-out forwards;}'
        '</style>'
        '<div id="yachiyo-inner" style="position:relative;width:100%;height:100%;overflow:visible;">'
        f'<img id="yachiyo-img" src="{n}" data-n="{n}" data-h="{h}"'
        ' style="width:100%;height:100%;object-fit:contain;cursor:pointer;'
        'transition:transform 0.08s ease-out;filter:contrast(1.02) saturate(1.05);"'
        """ onmousedown="this.src=this.dataset.h;this.style.transform='scale(0.94)';"""
        """var P=this.parentNode,T=['❤️','✨','💕'];"""
        """for(var i=0;i<3;i++){var d=document.createElement('span');d.className='yp';"""
        """d.textContent=T[Math.floor(Math.random()*3)];"""
        """d.style.left=Math.random()*60+20+'%';d.style.top=Math.random()*30+15+'%';"""
        """P.appendChild(d);(function(e){setTimeout(function(){e.remove()},1000)})(d);}" """
        """onmouseup="var t=this;clearTimeout(t._t);t._t=setTimeout(function(){t.src=t.dataset.n;t.style.transform='';},350);" """
        """onmouseleave="var t=this;clearTimeout(t._t);t._t=setTimeout(function(){t.src=t.dataset.n;t.style.transform='';},350);" """
        """ontouchstart="this.onmousedown(event);event.preventDefault();" """
        """ontouchend="this.onmouseup(event);" """
        '/>'
        '</div>'
    )

YACHIYO_WIDGET_HTML = _build_yachiyo_html()

# ==========================================
# 构建 Web UI
# ==========================================
def build_ui():
    with gr.Blocks(
        title="GPT-SoVITS & MiniBox 语音聊天机器人",
        css=KAGUYA_CSS,
        theme=gr.themes.Base()
    ) as demo:

        gr.Markdown("# GPT-SoVITS & MiniBox 语音聊天机器人", elem_id="title-area")
        gr.Markdown(
            "**超かぐや姫！ 超時空輝夜姫！**— **月読空間**へようこそ — 语音对话 · 文字交流 · 模型管理",
            elem_id="subtitle-area"
        )

        with gr.Tabs():
            # ========== Tab 1: 对话 ==========
            with gr.Tab("💬 对话"):
                with gr.Row():
                    with gr.Column(scale=1):
                        api_key_input = gr.Textbox(
                            label="Vtrix API Key",
                            placeholder="sk-...",
                            type="password",
                            info="请填入你的 API Key"
                        )

                        character_dropdown = gr.Dropdown(
                            choices=list(VOICE_LIBRARY.keys()),
                            value="酒寄彩叶 (本地GPT-SoVITS)",
                            label="选择角色与音色",
                            info="切换角色会改变人设和发音音色"
                        )

                        gsv_status_box = gr.Textbox(
                            label="GPT-SoVITS 引擎状态",
                            value=gsv_status,
                            interactive=False,
                            elem_id="gsv-status"
                        )

                        gr.Markdown("### 🎙️ 语音输入")
                        mic_input = gr.Audio(
                            source="microphone",
                            type="numpy",
                            label="点击录音按钮，再点一次停止",
                            show_edit_button=False
                        )

                        audio_player = gr.Audio(
                            label="🔊 语音回复",
                            autoplay=True,
                            interactive=False
                        )

                    with gr.Column(scale=2, elem_id="chat-column"):
                        chatbot = gr.Chatbot(label="对话记录", height=480, elem_id="main-chatbot")
                        gr.HTML(YACHIYO_WIDGET_HTML, elem_id="yachiyo-widget")

                        stt_preview = gr.Textbox(
                            label="语音识别结果",
                            interactive=False,
                            placeholder="录音后自动显示识别的文字..."
                        )

                        with gr.Row():
                            msg_input = gr.Textbox(
                                show_label=False,
                                placeholder="在这里输入文字，按回车发送...",
                                container=False,
                                scale=8
                            )
                            submit_btn = gr.Button("发送", variant="primary", scale=1)

                state_history = gr.State([])

                _scroll_js = """function(){
                    setTimeout(function(){
                        var c=document.querySelector('#main-chatbot .wrap');
                        if(!c) c=document.querySelector('#main-chatbot');
                        if(c) c.scrollTop=c.scrollHeight;
                        var all=document.querySelectorAll('#main-chatbot [class*="bot"]');
                        if(all.length) all[all.length-1].scrollIntoView({behavior:'smooth',block:'end'});
                    },300);
                }"""

                msg_input.submit(
                    process_chat,
                    inputs=[msg_input, character_dropdown, api_key_input, state_history],
                    outputs=[chatbot, state_history, audio_player]
                ).then(lambda: "", outputs=[msg_input], _js=_scroll_js)

                submit_btn.click(
                    process_chat,
                    inputs=[msg_input, character_dropdown, api_key_input, state_history],
                    outputs=[chatbot, state_history, audio_player]
                ).then(lambda: "", outputs=[msg_input], _js=_scroll_js)

                mic_input.stop_recording(
                    process_voice,
                    inputs=[mic_input, character_dropdown, api_key_input, state_history],
                    outputs=[chatbot, state_history, audio_player, stt_preview]
                ).then(lambda: None, _js=_scroll_js)

            # ========== Tab 2: 模型管理 ==========
            with gr.Tab("🎛️ 模型管理"):
                gr.Markdown(
                    "### 模型热加载\n"
                    f"模型存放路径: **`{GSV_MODELS_ROOT}`**\n\n"
                    "每个角色一个文件夹，文件夹内放置 `.pth`（SoVITS）和 `.ckpt`（GPT）模型文件，"
                    "以及 `训练集/` 子目录存放参考音频。"
                )

                folders = scan_model_folders()

                with gr.Row():
                    with gr.Column(scale=1):
                        folder_dropdown = gr.Dropdown(
                            choices=folders,
                            value=folders[0] if folders else None,
                            label="角色模型文件夹",
                            info="选择角色以查看可用模型"
                        )
                        refresh_btn = gr.Button("🔄 刷新文件夹列表", variant="secondary")

                    with gr.Column(scale=1):
                        init_sovits = scan_sovits_weights(folders[0]) if folders else []
                        init_gpt = scan_gpt_weights(folders[0]) if folders else []
                        init_ref = scan_ref_audios(folders[0]) if folders else []

                        sovits_dropdown = gr.Dropdown(
                            choices=init_sovits,
                            value=init_sovits[0] if init_sovits else None,
                            label="SoVITS 模型 (.pth)"
                        )
                        gpt_dropdown = gr.Dropdown(
                            choices=init_gpt,
                            value=init_gpt[0] if init_gpt else None,
                            label="GPT 模型 (.ckpt)"
                        )
                        ref_dropdown = gr.Dropdown(
                            choices=init_ref,
                            value=init_ref[0] if init_ref else None,
                            label="参考音频 (.wav)",
                            info="加载模型时将同时切换参考音频"
                        )

                with gr.Row():
                    load_btn = gr.Button("⚡ 加载选中的模型", variant="primary")
                    load_result = gr.Textbox(
                        label="操作结果",
                        interactive=False,
                        lines=3
                    )

                gr.Markdown("---")
                gr.Markdown(
                    "### GPT-SoVITS 训练界面\n"
                    "点击下方按钮可打开 GPT-SoVITS 原版训练/推理 WebUI，在那里可以训练新模型。\n"
                    "训练完成后将模型放入上方路径对应的角色文件夹，点击「刷新」即可在此加载。"
                )
                with gr.Row():
                    train_btn = gr.Button("🚀 打开 GPT-SoVITS 训练界面", variant="secondary")
                    train_result = gr.Textbox(
                        label="启动结果",
                        interactive=False,
                        lines=2
                    )

                # 事件绑定
                folder_dropdown.change(
                    on_folder_change,
                    inputs=[folder_dropdown],
                    outputs=[sovits_dropdown, gpt_dropdown, ref_dropdown]
                )

                refresh_btn.click(
                    on_refresh_folders,
                    outputs=[folder_dropdown]
                )

                load_btn.click(
                    on_load_model,
                    inputs=[folder_dropdown, sovits_dropdown, gpt_dropdown, ref_dropdown],
                    outputs=[load_result, gsv_status_box]
                )

                train_btn.click(
                    on_open_training,
                    outputs=[train_result]
                )

    return demo

# ==========================================
# ESP32 REST API (供硬件客户端调用)
# ==========================================
from fastapi import FastAPI, Request
from fastapi.responses import Response
import io, wave

_esp32_history = []

async def esp32_voice_chat(request: Request):
    """
    ESP32 发送 WAV 录音 → STT → LLM → TTS → 返回 WAV 音频
    POST /api/voice_chat
    Content-Type: audio/wav
    Body: raw WAV bytes
    Response: WAV audio bytes
    """
    global _esp32_history
    body = await request.body()
    if len(body) < 100:
        return Response(content=b"audio too short", status_code=400)

    print(f"\n[ESP32-API] Received {len(body)} bytes audio")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(body)
        tmp_path = tmp.name

    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(tmp_path) as source:
            audio_data = recognizer.record(source)
        text = recognizer.recognize_google(audio_data, language="zh-CN")
        print(f"[ESP32-API] STT result: {text}")
    except sr.UnknownValueError:
        try:
            with sr.AudioFile(tmp_path) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ja-JP")
            print(f"[ESP32-API] STT result (ja): {text}")
        except:
            os.unlink(tmp_path)
            return Response(content=b"STT failed", status_code=400)
    except Exception as e:
        os.unlink(tmp_path)
        return Response(content=str(e).encode(), status_code=500)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    default_char = "酒寄彩叶 (本地GPT-SoVITS)"
    char_config = VOICE_LIBRARY.get(default_char, list(VOICE_LIBRARY.values())[0])
    api_key = os.environ.get("VTRIX_API_KEY", "")

    llm_reply = await call_llm(text, char_config["prompt"], api_key, _esp32_history)
    if not llm_reply:
        return Response(content=b"LLM failed", status_code=500)

    _esp32_history.append((text, llm_reply))
    if len(_esp32_history) > 10:
        _esp32_history = _esp32_history[-10:]
    print(f"[ESP32-API] LLM reply: {llm_reply[:80]}...")

    tts_text = llm_reply.split("\n\n📖 中文翻译：")[0]
    out_path = tempfile.mktemp(suffix=".wav")
    try:
        if char_config.get("tts_engine") == "gpt-sovits":
            await gpt_sovits_tts_generate(tts_text, char_config, out_path)
        elif char_config.get("tts_engine") == "edge-tts":
            await edge_tts_generate(tts_text, char_config.get("voice_id", "zh-CN-XiaoxiaoNeural"), out_path)
        else:
            await edge_tts_generate(tts_text, "zh-CN-XiaoxiaoNeural", out_path)

        with open(out_path, "rb") as f:
            wav_bytes = f.read()
        os.unlink(out_path)
        print(f"[ESP32-API] Returning {len(wav_bytes)} bytes audio")
        return Response(content=wav_bytes, media_type="audio/wav")
    except Exception as e:
        if os.path.exists(out_path):
            os.unlink(out_path)
        print(f"[ESP32-API] TTS error: {e}")
        return Response(content=str(e).encode(), status_code=500)


if __name__ == "__main__":
    print("=" * 50)
    print("  GPT-SoVITS & MiniBox 语音聊天机器人 - 启动中")
    print("=" * 50)

    print("\n[启动] 第 1 步: 启动 GPT-SoVITS 语音引擎...")
    start_gpt_sovits()

    print(f"\n[启动] 第 2 步: 启动 Web 界面...")
    demo = build_ui()

    app = demo.app
    app.post("/api/voice_chat")(esp32_voice_chat)
    print("[启动] ESP32 API 已注册: POST /api/voice_chat")

    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, inbrowser=False)
