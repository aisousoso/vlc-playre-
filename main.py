import tkinter as tk
from tkinter import filedialog, ttk
import vlc
import re
import requests
import json
import os
import threading
import platform
import datetime
from PIL import Image, ImageTk
from io import BytesIO

SAVE_FILE = "data.json"

class IPTVPro:
    def __init__(self, root):
        self.root = root
        self.root.title("Show IPTV Pro MAX 🔥")
        self.root.geometry("1200x700")
        self.root.configure(bg="#0f0f0f")

        # ===== تهيئة VLC =====
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()

        # ===== بيانات التطبيق =====
        self.channels = []
        self.filtered = []
        self.favorites = set()
        self.current_url = ""
        self.is_playing = False
        self.is_maximized = False  # حالة التكبير

        self.load_data()

        # ===== تهيئة الثيم =====
        self._setup_style()

        # ===== الهيكل الرئيسي =====
        main_frame = ttk.Frame(root)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # اللوحة اليسرى (ثابتة العرض)
        self.left_panel = ttk.Frame(main_frame)
        self.left_panel.pack(side="left", fill="y", padx=(0, 5))
        self.left_panel.config(width=320)
        self.left_panel.pack_propagate(False)

        # اللوحة اليمنى (الفيديو + التحكم)
        self.right_panel = ttk.Frame(main_frame)
        self.right_panel.pack(side="right", fill="both", expand=True)

        # 🎬 شاشة العرض
        self.canvas = tk.Canvas(self.right_panel, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, pady=(0, 8))

        # ربط VLC حسب النظام
        sys_name = platform.system()
        if sys_name == "Windows":
            self.player.set_hwnd(self.canvas.winfo_id())
        elif sys_name == "Linux":
            self.player.set_xwindow(self.canvas.winfo_id())

        # 🎛️ أزرار التحكم أفقية
        self.controls_frame = ttk.Frame(self.right_panel)
        self.controls_frame.pack(fill="x", side="bottom", pady=(0, 2))

        btns = [
            ("📂 ملف", self.load_file),
            ("🌐 URL", self.load_url),
            ("⭐ مفضلة", self.add_favorite),
            ("▶ تشغيل", self.play),
            ("⏸ إيقاف", self.pause),
            ("🎬 ترجمة", self.load_subtitle),
            ("🔲 تكبير", self.toggle_video_size)  # زر التكبير
        ]
        for txt, cmd in btns:
            ttk.Button(self.controls_frame, text=txt, command=cmd, padding=(10, 5)).pack(side="left", padx=4)

        # 🔊 التحكم بالصوت
        vol_frame = ttk.Frame(self.controls_frame)
        vol_frame.pack(side="right", padx=5)
        self.volume_var = tk.IntVar(value=70)
        self.volume = ttk.Scale(vol_frame, from_=0, to=100, orient="horizontal",
                                variable=self.volume_var, command=self.set_volume)
        self.volume.pack(side="left", padx=5)
        ttk.Label(vol_frame, text="🔊").pack(side="left")

        # ===== عناصر اللوحة اليسرى =====
        self.search = ttk.Entry(self.left_panel, font=("Segoe UI", 11))
        self.search.pack(fill="x", pady=(0, 5))
        self.search.insert(0, "🔍 ابحث عن قناة...")
        self.search.bind("<FocusIn>", self._clear_search_hint)
        self.search.bind("<FocusOut>", self._add_search_hint)
        self.search.bind("<KeyRelease>", self.filter_channels)

        self.category = tk.StringVar(value="الكل")
        self.category_combo = ttk.Combobox(self.left_panel, textvariable=self.category, state="readonly", font=("Segoe UI", 10))
        self.category_combo.pack(fill="x", pady=(0, 5))
        self.category_combo["values"] = ["الكل"]
        self.category_combo.bind("<<ComboboxSelected>>", self.filter_channels)

        list_frame = ttk.Frame(self.left_panel)
        list_frame.pack(fill="both", expand=True)

        self.scrollbar = ttk.Scrollbar(list_frame)
        self.scrollbar.pack(side="right", fill="y")

        self.listbox = tk.Listbox(list_frame, bg="#1e1e1e", fg="#ffffff",
                                  font=("Segoe UI", 10), selectbackground="#3a7bd5",
                                  selectforeground="#ffffff", highlightthickness=0,
                                  yscrollcommand=self.scrollbar.set, activestyle="none")
        self.listbox.pack(side="left", fill="both", expand=True)
        self.scrollbar.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", self.play_channel)

        self.logo_label = ttk.Label(self.left_panel, background="#0f0f0f")
        self.logo_label.pack(pady=10)

        # ===== شريط الحالة =====
        self.status_var = tk.StringVar(value="✅ جاهز")
        ttk.Label(root, textvariable=self.status_var, foreground="#888888", background="#0f0f0f", font=("Segoe UI", 9)).pack(fill="x", side="bottom")

        # ===== اختصارات لوحة المفاتيح =====
        self.root.bind("<space>", lambda e: self.toggle_play())
        self.root.bind("<f>", lambda e: self.add_favorite())
        self.root.bind("<Control-o>", lambda e: self.load_file())
        self.root.bind("<Control-u>", lambda e: self.load_url())
        self.root.bind("<Escape>", lambda e: self.toggle_video_size() if self.is_maximized else None)
        self.canvas.bind("<Double-1>", lambda e: self.toggle_video_size())  # نقر مزدوج على الفيديو

        # ===== تشغيل حلقة التحديث (محفوظة كما طلبت) =====
        self.update()

    # ===== تكبير/تصغير شاشة العرض =====
    def toggle_video_size(self):
        self.is_maximized = not self.is_maximized
        if self.is_maximized:
            self.left_panel.pack_forget()
            self.canvas.focus_set()  # تفعيل اختصارات الكيبورد
            self.status_var.set("🔲 وضع التكبير - اضغط ESC أو 🔲 للعودة")
        else:
            self.left_panel.pack(side="left", fill="y", padx=(0, 5))
            self.status_var.set("✅ جاهز")

    # ===== مساعدات شريط البحث =====
    def _clear_search_hint(self, event=None):
        if self.search.get() == "🔍 ابحث عن قناة...":
            self.search.delete(0, "end")
            self.search.config(foreground="black")

    def _add_search_hint(self, event=None):
        if self.search.get() == "":
            self.search.insert(0, "🔍 ابحث عن قناة...")
            self.search.config(foreground="gray")

    # ===== ثيم الواجهة =====
    def _setup_style(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background='#0f0f0f')
        style.configure('TButton', background='#2a2a2a', foreground='#ffffff', font=('Segoe UI', 10), padding=6)
        style.map('TButton', background=[('active', '#3a3a3a'), ('pressed', '#1a1a1a')])
        style.configure('TEntry', background='#1e1e1e', foreground='#ffffff', fieldbackground='#1e1e1e', font=('Segoe UI', 11))
        style.configure('TCombobox', background='#1e1e1e', foreground='#ffffff', fieldbackground='#1e1e1e', font=('Segoe UI', 10))
        style.configure('TScrollbar', background='#1e1e1e', troughcolor='#0f0f0f')
        style.configure('TScale', background='#0f0f0f', troughcolor='#1e1e1e')
        style.configure('TLabel', background='#0f0f0f', foreground='#ffffff', font=('Segoe UI', 10))

    # ===== تحميل ملف =====
    def load_file(self):
        file = filedialog.askopenfilename(filetypes=[("M3U files", "*.m3u *.m3u8")])
        if file:
            self.status_var.set("⏳ جاري قراءة الملف...")
            threading.Thread(target=self._parse_file_thread, args=(file,), daemon=True).start()

    def _parse_file_thread(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            self.root.after(0, lambda: self._on_m3u_loaded(text))
        except Exception as e:
            self.root.after(0, lambda: self.status_var.set(f"❌ خطأ في القراءة: {e}"))

    # ===== تحميل URL =====
    def load_url(self):
        win = tk.Toplevel(self.root)
        win.title("رابط IPTV")
        win.geometry("400x140")
        win.configure(bg="#0f0f0f")
        win.resizable(False, False)

        ttk.Label(win, text="أدخل رابط ملف M3U/M3U8:", foreground="white", background="#0f0f0f").pack(pady=(10, 5))
        entry = ttk.Entry(win, width=45)
        entry.pack(pady=5)

        def load_thread():
            url = entry.get().strip()
            if not url: return
            self.root.after(0, lambda: self.status_var.set("⏳ جاري التحميل من الرابط..."))
            try:
                res = requests.get(url, timeout=15)
                res.raise_for_status()
                self.root.after(0, lambda: self._on_m3u_loaded(res.text))
            except Exception as e:
                self.root.after(0, lambda: self.status_var.set(f"❌ فشل التحميل: {e}"))
            finally:
                self.root.after(0, win.destroy)

        ttk.Button(win, text="تحميل", command=lambda: threading.Thread(target=load_thread, daemon=True).start()).pack(pady=10)
        win.grab_set()

    # ===== معالجة البيانات بعد التحميل =====
    def _on_m3u_loaded(self, text):
        self.channels = self.parse_m3u_text(text)
        self.update_list(self.channels)
        self._update_categories()
        self.status_var.set("✅ تم تحميل القنوات بنجاح")

    # ===== تحليل M3U =====
    def parse_m3u_text(self, text):
        channels = []
        name = logo = group = ""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#EXTINF"):
                name_match = re.search(r",(.*)", line)
                name = name_match.group(1).strip() if name_match else "غير معروف"
                logo_match = re.search(r'tvg-logo="([^"]*)"', line)
                logo = logo_match.group(1) if logo_match else ""
                group_match = re.search(r'group-title="([^"]*)"', line)
                group = group_match.group(1) if group_match else "أخرى"
            elif line.startswith(("http://", "https://", "rtmp://", "rtp://")):
                channels.append((name, line, logo, group))
        return channels

    # ===== تحديث الفئات ديناميكيًا =====
    def _update_categories(self):
        groups = sorted(set(c[3] for c in self.channels))
        self.category_combo["values"] = ["الكل"] + groups
        self.category.set("الكل")

    # ===== عرض القائمة =====
    def update_list(self, data):
        self.filtered = data
        self.listbox.delete(0, tk.END)
        for ch in data:  # ✅ تم إصلاح الحلقة
            star = "⭐ " if ch[1] in self.favorites else ""
            self.listbox.insert(tk.END, f"{star}{ch[0]}")

    def filter_channels(self, event=None):
        q = self.search.get().lower()
        cat = self.category.get()
        self.filtered = [c for c in self.channels
                         if q in c[0].lower() and (cat == "الكل" or cat == c[3])]
        self.update_list(self.filtered)

    # ===== تشغيل القناة =====
    def play_channel(self, event):
        i = self.listbox.curselection()
        if i:
            ch = self.filtered[i[0]]
            self.current_url = ch[1]
            media = self.instance.media_new(ch[1])
            self.player.set_media(media)
            self.player.play()
            self.is_playing = True
            self.show_logo(ch[2])
            self.save_data()
            self.status_var.set(f"📺 جاري تشغيل: {ch[0]}")

    # ===== تحميل الشعار (غير متزامن) =====
    def show_logo(self, url):
        if url:
            threading.Thread(target=self._fetch_logo, args=(url,), daemon=True).start()

    def _fetch_logo(self, url):
        try:
            img = requests.get(url, timeout=10).content
            image = Image.open(BytesIO(img)).resize((120, 120), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self.root.after(0, lambda: self.logo_label.config(image=photo))
            self.logo_label.image = photo
        except Exception:
            pass

    # ===== مفضلة =====
    def add_favorite(self):
        if self.current_url:
            if self.current_url in self.favorites:
                self.favorites.remove(self.current_url)
                self.status_var.set("➖ تم الإزالة من المفضلة")
            else:
                self.favorites.add(self.current_url)
                self.status_var.set("➕ تم الإضافة إلى المفضلة")
            self.update_list(self.filtered)
            self.save_data()

    # ===== ترجمة =====
    def load_subtitle(self):
        file = filedialog.askopenfilename(filetypes=[("SRT", "*.srt"), ("All", "*.*")])
        if file:
            self.player.video_set_subtitle_file(file)
            self.status_var.set("🎬 تم تحميل ملف الترجمة")

    # ===== تحكم =====
    def play(self):
        self.player.play()
        self.is_playing = True
        self.status_var.set("▶ تشغيل")

    def pause(self):
        self.player.pause()
        self.status_var.set("⏸ إيقاف مؤقت")

    def toggle_play(self):
        if self.is_playing:
            self.pause()
            self.is_playing = False
        else:
            self.play()

    def set_volume(self, v):
        self.player.audio_set_volume(int(float(v)))

    # ===== دالة update() (محفوظة حسب طلبك) =====
    def update(self):
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        if not self.status_var.get().startswith(("⏳", "❌", "✅", "📺", "➕", "➖", "🎬", "🔲")):
            self.status_var.set(f"🕒 {current_time}")
        self.root.after(1000, self.update)

    # ===== حفظ وتحميل البيانات =====
    def save_data(self):
        data = {"favorites": list(self.favorites), "last": self.current_url}
        try:
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception: pass

    def load_data(self):
        if os.path.exists(SAVE_FILE):
            try:
                with open(SAVE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.favorites = set(data.get("favorites", []))
                self.current_url = data.get("last", "")
            except (json.JSONDecodeError, Exception): pass


if __name__ == "__main__":
    root = tk.Tk()
    app = IPTVPro(root)
    root.mainloop()