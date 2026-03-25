"""下载 ffmpeg + ffprobe 到项目本地 bin 目录"""
import os
import io
import zipfile
import urllib.request

BIN_DIR = os.path.join(os.path.dirname(__file__), "bin")
FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

def main():
    os.makedirs(BIN_DIR, exist_ok=True)

    ffmpeg_path = os.path.join(BIN_DIR, "ffmpeg.exe")
    ffprobe_path = os.path.join(BIN_DIR, "ffprobe.exe")

    if os.path.exists(ffmpeg_path) and os.path.exists(ffprobe_path):
        print("ffmpeg 和 ffprobe 已存在，跳过下载。")
        return

    print(f"正在从 GitHub 下载 ffmpeg (约 130MB)，请稍候...")
    try:
        req = urllib.request.Request(FFMPEG_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
        print(f"下载完成 ({len(data) / 1024 / 1024:.1f} MB)，正在解压...")

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                basename = os.path.basename(name)
                if basename in ("ffmpeg.exe", "ffprobe.exe"):
                    target = os.path.join(BIN_DIR, basename)
                    with zf.open(name) as src, open(target, "wb") as dst:
                        dst.write(src.read())
                    print(f"  已解压: {target}")

        if os.path.exists(ffmpeg_path) and os.path.exists(ffprobe_path):
            print("ffmpeg 安装成功！")
        else:
            print("警告：解压后未找到 ffmpeg.exe 或 ffprobe.exe")
    except Exception as e:
        print(f"下载失败: {e}")
        print("请手动下载 ffmpeg: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip")
        print(f"将 ffmpeg.exe 和 ffprobe.exe 放入: {BIN_DIR}")

if __name__ == "__main__":
    main()
