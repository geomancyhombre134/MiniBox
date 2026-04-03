# -*- coding: utf-8 -*-
"""
MiniBox — 彩叶 ESP32 固件烧录工具

使用 esptool 对 ESP32-S3 进行固件烧录，支持：
  - 自动检测串口
  - 选择固件文件（合并 bin 或分区烧录）
  - 配置 WiFi 和服务器参数（写入 NVS）
  - 一键烧录 + 进度显示
"""

import os
import sys
import json
import struct
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import serial.tools.list_ports

APP_DIR = os.path.dirname(os.path.abspath(__file__))
FIRMWARE_DIR = os.path.join(APP_DIR, "firmware")
CONFIG_FILE = os.path.join(APP_DIR, "flash_config.json")

DEFAULT_BAUD = "921600"
CHIP_TYPE = "esp32s3"

# ==========================================
# 自动获取本机局域网 IP
# ==========================================
def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "192.168.1.100"


# ==========================================
# 配置持久化
# ==========================================
def load_config():
    defaults = {
        "wifi_ssid": "",
        "wifi_password": "",
        "server_host": get_local_ip(),
        "server_port": "7860",
        "firmware_path": "",
        "baud_rate": DEFAULT_BAUD,
        "com_port": "",
        "flash_mode": "dio",
        "flash_freq": "80m",
        "erase_before_flash": True,
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            defaults.update(saved)
        except:
            pass
    return defaults


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except:
        pass


# ==========================================
# 串口扫描
# ==========================================
def scan_ports():
    ports = serial.tools.list_ports.comports()
    result = []
    for p in sorted(ports, key=lambda x: x.device):
        label = f"{p.device}"
        if p.description and p.description != "n/a":
            label += f"  ({p.description})"
        result.append((p.device, label))
    return result


# ==========================================
# NVS 配置二进制生成
# ==========================================
def build_nvs_bin(wifi_ssid, wifi_password, server_host, server_port):
    """
    生成简易 NVS 配置分区 bin，固件侧从 NVS 或自定义分区读取此 JSON。
    格式：4字节长度头 + JSON + 0xFF 填充至 4096 字节。
    """
    config_data = {
        "wifi_ssid": wifi_ssid,
        "wifi_password": wifi_password,
        "server_host": server_host,
        "server_port": int(server_port) if server_port else 7860,
    }
    json_bytes = json.dumps(config_data, ensure_ascii=False).encode("utf-8")
    page_size = 4096
    if len(json_bytes) >= page_size - 4:
        raise ValueError(f"配置数据过长 ({len(json_bytes)} bytes)，最大 {page_size - 4}")
    header = struct.pack("<I", len(json_bytes))
    bin_data = header + json_bytes
    bin_data += b'\xff' * (page_size - len(bin_data))
    return bin_data


# ==========================================
# 固件扫描
# ==========================================
def scan_firmware():
    files = []
    if os.path.isdir(FIRMWARE_DIR):
        for f in sorted(os.listdir(FIRMWARE_DIR)):
            if f.endswith(".bin"):
                files.append(f)
    return files


# ==========================================
# 主界面
# ==========================================
class FlashToolApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MiniBox — 彩叶 ESP32 固件烧录工具")
        self.root.geometry("750x720")
        self.root.minsize(680, 640)
        self.root.configure(bg="#fdf6f0")

        self.cfg = load_config()
        self.flashing = False
        self._port_device_map = {}

        self._apply_style()
        self._build_ui()
        self._load_values()

    def _apply_style(self):
        style = ttk.Style()
        style.theme_use("clam")

        bg = "#fdf6f0"
        accent = "#c2185b"
        text_color = "#3e2723"

        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=text_color,
                         font=("Microsoft YaHei UI", 10))
        style.configure("TLabelframe", background=bg, foreground=accent,
                         font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TLabelframe.Label", background=bg, foreground=accent,
                         font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("TEntry", fieldbackground="#ffffff")
        style.configure("TCombobox", fieldbackground="#ffffff")
        style.configure("TCheckbutton", background=bg,
                         font=("Microsoft YaHei UI", 9))

        style.configure("Flash.TButton",
                         font=("Microsoft YaHei UI", 12, "bold"),
                         foreground="#ffffff", background=accent,
                         padding=(20, 10))
        style.map("Flash.TButton",
                   background=[("active", "#ad1457"), ("disabled", "#bcaaa4")])

        style.configure("Small.TButton",
                         font=("Microsoft YaHei UI", 9),
                         padding=(8, 4))

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        # ---------- 标题 ----------
        title_frame = ttk.Frame(main)
        title_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(title_frame, text="MiniBox — 彩叶 ESP32 固件烧录工具",
                  font=("Microsoft YaHei UI", 16, "bold"),
                  foreground="#c2185b").pack()
        ttk.Label(title_frame, text="超かぐや姫！超時空輝夜姫！",
                  font=("Microsoft YaHei UI", 9),
                  foreground="#8d6e63").pack()

        # ---------- 串口 & 固件 ----------
        hw_frame = ttk.LabelFrame(main, text="硬件连接", padding=8)
        hw_frame.pack(fill=tk.X, pady=4)

        row1 = ttk.Frame(hw_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="串口:").pack(side=tk.LEFT, padx=(0, 4))
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(row1, textvariable=self.port_var,
                                        width=30, state="readonly")
        self.port_combo.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(row1, text="刷新", style="Small.TButton",
                   command=self._refresh_ports).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(row1, text="波特率:").pack(side=tk.LEFT, padx=(0, 4))
        self.baud_var = tk.StringVar(value=self.cfg.get("baud_rate", DEFAULT_BAUD))
        baud_combo = ttk.Combobox(row1, textvariable=self.baud_var, width=10,
                                   values=["115200", "230400", "460800", "921600"],
                                   state="readonly")
        baud_combo.pack(side=tk.LEFT)

        row2 = ttk.Frame(hw_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="固件:").pack(side=tk.LEFT, padx=(0, 4))
        self.fw_var = tk.StringVar()
        self.fw_combo = ttk.Combobox(row2, textvariable=self.fw_var, width=46)
        self.fw_combo.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(row2, text="浏览...", style="Small.TButton",
                   command=self._browse_firmware).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(row2, text="刷新", style="Small.TButton",
                   command=self._refresh_firmware).pack(side=tk.LEFT)

        row3 = ttk.Frame(hw_frame)
        row3.pack(fill=tk.X, pady=2)
        self.erase_var = tk.BooleanVar(value=self.cfg.get("erase_before_flash", True))
        ttk.Checkbutton(row3, text="烧录前擦除整片 Flash（首次烧录建议勾选）",
                        variable=self.erase_var).pack(side=tk.LEFT)

        # ---------- WiFi & 服务器配置 ----------
        net_frame = ttk.LabelFrame(main, text="网络配置（写入 ESP32 设备）", padding=8)
        net_frame.pack(fill=tk.X, pady=4)

        r1 = ttk.Frame(net_frame)
        r1.pack(fill=tk.X, pady=2)
        ttk.Label(r1, text="WiFi SSID:", width=12).pack(side=tk.LEFT)
        self.ssid_var = tk.StringVar()
        ttk.Entry(r1, textvariable=self.ssid_var, width=28).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(r1, text="WiFi 密码:").pack(side=tk.LEFT, padx=(0, 4))
        self.wifi_pw_var = tk.StringVar()
        self.wifi_pw_entry = ttk.Entry(r1, textvariable=self.wifi_pw_var, width=24, show="*")
        self.wifi_pw_entry.pack(side=tk.LEFT, padx=(0, 4))
        self.show_pw_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(r1, text="显示", variable=self.show_pw_var,
                        command=self._toggle_pw_visibility).pack(side=tk.LEFT)

        r2 = ttk.Frame(net_frame)
        r2.pack(fill=tk.X, pady=2)
        ttk.Label(r2, text="服务器 IP:", width=12).pack(side=tk.LEFT)
        self.host_var = tk.StringVar()
        ttk.Entry(r2, textvariable=self.host_var, width=20).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(r2, text="端口:").pack(side=tk.LEFT, padx=(0, 4))
        self.port_num_var = tk.StringVar()
        ttk.Entry(r2, textvariable=self.port_num_var, width=8).pack(side=tk.LEFT)

        hint = ttk.Label(net_frame,
                         text="提示：服务器 IP 填运行 webui.py 的电脑 IP（已自动检测本机 IP），API Key 无需填入，它安全地保存在服务器端",
                         foreground="#8d6e63", font=("Microsoft YaHei UI", 8))
        hint.pack(fill=tk.X, pady=(4, 0))

        # ---------- 操作按钮 ----------
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=8)

        self.flash_btn = ttk.Button(btn_frame, text="开始烧录", style="Flash.TButton",
                                     command=self._start_flash)
        self.flash_btn.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(btn_frame, text="仅写入网络配置", style="Small.TButton",
                   command=self._write_config_only).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(btn_frame, text="读取芯片信息", style="Small.TButton",
                   command=self._read_chip_info).pack(side=tk.LEFT)

        # ---------- 进度 ----------
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(main, variable=self.progress_var,
                                             maximum=100, length=400)
        self.progress_bar.pack(fill=tk.X, pady=(4, 2))

        self.status_var = tk.StringVar(value="就绪 — 请连接 ESP32 并选择固件")
        ttk.Label(main, textvariable=self.status_var,
                  font=("Microsoft YaHei UI", 9),
                  foreground="#5d4037").pack(fill=tk.X, pady=(0, 4))

        # ---------- 日志 ----------
        log_frame = ttk.LabelFrame(main, text="烧录日志", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=4)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=14, font=("Consolas", 9),
            bg="#3e2723", fg="#efebe9", insertbackground="#efebe9",
            wrap=tk.WORD, state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self._refresh_ports()
        self._refresh_firmware()

    def _load_values(self):
        self.ssid_var.set(self.cfg.get("wifi_ssid", ""))
        self.wifi_pw_var.set(self.cfg.get("wifi_password", ""))
        self.host_var.set(self.cfg.get("server_host", get_local_ip()))
        self.port_num_var.set(self.cfg.get("server_port", "7860"))
        fw = self.cfg.get("firmware_path", "")
        if fw:
            self.fw_var.set(fw)
        port = self.cfg.get("com_port", "")
        if port:
            self.port_var.set(port)

    def _save_current(self):
        self.cfg.update({
            "wifi_ssid": self.ssid_var.get(),
            "wifi_password": self.wifi_pw_var.get(),
            "server_host": self.host_var.get(),
            "server_port": self.port_num_var.get(),
            "firmware_path": self.fw_var.get(),
            "baud_rate": self.baud_var.get(),
            "com_port": self.port_var.get(),
            "erase_before_flash": self.erase_var.get(),
        })
        save_config(self.cfg)

    def _toggle_pw_visibility(self):
        self.wifi_pw_entry.config(show="" if self.show_pw_var.get() else "*")

    def _refresh_ports(self):
        ports = scan_ports()
        labels = [lbl for _, lbl in ports]
        devices = [dev for dev, _ in ports]
        self.port_combo["values"] = labels
        self._port_device_map = dict(zip(labels, devices))
        if labels:
            current = self.port_var.get()
            if current not in labels:
                self.port_combo.current(len(labels) - 1)
        self.log(f"[串口] 检测到 {len(ports)} 个串口设备")

    def _refresh_firmware(self):
        files = scan_firmware()
        current_values = list(self.fw_combo["values"]) if self.fw_combo["values"] else []
        fw_paths = [os.path.join(FIRMWARE_DIR, f) for f in files]
        for v in current_values:
            if v not in fw_paths and os.path.isfile(v):
                fw_paths.append(v)
        self.fw_combo["values"] = fw_paths
        if fw_paths and not self.fw_var.get():
            self.fw_var.set(fw_paths[0])
        self.log(f"[固件] firmware/ 目录下发现 {len(files)} 个 .bin 文件")

    def _browse_firmware(self):
        path = filedialog.askopenfilename(
            title="选择固件文件",
            initialdir=FIRMWARE_DIR if os.path.isdir(FIRMWARE_DIR) else APP_DIR,
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")]
        )
        if path:
            self.fw_var.set(path)
            vals = list(self.fw_combo["values"]) if self.fw_combo["values"] else []
            if path not in vals:
                vals.append(path)
                self.fw_combo["values"] = vals

    def _get_selected_port(self):
        label = self.port_var.get()
        return self._port_device_map.get(label, label)

    def log(self, text):
        def _append():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, text + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.root.after(0, _append)

    def set_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def set_progress(self, value):
        self.root.after(0, lambda: self.progress_var.set(value))

    def _set_flashing(self, state):
        self.flashing = state
        self.root.after(0, lambda: self.flash_btn.config(
            state=tk.DISABLED if state else tk.NORMAL
        ))

    # ---------- 读取芯片信息 ----------
    def _read_chip_info(self):
        port = self._get_selected_port()
        if not port:
            messagebox.showwarning("提示", "请先选择串口")
            return

        self.log(f"\n[芯片] 正在读取 {port} 上的芯片信息...")
        self.set_status("正在读取芯片信息...")

        def _run():
            try:
                cmd = [
                    sys.executable, "-m", "esptool",
                    "--port", port,
                    "--baud", "115200",
                    "chip_id"
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                self.log(result.stdout)
                if result.returncode != 0:
                    self.log(f"[错误] {result.stderr}")
                    self.set_status("读取芯片信息失败")
                else:
                    self.set_status("芯片信息读取完成")
            except FileNotFoundError:
                self.log("[错误] 未找到 esptool，请先安装: pip install esptool")
                self.set_status("缺少 esptool")
            except subprocess.TimeoutExpired:
                self.log("[错误] 读取超时，请检查连接和驱动")
                self.set_status("读取超时")
            except Exception as e:
                self.log(f"[错误] {e}")
                self.set_status("读取失败")

        threading.Thread(target=_run, daemon=True).start()

    # ---------- 写入网络配置 ----------
    def _write_config_only(self):
        port = self._get_selected_port()
        if not port:
            messagebox.showwarning("提示", "请先选择串口")
            return

        ssid = self.ssid_var.get().strip()
        if not ssid:
            messagebox.showwarning("提示", "请填写 WiFi SSID")
            return

        self._save_current()
        self.log(f"\n[配置] 正在通过串口写入网络配置...")
        self.set_status("正在写入网络配置...")

        def _run():
            try:
                config_json = json.dumps({
                    "wifi_ssid": ssid,
                    "wifi_password": self.wifi_pw_var.get(),
                    "server_host": self.host_var.get().strip(),
                    "server_port": int(self.port_num_var.get() or 7860),
                }, ensure_ascii=False)

                import serial
                with serial.Serial(port, 115200, timeout=3) as ser:
                    cmd = f"MINIBOX_CONFIG:{config_json}\n"
                    ser.write(cmd.encode("utf-8"))
                    self.log(f"[配置] 已发送: {cmd.strip()}")

                    response = ser.readline().decode("utf-8", errors="replace").strip()
                    if response:
                        self.log(f"[配置] 设备回复: {response}")

                self.log("[配置] 网络配置写入完成")
                self.set_status("网络配置已写入")
            except Exception as e:
                self.log(f"[错误] 写入配置失败: {e}")
                self.set_status("配置写入失败")

        threading.Thread(target=_run, daemon=True).start()

    # ---------- 开始烧录 ----------
    def _start_flash(self):
        if self.flashing:
            return

        port = self._get_selected_port()
        fw_path = self.fw_var.get().strip()

        if not port:
            messagebox.showwarning("提示", "请先选择串口")
            return
        if not fw_path or not os.path.isfile(fw_path):
            messagebox.showwarning("提示", "请选择有效的固件文件 (.bin)")
            return

        self._save_current()
        self._set_flashing(True)
        self.set_progress(0)

        baud = self.baud_var.get()
        erase = self.erase_var.get()

        self.log(f"\n{'='*50}")
        self.log(f"  开始烧录 — MiniBox 彩叶")
        self.log(f"{'='*50}")
        self.log(f"  串口: {port}")
        self.log(f"  波特率: {baud}")
        self.log(f"  固件: {fw_path}")
        self.log(f"  擦除Flash: {'是' if erase else '否'}")
        self.log(f"  芯片: {CHIP_TYPE}")
        self.log(f"{'='*50}\n")

        def _flash_thread():
            try:
                self.set_status("正在烧录固件...")
                self.set_progress(5)

                cmd = [
                    sys.executable, "-m", "esptool",
                    "--chip", CHIP_TYPE,
                    "--port", port,
                    "--baud", baud,
                ]

                if erase:
                    self.log("[步骤 1/3] 擦除 Flash...")
                    self.set_progress(10)
                    erase_cmd = cmd + ["erase_flash"]
                    result = subprocess.run(erase_cmd, capture_output=True, text=True, timeout=60)
                    self.log(result.stdout)
                    if result.returncode != 0:
                        self.log(f"[错误] 擦除失败:\n{result.stderr}")
                        self.set_status("擦除 Flash 失败")
                        return
                    self.log("[步骤 1/3] 擦除完成")
                    self.set_progress(30)
                else:
                    self.log("[步骤 1/3] 跳过擦除")
                    self.set_progress(30)

                self.log("[步骤 2/3] 写入固件...")
                self.set_progress(35)

                write_cmd = cmd + [
                    "write_flash",
                    "--flash_mode", self.cfg.get("flash_mode", "dio"),
                    "--flash_freq", self.cfg.get("flash_freq", "80m"),
                    "--flash_size", "detect",
                    "0x0", fw_path,
                ]

                process = subprocess.Popen(
                    write_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1
                )

                for line in process.stdout:
                    line = line.rstrip()
                    if line:
                        self.log(line)
                    if "Writing at" in line and "%" in line:
                        try:
                            pct_str = line.split("(")[1].split("%")[0].strip()
                            pct = float(pct_str)
                            self.set_progress(35 + pct * 0.5)
                        except:
                            pass

                process.wait(timeout=300)
                if process.returncode != 0:
                    self.log("[错误] 固件写入失败")
                    self.set_status("固件写入失败")
                    return

                self.log("[步骤 2/3] 固件写入完成")
                self.set_progress(85)

                ssid = self.ssid_var.get().strip()
                if ssid:
                    self.log("[步骤 3/3] 写入网络配置...")
                    self.set_progress(88)
                    try:
                        nvs_bin = build_nvs_bin(
                            ssid,
                            self.wifi_pw_var.get(),
                            self.host_var.get().strip() or get_local_ip(),
                            self.port_num_var.get() or "7860"
                        )
                        nvs_tmp = os.path.join(APP_DIR, "_temp_nvs.bin")
                        with open(nvs_tmp, "wb") as f:
                            f.write(nvs_bin)

                        nvs_cmd = cmd + [
                            "write_flash",
                            "0x9000", nvs_tmp,
                        ]
                        result = subprocess.run(nvs_cmd, capture_output=True, text=True, timeout=30)
                        self.log(result.stdout)
                        if os.path.exists(nvs_tmp):
                            os.remove(nvs_tmp)

                        if result.returncode == 0:
                            self.log("[步骤 3/3] 网络配置写入完成")
                        else:
                            self.log(f"[警告] 配置写入可能失败: {result.stderr}")
                            self.log("  可在设备启动后通过串口发送配置")
                    except Exception as e:
                        self.log(f"[警告] 配置写入失败: {e}")
                        self.log("  可在设备启动后通过串口发送配置")
                else:
                    self.log("[步骤 3/3] 未填写 WiFi，跳过网络配置")

                self.set_progress(100)
                self.log(f"\n{'='*50}")
                self.log("  烧录完成！设备将自动重启。")
                self.log(f"{'='*50}\n")
                self.set_status("烧录完成！")

                self.root.after(0, lambda: messagebox.showinfo(
                    "烧录完成",
                    "固件烧录成功！\n\n"
                    "设备将自动重启。\n"
                    "如已配置WiFi，设备将自动连接网络。\n\n"
                    "请确保 PC 端 webui.py 已启动。"
                ))

            except FileNotFoundError:
                self.log("[错误] 未找到 esptool。请先安装:")
                self.log("  pip install esptool")
                self.set_status("缺少 esptool，请先安装")
            except subprocess.TimeoutExpired:
                self.log("[错误] 烧录超时，请检查设备连接")
                self.set_status("烧录超时")
            except Exception as e:
                self.log(f"[错误] 烧录异常: {e}")
                self.set_status(f"烧录失败: {e}")
            finally:
                self._set_flashing(False)

        threading.Thread(target=_flash_thread, daemon=True).start()

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self._save_current()
        self.root.destroy()


# ==========================================
# 入口
# ==========================================
if __name__ == "__main__":
    app = FlashToolApp()
    app.run()
