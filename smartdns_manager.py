import tkinter as tk
from tkinter import ttk, messagebox
import threading
import subprocess
import psutil
import json
import os
import sys
import ctypes
import time
import re
from datetime import datetime
from pathlib import Path
import ctypes.wintypes

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ─── Constants ────────────────────────────────────────────────────────────────
APP_NAME    = "SmartDNS Manager"
APP_VERSION = "v1.0"
SMARTDNS_EXE   = "smartdns.exe"
SMARTDNS_ARGS  = ["smartdns", "run"]
PID_FILE       = Path(os.environ.get("APPDATA", ".")) / "smartdns_manager" / "smartdns.pid"
BACKUP_FILE    = Path(os.environ.get("APPDATA", ".")) / "smartdns_manager" / "dns_backup.json"
LOCAL_DNS      = "127.0.0.1"

# ─── Color Palette ────────────────────────────────────────────────────────────
BG_DEEP    = "#0D0F14"
BG_CARD    = "#141720"
BG_HOVER   = "#1C2030"
BG_BORDER  = "#252A3A"
ACCENT     = "#00D4AA"
ACCENT_DIM = "#007A62"
RED        = "#FF4A6E"
RED_DIM    = "#8B1F35"
YELLOW     = "#FFB800"
TEXT_PRI   = "#E8EAF0"
TEXT_SEC   = "#7A8299"
TEXT_MUTED = "#454C63"

# ─── Admin Check ──────────────────────────────────────────────────────────────
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def run_as_admin():
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )

# ─── DNS / Process Utilities ──────────────────────────────────────────────────
def get_active_adapter():
    """Return the name of the first active (non-loopback) physical adapter."""
    result = subprocess.run(
        ["netsh", "interface", "show", "interface"],
        capture_output=True, text=True, encoding="gbk" # Windows 终端默认通常是 GBK
    )
    
    # 如果 GBK 失败尝试 UTF-8
    stdout = result.stdout
    if not stdout:
        result = subprocess.run(
            ["netsh", "interface", "show", "interface"],
            capture_output=True, text=True, encoding="utf-8"
        )
        stdout = result.stdout

    blacklist = ["virtual", "vmware", "virtualbox", "loopback", "pseudo", "veth", "teredo", "tunnel", "singbox"]
    
    candidates = []
    for line in stdout.splitlines():
        # 支持中英文状态检测
        if ("Connected" in line or "已连接" in line):
            parts = line.split()
            if len(parts) >= 4:
                name = " ".join(parts[3:])
                name_low = name.lower()
                
                # 检查黑名单
                if any(b in name_low for b in blacklist):
                    continue
                
                # 优先权重：物理网卡名称
                score = 0
                if "wlan" in name_low or "wi-fi" in name_low or "wifi" in name_low:
                    score = 10
                elif "以太网" in name_low or "ethernet" in name_low:
                    score = 5
                
                candidates.append((score, name))
    
    if candidates:
        # 按权重排序，取最高分
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    
    return None

def get_current_dns(adapter):
    # 使用 GBK 编码读取，防止中文环境下解析失败
    result = subprocess.run(
        ["netsh", "interface", "ip", "show", "dns", f"name={adapter}"],
        capture_output=True, text=True, encoding="gbk", errors="ignore"
    )
    for line in result.stdout.splitlines():
        m = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
        if m:
            return m.group(1)
    return None

def set_dns(adapter, dns_ip):
    subprocess.run(
        ["netsh", "interface", "ip", "set", "dns",
         f"name={adapter}", "static", dns_ip],
        capture_output=True
    )

def reset_dns_to_dhcp(adapter):
    subprocess.run(
        ["netsh", "interface", "ip", "set", "dns",
         f"name={adapter}", "dhcp"],
        capture_output=True
    )

def find_smartdns_process():
    my_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # 排除当前管理程序进程，防止误报
            if proc.info['pid'] == my_pid:
                continue
            
            # 检查进程名
            name = (proc.info['name'] or '').lower()
            if name == SMARTDNS_EXE.lower():
                return proc
            
            # 检查命令行（主要针对通过 python 运行的情况）
            if proc.info['cmdline']:
                cmd_str = " ".join(proc.info['cmdline']).lower()
                # 必须包含 smartdns，但不能包含管理程序自身的文件名
                if "smartdns" in cmd_str and "smartdns_manager" not in cmd_str:
                    # 进一步确认是运行指令而非其他
                    if "run" in cmd_str or SMARTDNS_EXE.lower() in cmd_str:
                        return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None

def read_pid_file():
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except Exception:
            pass
    return None

def write_pid_file(pid):
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid))

def delete_pid_file():
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass

def save_dns_backup(adapter, dns_ip):
    BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    BACKUP_FILE.write_text(json.dumps({"adapter": adapter, "dns": dns_ip}, indent=2))

def load_dns_backup():
    if BACKUP_FILE.exists():
        try:
            data = json.loads(BACKUP_FILE.read_text())
            return data.get("adapter"), data.get("dns")
        except Exception:
            pass
    return None, None

def delete_backup_file():
    try:
        BACKUP_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  GUI Application
# ══════════════════════════════════════════════════════════════════════════════
class SmartDNSApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  {APP_VERSION}")
        self.geometry("620x560")
        self.minsize(580, 500)
        self.configure(bg=BG_DEEP)
        self.resizable(True, True)

        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - 620) // 2
        y = (self.winfo_screenheight() - 560) // 2
        self.geometry(f"+{x}+{y}")

        # Set Icons
        try:
            icon_path = resource_path("favicon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
            
            # Windows taskbar icon fix
            myappid = f'mycompany.smartdnsmanager.{APP_VERSION}' # unique identifier
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        self._status   = "unknown"   # "running" | "stopped" | "unknown"
        self._busy     = False
        self._dot_tick = 0

        self._build_styles()
        self._build_ui()
        self._refresh_status()
        self._tick_clock()

    # ─── ttk Styles ───────────────────────────────────────────────────────────
    def _build_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame",      background=BG_DEEP)
        s.configure("Card.TFrame", background=BG_CARD)
        s.configure("TLabel",      background=BG_DEEP, foreground=TEXT_PRI,
                    font=("Segoe UI", 10))
        s.configure("Card.TLabel", background=BG_CARD, foreground=TEXT_PRI,
                    font=("Segoe UI", 10))
        s.configure("Muted.TLabel", background=BG_CARD, foreground=TEXT_SEC,
                    font=("Segoe UI", 9))
        s.configure("TScrollbar", troughcolor=BG_CARD, background=BG_BORDER,
                    arrowcolor=TEXT_MUTED, borderwidth=0)

    # ─── UI Layout ────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = self
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        # ── Header ──────────────────────────────────────────────────────────
        hdr = tk.Frame(root, bg=BG_CARD, height=64)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(1, weight=1)

        # Accent bar on left
        tk.Frame(hdr, bg=ACCENT, width=3).pack(side="left", fill="y")

        left = tk.Frame(hdr, bg=BG_CARD)
        left.pack(side="left", padx=18, pady=14)

        tk.Label(left, text="SmartDNS", bg=BG_CARD, fg=TEXT_PRI,
                 font=("Segoe UI Semibold", 16, "bold")).pack(anchor="w")
        tk.Label(left, text="DNS 智能管理控制台", bg=BG_CARD, fg=TEXT_SEC,
                 font=("Segoe UI", 9)).pack(anchor="w")

        right = tk.Frame(hdr, bg=BG_CARD)
        right.pack(side="right", padx=18)

        self.lbl_admin = tk.Label(
            right, text="● 管理员" if is_admin() else "⚠ 非管理员",
            bg=BG_CARD,
            fg=ACCENT if is_admin() else YELLOW,
            font=("Segoe UI", 9)
        )
        self.lbl_admin.pack(anchor="e")
        self.lbl_time = tk.Label(right, text="", bg=BG_CARD, fg=TEXT_MUTED,
                                 font=("Consolas", 9))
        self.lbl_time.pack(anchor="e")

        # ── Main body ────────────────────────────────────────────────────────
        body = tk.Frame(root, bg=BG_DEEP)
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=12)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        # Status Card
        self._build_status_card(body)

        # Action Buttons
        self._build_action_buttons(body)

        # Log
        self._build_log(body)

        # ── Footer ───────────────────────────────────────────────────────────
        foot = tk.Frame(root, bg=BG_CARD, height=28)
        foot.grid(row=2, column=0, sticky="ew")
        tk.Label(foot, text=f"{APP_NAME} {APP_VERSION}  ·  Windows DNS 自动化管理",
                 bg=BG_CARD, fg=TEXT_MUTED, font=("Segoe UI", 8)
                 ).pack(side="left", padx=14, pady=6)

    def _card(self, parent, row):
        f = tk.Frame(parent, bg=BG_CARD, bd=0, relief="flat")
        f.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        f.columnconfigure(0, weight=1)
        # Bottom border simulation
        tk.Frame(f, bg=BG_BORDER, height=1).pack(side="bottom", fill="x")
        return f

    def _build_status_card(self, parent):
        card = self._card(parent, 0)
        inner = tk.Frame(card, bg=BG_CARD)
        inner.pack(fill="x", padx=18, pady=14)
        inner.columnconfigure(1, weight=1)

        # Big status dot + text
        dot_col = tk.Frame(inner, bg=BG_CARD)
        dot_col.grid(row=0, column=0, rowspan=2, padx=(0, 16))
        self.canvas_dot = tk.Canvas(dot_col, width=44, height=44,
                                    bg=BG_CARD, highlightthickness=0)
        self.canvas_dot.pack()
        self._draw_dot(TEXT_MUTED)

        info_col = tk.Frame(inner, bg=BG_CARD)
        info_col.grid(row=0, column=1, sticky="w")

        self.lbl_status_title = tk.Label(
            info_col, text="检测中…", bg=BG_CARD, fg=TEXT_PRI,
            font=("Segoe UI Semibold", 14, "bold")
        )
        self.lbl_status_title.pack(anchor="w")
        self.lbl_status_sub = tk.Label(
            info_col, text="正在获取服务状态", bg=BG_CARD, fg=TEXT_SEC,
            font=("Segoe UI", 9)
        )
        self.lbl_status_sub.pack(anchor="w")

        # DNS info row
        dns_row = tk.Frame(inner, bg=BG_CARD)
        dns_row.grid(row=1, column=1, sticky="w", pady=(8, 0))

        def dns_kv(parent, key, var):
            k = tk.Label(parent, text=key, bg=BG_CARD, fg=TEXT_MUTED,
                         font=("Segoe UI", 9))
            k.pack(side="left")
            v = tk.Label(parent, textvariable=var, bg=BG_CARD, fg=ACCENT,
                         font=("Consolas", 9))
            v.pack(side="left", padx=(4, 16))

        self.var_adapter = tk.StringVar(value="—")
        self.var_cur_dns = tk.StringVar(value="—")
        self.var_bak_dns = tk.StringVar(value="—")
        dns_kv(dns_row, "网卡:",      self.var_adapter)
        dns_kv(dns_row, "当前 DNS:",  self.var_cur_dns)
        dns_kv(dns_row, "备份 DNS:",  self.var_bak_dns)

    def _draw_dot(self, color, size=18):
        c = self.canvas_dot
        c.delete("all")
        cx, cy = 22, 22
        # Glow ring
        c.create_oval(cx-size-4, cy-size-4, cx+size+4, cy+size+4,
                      fill="", outline=color, width=1)
        c.create_oval(cx-size, cy-size, cx+size, cy+size,
                      fill=color, outline="")

    def _build_action_buttons(self, parent):
        row = tk.Frame(parent, bg=BG_DEEP)
        row.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)

        self.btn_start = self._action_btn(
            row, "▶  启 动 SmartDNS", ACCENT, BG_DEEP, ACCENT_DIM,
            self._on_start, col=0
        )
        self.btn_stop = self._action_btn(
            row, "■  停 止 SmartDNS", RED, BG_DEEP, RED_DIM,
            self._on_stop, col=1
        )

    def _action_btn(self, parent, text, fg, bg, active_bg, cmd, col):
        btn = tk.Button(
            parent, text=text, command=cmd,
            bg=BG_CARD, fg=fg, activebackground=active_bg, activeforeground=fg,
            relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI Semibold", 11, "bold"),
            padx=0, pady=12
        )
        btn.grid(row=0, column=col, sticky="ew",
                 padx=(0 if col > 0 else 0, 6 if col == 0 else 0),
                 ipadx=10)
        if col == 0:
            btn.grid_configure(padx=(0, 6))
        else:
            btn.grid_configure(padx=(6, 0))

        # Hover effect
        def on_enter(e):
            if btn['state'] == 'normal':
                btn.config(bg=active_bg)
        def on_leave(e):
            btn.config(bg=BG_CARD)

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        return btn

    def _build_log(self, parent):
        lf = tk.Frame(parent, bg=BG_CARD)
        lf.grid(row=2, column=0, sticky="nsew")
        lf.rowconfigure(1, weight=1)
        lf.columnconfigure(0, weight=1)
        tk.Frame(lf, bg=BG_BORDER, height=1).grid(row=0, column=0, columnspan=2, sticky="ew")

        head = tk.Frame(lf, bg=BG_CARD)
        head.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(head, text="  操作日志", bg=BG_CARD, fg=TEXT_SEC,
                 font=("Segoe UI", 9)).pack(side="left", pady=6)
        tk.Button(head, text="清空", bg=BG_CARD, fg=TEXT_MUTED,
                  activebackground=BG_HOVER, activeforeground=TEXT_SEC,
                  relief="flat", bd=0, cursor="hand2",
                  font=("Segoe UI", 8), command=self._clear_log
                  ).pack(side="right", padx=10, pady=4)

        self.log_text = tk.Text(
            lf, bg=BG_CARD, fg=TEXT_PRI, insertbackground=ACCENT,
            font=("Consolas", 9), relief="flat", bd=0,
            selectbackground=BG_HOVER, selectforeground=TEXT_PRI,
            wrap="word", state="disabled", padx=12, pady=8
        )
        self.log_text.grid(row=1, column=0, sticky="nsew")

        sb = ttk.Scrollbar(lf, orient="vertical", command=self.log_text.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=sb.set)

        # Tag colors
        self.log_text.tag_config("info",    foreground=TEXT_PRI)
        self.log_text.tag_config("ok",      foreground=ACCENT)
        self.log_text.tag_config("warn",    foreground=YELLOW)
        self.log_text.tag_config("error",   foreground=RED)
        self.log_text.tag_config("muted",   foreground=TEXT_MUTED)
        self.log_text.tag_config("time",    foreground=TEXT_MUTED)

    # ─── Logging ──────────────────────────────────────────────────────────────
    def _log(self, msg, tag="info"):
        def _do():
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"[{ts}] ", "time")
            self.log_text.insert("end", f"{msg}\n", tag)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.after(0, _do)

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ─── Status Refresh ───────────────────────────────────────────────────────
    def _refresh_status(self):
        def _do():
            proc   = find_smartdns_process()
            adapter = get_active_adapter()
            cur_dns = get_current_dns(adapter) if adapter else None
            _, bak_dns = load_dns_backup()

            self.after(0, lambda: self._apply_status(proc, adapter, cur_dns, bak_dns))

        threading.Thread(target=_do, daemon=True).start()

    def _apply_status(self, proc, adapter, cur_dns, bak_dns):
        self.var_adapter.set(adapter or "未检测到")
        self.var_cur_dns.set(cur_dns or "—")
        self.var_bak_dns.set(bak_dns or "—")

        if proc:
            self._status = "running"
            self._draw_dot(ACCENT)
            self.lbl_status_title.config(text="服务运行中", fg=ACCENT)
            self.lbl_status_sub.config(
                text=f"PID {proc.pid}  ·  DNS 已切换至 {LOCAL_DNS}", fg=TEXT_SEC)
            self.btn_start.config(state="disabled", fg=TEXT_MUTED, cursor="")
            self.btn_stop.config(state="normal",   fg=RED, cursor="hand2")
        else:
            self._status = "stopped"
            self._draw_dot(TEXT_MUTED)
            self.lbl_status_title.config(text="服务已停止", fg=TEXT_SEC)
            self.lbl_status_sub.config(
                text="SmartDNS 未在运行", fg=TEXT_MUTED)
            self.btn_start.config(state="normal",   fg=ACCENT, cursor="hand2")
            self.btn_stop.config(state="disabled",  fg=TEXT_MUTED, cursor="")

    def _tick_clock(self):
        self.lbl_time.config(text=datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.after(1000, self._tick_clock)

    # ─── Confirm Dialog (custom) ───────────────────────────────────────────────
    def _confirm(self, title, message, yes_text="确认", no_text="取消"):
        """Modal confirm dialog; returns True/False."""
        result = {"value": False}
        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.geometry("440x180")
        dlg.configure(bg=BG_CARD)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        # Center
        self.update_idletasks()
        px = self.winfo_x() + (self.winfo_width()  - 440) // 2
        py = self.winfo_y() + (self.winfo_height() - 180) // 2
        dlg.geometry(f"+{px}+{py}")

        tk.Frame(dlg, bg=ACCENT, height=3).pack(fill="x")

        tk.Label(dlg, text=title, bg=BG_CARD, fg=TEXT_PRI,
                 font=("Segoe UI Semibold", 12, "bold"),
                 pady=12).pack()

        tk.Label(dlg, text=message, bg=BG_CARD, fg=TEXT_SEC,
                 font=("Segoe UI", 9), wraplength=400,
                 justify="center").pack(padx=20)

        btn_row = tk.Frame(dlg, bg=BG_CARD)
        btn_row.pack(pady=16)

        def _yes():
            result["value"] = True
            dlg.destroy()

        def _no():
            result["value"] = False
            dlg.destroy()

        tk.Button(btn_row, text=yes_text, bg=ACCENT, fg=BG_DEEP,
                  activebackground=ACCENT_DIM, activeforeground=BG_DEEP,
                  relief="flat", bd=0, cursor="hand2",
                  font=("Segoe UI Semibold", 10, "bold"),
                  width=10, pady=6, command=_yes).pack(side="left", padx=6)

        tk.Button(btn_row, text=no_text, bg=BG_BORDER, fg=TEXT_SEC,
                  activebackground=BG_HOVER, activeforeground=TEXT_PRI,
                  relief="flat", bd=0, cursor="hand2",
                  font=("Segoe UI", 10),
                  width=10, pady=6, command=_no).pack(side="left", padx=6)

        dlg.wait_window()
        return result["value"]

    # ─── Start Flow ───────────────────────────────────────────────────────────
    def _on_start(self):
        if self._busy:
            return
        if not is_admin():
            messagebox.showerror("权限不足",
                                 "请以管理员身份运行本程序。\n右键 → 以管理员身份运行。")
            return
        self._busy = True
        self.btn_start.config(state="disabled")
        threading.Thread(target=self._start_flow, daemon=True).start()

    def _start_flow(self):
        self._log("── 启动流程开始 ──", "muted")

        # 1. Check duplicate
        proc = find_smartdns_process()
        if proc:
            self._log(f"SmartDNS 进程已存在 (PID {proc.pid})，跳过启动。", "warn")
            self._busy = False
            self.after(0, self._refresh_status)
            return

        # 2. Get adapter & current DNS
        adapter = get_active_adapter()
        if not adapter:
            self._log("未检测到活动网卡，无法继续。", "error")
            self._busy = False
            return

        cur_dns = get_current_dns(adapter)
        self._log(f"活动网卡: {adapter}", "info")
        self._log(f"当前 DNS:  {cur_dns or '未获取到'}", "info")

        # ── 分支判断 ──────────────────────────────────────────────────────────
        # 情况 A：当前 DNS 已是本地 127.0.0.1 → 说明备份可能存在，尝试还原
        if cur_dns == LOCAL_DNS:
            self._log(f"检测到当前 DNS 已为 {LOCAL_DNS}，尝试读取备份并还原…", "warn")
            _, bak_dns = load_dns_backup()

            if not bak_dns:
                self._log("未找到备份记录且当前 DNS 已为本地代理，将尝试强制重置为 DHCP 防止断网。", "warn")
                reset_dns_to_dhcp(adapter)
                self._log(f"已将网卡 {adapter} 的 DNS 切换为自动获取。", "ok")
                self._busy = False
                self.after(0, self._refresh_status)
                return

            self._log(f"发现备份 DNS: {bak_dns}", "info")

            # 询问用户是否还原
            msg = (f"当前 DNS 已为 {LOCAL_DNS}（本地代理地址）。\n\n"
                   f"检测到备份 DNS: {bak_dns}\n"
                   f"网卡: {adapter}\n\n"
                   f"是否将 DNS 还原为备份值后再重新启动？")

            result_holder = {"ok": None}
            evt = threading.Event()

            def ask_restore():
                result_holder["ok"] = self._confirm(
                    "检测到异常 DNS 状态", msg, "还原并重启", "取消"
                )
                evt.set()

            self.after(0, ask_restore)
            evt.wait()

            if not result_holder["ok"]:
                self._log("用户取消操作。", "warn")
                self._busy = False
                self.after(0, lambda: self.btn_start.config(state="normal", fg=ACCENT))
                return

            # 还原 DNS
            set_dns(adapter, bak_dns)
            self._log(f"DNS 已还原为 {bak_dns}", "ok")
            delete_backup_file()
            self._log("备份文件已清理，重新以正常流程启动…", "muted")

            # 更新 cur_dns，继续走正常备份+切换流程
            cur_dns = bak_dns

        # ── 情况 B（含还原后续）：当前 DNS 不是本地 → 正常备份并切换 ────────
        # 3. Confirm backup
        msg = (f"检测到当前 DNS 为  {cur_dns or '未知'}\n\n"
               f"确认后将备份此地址，并将 DNS 切换为 {LOCAL_DNS}。\n"
               f"网卡: {adapter}")

        result_holder = {"ok": None}
        evt = threading.Event()

        def ask_backup():
            result_holder["ok"] = self._confirm(
                "确认备份当前 DNS", msg, "确认并启动", "取消"
            )
            evt.set()

        self.after(0, ask_backup)
        evt.wait()

        if not result_holder["ok"]:
            self._log("用户取消操作。", "warn")
            self._busy = False
            self.after(0, lambda: self.btn_start.config(state="normal", fg=ACCENT))
            return

        # 4. Backup
        save_dns_backup(adapter, cur_dns or "")
        self._log(f"DNS 已备份 → {BACKUP_FILE}", "ok")

        # 5. Switch DNS to local
        set_dns(adapter, LOCAL_DNS)
        self._log(f"系统 DNS 已切换为 {LOCAL_DNS}", "ok")

        # 6. Launch SmartDNS hidden
        try:
            proc = subprocess.Popen(
                SMARTDNS_ARGS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
                              | subprocess.DETACHED_PROCESS
            )
            write_pid_file(proc.pid)
            self._log(f"SmartDNS 已在后台启动 (PID {proc.pid})", "ok")
        except FileNotFoundError:
            self._log(f"找不到可执行文件: {SMARTDNS_EXE}", "error")
            self._log("请确保 smartdns.exe 在系统 PATH 中或同目录下。", "warn")
            # Rollback DNS
            set_dns(adapter, cur_dns or "")
            self._log("DNS 已回滚。", "warn")
            self._busy = False
            self.after(0, self._refresh_status)
            return
        except Exception as e:
            self._log(f"启动失败: {e}", "error")
            self._busy = False
            self.after(0, self._refresh_status)
            return

        self._log("SmartDNS 启动完成，系统 DNS 已接管。", "ok")
        self._busy = False
        self.after(500, self._refresh_status)

    # ─── Stop Flow ────────────────────────────────────────────────────────────
    def _on_stop(self):
        if self._busy:
            return
        if not is_admin():
            messagebox.showerror("权限不足",
                                 "请以管理员身份运行本程序。")
            return
        self._busy = True
        self.btn_stop.config(state="disabled")
        threading.Thread(target=self._stop_flow, daemon=True).start()

    def _stop_flow(self):
        self._log("── 停止流程开始 ──", "muted")

        # 1. Locate process
        proc = find_smartdns_process()
        pid  = read_pid_file()

        if not proc and pid:
            try:
                proc = psutil.Process(pid)
            except psutil.NoSuchProcess:
                proc = None

        if not proc:
            self._log("未找到 SmartDNS 进程。", "warn")
        else:
            # 2. Kill
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(proc.pid)],
                    capture_output=True
                )
                self._log(f"SmartDNS (PID {proc.pid}) 已强制终止。", "ok")
            except Exception as e:
                self._log(f"终止失败: {e}", "error")

        delete_pid_file()

        # 3. DNS Restore confirm
        adapter, bak_dns = load_dns_backup()
        if not bak_dns:
            self._log("未找到 DNS 备份记录，将尝试将 DNS 设置为自动获取（DHCP）以防止断网。", "warn")
            if not adapter: adapter = get_active_adapter()
            if adapter:
                reset_dns_to_dhcp(adapter)
                self._log(f"已将网卡 {adapter} 的 DNS 设置为自动获取 (DHCP)。", "ok")
            else:
                self._log("未定位到活动网卡，请手动检查网络设置。", "error")
            self._busy = False
            self.after(0, self._refresh_status)
            return

        msg = (f"SmartDNS 已停止。\n\n"
               f"是否将系统 DNS 还原为备份值: {bak_dns}？\n"
               f"网卡: {adapter}\n\n"
               f"⚠  若选否，DNS 将保持 {LOCAL_DNS}，可能导致断网。")

        result_holder = {"ok": None}
        evt = threading.Event()

        def ask():
            result_holder["ok"] = self._confirm(
                "还原系统 DNS", msg, "立即还原", "暂不还原"
            )
            evt.set()

        self.after(0, ask)
        evt.wait()

        if result_holder["ok"]:
            set_dns(adapter, bak_dns)
            self._log(f"系统 DNS 已还原为 {bak_dns}", "ok")
            delete_backup_file()
            self._log("备份文件已清理。", "muted")
            self._log("服务已停止，网络设置已恢复。", "ok")
        else:
            self._log("用户选择暂不还原 DNS，当前 DNS 仍为 127.0.0.1。", "warn")

        self._busy = False
        self.after(500, self._refresh_status)


# ══════════════════════════════════════════════════════════════════════════════
#  Entry Point
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if sys.platform == "win32" and not is_admin():
        if messagebox:
            pass  # messagebox not yet available before Tk()
        # Re-launch as admin
        try:
            run_as_admin()
        except Exception:
            pass
        sys.exit(0)

    app = SmartDNSApp()

    # Initial log entry
    app._log("SmartDNS Manager 已启动", "ok")
    if is_admin():
        app._log("已获取管理员权限", "ok")
    else:
        app._log("⚠ 未以管理员身份运行，部分功能将不可用", "warn")

    app.mainloop()
