"""
YOUTUBE SILENXS - YouTube Downloader
=====================================
Desktop application for downloading YouTube videos.

Required libraries (install via pip):
    pip install PyQt5 yt-dlp

Required external binary:
    ffmpeg.exe  -> place in ./ffmpeg/ folder next to main.py
                   (download from: https://www.gyan.dev/ffmpeg/builds/  -> "release essentials")

Run from source (IDLE / cmd):
    python main.py

Build standalone EXE (one file):
    pip install pyinstaller
    pyinstaller --onefile --noconsole --name "YouTubeSilenxs" ^
        --add-binary "ffmpeg/ffmpeg.exe;ffmpeg" ^
        --hidden-import PyQt5 ^
        main.py

After build the EXE is in ./dist/YouTubeSilenxs.exe
"""

import os
import sys
import re
import traceback
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QFontDatabase, QColor, QPalette, QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSlider, QProgressBar, QFileDialog,
    QMessageBox, QComboBox, QSizePolicy, QSpacerItem, QFrame
)

try:
    import yt_dlp
except ImportError:
    print("ERROR: yt-dlp not installed. Run: pip install yt-dlp")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def resource_path(relative: str) -> str:
    """Get absolute path to a resource (works for dev and PyInstaller --onefile)."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative)


def get_ffmpeg_path() -> str | None:
    """Locate bundled ffmpeg.exe (works in dev and after PyInstaller --onefile build)."""
    candidates = [
        resource_path(os.path.join("ffmpeg", "ffmpeg.exe")),
        resource_path("ffmpeg.exe"),
    ]
    if os.name != "nt":  # linux/mac fallback for testing
        candidates += [
            resource_path(os.path.join("ffmpeg", "ffmpeg")),
            resource_path("ffmpeg"),
        ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


# ---------------------------------------------------------------------------
# ASCII ART
# ---------------------------------------------------------------------------
ASCII_YOUTUBE = r"""
 __   __  _______  __   __  _______  __   __  _______  _______ 
|  | |  ||       ||  | |  ||       ||  | |  ||  _    ||       |
|  |_|  ||   _   ||  | |  ||_     _||  | |  || |_|   ||    ___|
|       ||  | |  ||  |_|  |  |   |  |  |_|  ||       ||   |___ 
|_     _||  |_|  ||       |  |   |  |       ||  _   | |    ___|
  |   |  |       ||       |  |   |  |       || |_|   ||   |___ 
  |___|  |_______||_______|  |___|  |_______||_______||_______|
"""

ASCII_SILENXS = r"""
 _______  ___   ___      __   __  _______  ______    __   __  _______  __    _  ______  
|       ||   | |   |    |  | |  ||       ||    _ |  |  | |  ||   _   ||  |  | ||      | 
|  _____||   | |   |    |  |_|  ||    ___||   | ||  |  |_|  ||  |_|  ||   |_| ||  _    |
| |_____ |   | |   |    |       ||   |___ |   |_||_ |       ||       ||       || | |   |
|_____  ||   | |   |___ |       ||    ___||    __  ||       ||       ||  _    || |_|   |
 _____| ||   | |       | |     | |   |___ |   |  | ||   _   ||   _   || | |   ||       |
|_______||___| |_______|  |___|  |_______||___|  |_||__| |__||__| |__||_|  |__||______| 
"""


def rainbow_html(text: str) -> str:
    """Return HTML where each non-empty line gets a different rainbow color."""
    colors = [
        "#ff3b3b", "#ff8c1a", "#ffd400", "#3ddc84",
        "#1ec8ff", "#5b6dff", "#c44dff",
    ]
    lines = text.splitlines()
    out = []
    ci = 0
    for line in lines:
        if line.strip() == "":
            out.append("&nbsp;")
            continue
        color = colors[ci % len(colors)]
        ci += 1
        safe = (line.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace(" ", "&nbsp;"))
        out.append(f'<span style="color:{color};">{safe}</span>')
    return "<pre style='font-family: Consolas, monospace; font-size:11px; line-height:1.0; margin:0;'>" \
           + "<br>".join(out) + "</pre>"


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------
class FetchInfoThread(QThread):
    """Fetch video metadata + available formats (no download)."""
    success = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            self.success.emit(info)
        except yt_dlp.utils.DownloadError as e:
            msg = str(e).lower()
            if "name or service not known" in msg or "getaddrinfo" in msg \
                    or "failed to resolve" in msg or "network" in msg \
                    or "unable to download webpage" in msg:
                self.failed.emit("NETWORK")
            else:
                self.failed.emit("NOTFOUND")
        except Exception as e:
            self.failed.emit(f"ERROR:{e}")


class DownloadThread(QThread):
    """Download a video using yt-dlp with chosen format."""
    progress = pyqtSignal(float, str)   # percent, status text
    finished_ok = pyqtSignal(str)       # final filepath
    failed = pyqtSignal(str)

    def __init__(self, url: str, format_selector: str, output_dir: str,
                 output_filename: str | None, ffmpeg_path: str | None):
        super().__init__()
        self.url = url
        self.format_selector = format_selector
        self.output_dir = output_dir
        self.output_filename = output_filename
        self.ffmpeg_path = ffmpeg_path
        self._final_path = None

    def _hook(self, d):
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            pct = (downloaded / total * 100) if total else 0
            speed_str = f"{speed/1024/1024:.2f} MB/s" if speed else "..."
            txt = f"Downloading... {pct:.1f}%  |  {speed_str}  |  ETA {eta}s"
            self.progress.emit(pct, txt)
        elif status == "finished":
            self.progress.emit(100.0, "Merging / finalizing...")
            self._final_path = d.get("filename")

    def run(self):
        try:
            outtmpl = os.path.join(
                self.output_dir,
                self.output_filename if self.output_filename else "%(title)s.%(ext)s",
            )
            ydl_opts = {
                "format": self.format_selector,
                "outtmpl": outtmpl,
                "noplaylist": True,
                "progress_hooks": [self._hook],
                "quiet": True,
                "no_warnings": True,
                "merge_output_format": "mp4",
            }
            if self.ffmpeg_path:
                ydl_opts["ffmpeg_location"] = self.ffmpeg_path

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                final = ydl.prepare_filename(info)
                # if merged to mp4, extension may have changed
                base, _ = os.path.splitext(final)
                for ext in (".mp4", ".mkv", ".webm", ".m4a", ".mp3"):
                    if os.path.isfile(base + ext):
                        final = base + ext
                        break
            self.finished_ok.emit(final)
        except yt_dlp.utils.DownloadError as e:
            msg = str(e).lower()
            if "ffmpeg" in msg:
                self.failed.emit("FFmpeg error - the program could not merge audio+video. "
                                 "Make sure ffmpeg.exe is in the ./ffmpeg/ folder.")
            elif "network" in msg or "getaddrinfo" in msg:
                self.failed.emit("Network error during download.")
            else:
                self.failed.emit(f"Download error: {e}")
        except Exception as e:
            self.failed.emit(f"Unexpected error: {e}\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Stylesheet (dark theme)
# ---------------------------------------------------------------------------
APP_STYLE = """
* { font-family: 'Segoe UI', Arial, sans-serif; }
QMainWindow, QWidget { background-color: #0e0e10; color: #f1f1f1; }
QLabel#Title { color: #ffffff; font-size: 18px; font-weight: 600; }
QLabel#Sub   { color: #aaaaaa; font-size: 12px; }
QLineEdit {
    background-color: #1a1a1d; border: 1px solid #333; border-radius: 6px;
    padding: 10px 12px; font-size: 14px; color: #ffffff;
    selection-background-color: #ff0033;
}
QLineEdit:focus { border: 1px solid #ff0033; }
QPushButton {
    background-color: #ff0033; color: white; border: none;
    border-radius: 6px; padding: 10px 20px; font-size: 14px; font-weight: 600;
}
QPushButton:hover  { background-color: #ff2a52; }
QPushButton:pressed{ background-color: #cc0029; }
QPushButton:disabled{ background-color: #444; color: #888; }
QPushButton#Secondary {
    background-color: #2a2a2e; color: #f1f1f1; border: 1px solid #444;
}
QPushButton#Secondary:hover { background-color: #3a3a3e; }
QPushButton#Retry { background-color: #f5a623; color: #111; }
QPushButton#Retry:hover { background-color: #ffb84d; }

QProgressBar {
    background-color: #1a1a1d; border: 1px solid #333; border-radius: 6px;
    text-align: center; color: white; height: 22px;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #ff0033, stop:1 #ff8c1a);
    border-radius: 5px;
}

QSlider::groove:horizontal {
    height: 8px; background: #2a2a2e; border-radius: 4px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #ff0033, stop:1 #ff8c1a);
    border-radius: 4px;
}
QSlider::handle:horizontal {
    background: #ffffff; border: 2px solid #ff0033;
    width: 18px; margin: -6px 0; border-radius: 9px;
}
QComboBox {
    background-color: #1a1a1d; border: 1px solid #333; border-radius: 6px;
    padding: 6px 10px; color: white; min-width: 120px;
}
QComboBox QAbstractItemView {
    background: #1a1a1d; color: white; selection-background-color: #ff0033;
}
QLabel#Status { color: #cccccc; font-size: 13px; }
QLabel#Error  { color: #ff5566; font-size: 13px; font-weight: 600; }
QFrame#Card {
    background-color: #141417; border: 1px solid #232327; border-radius: 10px;
}
"""


# ---------------------------------------------------------------------------
# Page 1 - URL input
# ---------------------------------------------------------------------------
class UrlPage(QWidget):
    submitted = pyqtSignal(dict)  # emits info dict on success

    def __init__(self):
        super().__init__()
        self.fetch_thread: FetchInfoThread | None = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(16)

        # ASCII rainbow titles
        ascii1 = QLabel()
        ascii1.setText(rainbow_html(ASCII_YOUTUBE))
        ascii1.setAlignment(Qt.AlignCenter)
        ascii1.setTextFormat(Qt.RichText)
        root.addWidget(ascii1)

        ascii2 = QLabel()
        ascii2.setText(rainbow_html(ASCII_SILENXS))
        ascii2.setAlignment(Qt.AlignCenter)
        ascii2.setTextFormat(Qt.RichText)
        root.addWidget(ascii2)

        root.addSpacing(10)

        card = QFrame(); card.setObjectName("Card")
        cardLay = QVBoxLayout(card)
        cardLay.setContentsMargins(24, 20, 24, 20)
        cardLay.setSpacing(12)

        title = QLabel("Enter YouTube URL"); title.setObjectName("Title")
        sub = QLabel("Paste a video link below and click Search."); sub.setObjectName("Sub")
        cardLay.addWidget(title)
        cardLay.addWidget(sub)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.url_input.returnPressed.connect(self.on_search)
        cardLay.addWidget(self.url_input)

        btnRow = QHBoxLayout()
        btnRow.addStretch(1)
        self.search_btn = QPushButton("Search")
        self.search_btn.setMinimumWidth(140)
        self.search_btn.clicked.connect(self.on_search)
        btnRow.addWidget(self.search_btn)
        cardLay.addLayout(btnRow)

        self.status_lbl = QLabel(""); self.status_lbl.setObjectName("Status")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        cardLay.addWidget(self.status_lbl)

        root.addWidget(card)
        root.addStretch(1)

    def on_search(self):
        url = self.url_input.text().strip()
        if not url:
            self.status_lbl.setText("Please paste a YouTube URL first.")
            self.status_lbl.setObjectName("Error")
            self.status_lbl.setStyleSheet("color:#ff5566; font-weight:600;")
            return
        if not re.search(r"(youtube\.com|youtu\.be)", url, re.IGNORECASE):
            self.status_lbl.setText("This does not look like a YouTube URL.")
            self.status_lbl.setStyleSheet("color:#ff5566; font-weight:600;")
            return

        self.search_btn.setEnabled(False)
        self.status_lbl.setStyleSheet("color:#cccccc;")
        self.status_lbl.setText("Searching...")

        self.fetch_thread = FetchInfoThread(url)
        self.fetch_thread.success.connect(self._on_ok)
        self.fetch_thread.failed.connect(self._on_fail)
        self.fetch_thread.start()

    def _on_ok(self, info):
        self.search_btn.setEnabled(True)
        self.status_lbl.setText("")
        info["_source_url"] = self.url_input.text().strip()
        self.submitted.emit(info)

    def _on_fail(self, code: str):
        self.search_btn.setEnabled(True)
        if code == "NETWORK":
            msg = ("Connection to YouTube failed.\n"
                   "Check your internet connection and DNS servers.")
        elif code == "NOTFOUND":
            msg = ("Video not found, or YouTube service unreachable.\n"
                   "Check the URL, your internet connection and DNS servers.")
        else:
            msg = f"Error: {code}"
        QMessageBox.critical(self, "Error", msg)


# ---------------------------------------------------------------------------
# Page 2 - quality select + download
# ---------------------------------------------------------------------------
class DownloadPage(QWidget):
    back_requested = pyqtSignal()

    def __init__(self, ffmpeg_path: str | None):
        super().__init__()
        self.ffmpeg_path = ffmpeg_path
        self.info: dict = {}
        self.url: str = ""
        self.video_qualities: list[dict] = []   # [{label, height, format_id}]
        self.audio_qualities: list[dict] = []   # [{label, abr, format_id, ext}]
        self.download_thread: DownloadThread | None = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 24, 40, 24)
        root.setSpacing(14)

        # header
        topRow = QHBoxLayout()
        back_btn = QPushButton("\u2190 Back")
        back_btn.setObjectName("Secondary")
        back_btn.setMaximumWidth(100)
        back_btn.clicked.connect(self.back_requested.emit)
        topRow.addWidget(back_btn)
        topRow.addStretch(1)
        root.addLayout(topRow)

        # tiny rainbow header
        header = QLabel(rainbow_html(ASCII_SILENXS))
        header.setAlignment(Qt.AlignCenter)
        header.setTextFormat(Qt.RichText)
        root.addWidget(header)

        self.title_lbl = QLabel("")
        self.title_lbl.setObjectName("Title")
        self.title_lbl.setAlignment(Qt.AlignCenter)
        self.title_lbl.setWordWrap(True)
        root.addWidget(self.title_lbl)

        # CARD: format/quality
        card = QFrame(); card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(14)

        # Format selector (Video / Audio)
        formRow = QHBoxLayout()
        formRow.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Video (MP4)", "Audio only (MP3)"])
        self.format_combo.currentIndexChanged.connect(self._refresh_quality_widget)
        formRow.addWidget(self.format_combo)
        formRow.addStretch(1)
        cl.addLayout(formRow)

        # Quality slider + label
        qLabel = QLabel("Quality:")
        cl.addWidget(qLabel)

        sliderRow = QHBoxLayout()
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setMinimum(0)
        self.quality_slider.setMaximum(0)
        self.quality_slider.setTickPosition(QSlider.TicksBelow)
        self.quality_slider.setTickInterval(1)
        self.quality_slider.setSingleStep(1)
        self.quality_slider.setPageStep(1)
        self.quality_slider.setTracking(True)
        # Klik na pasek = natychmiastowy skok do tej pozycji (nie tylko o jeden krok)
        self.quality_slider.setStyleSheet("")  # zachowujemy globalny CSS
        from PyQt5.QtWidgets import QStyle, QStyleOptionSlider
        def _slider_mouse_press(ev, _s=self.quality_slider):
            if ev.button() == Qt.LeftButton:
                opt = QStyleOptionSlider()
                _s.initStyleOption(opt)
                groove = _s.style().subControlRect(
                    QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, _s)
                handle = _s.style().subControlRect(
                    QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, _s)
                slider_min = groove.x()
                slider_max = groove.right() - handle.width() + 1
                pos = ev.x() - handle.width() // 2
                val = QStyle.sliderValueFromPosition(
                    _s.minimum(), _s.maximum(),
                    pos - slider_min, slider_max - slider_min, opt.upsideDown)
                _s.setValue(val)
                ev.accept()
            else:
                QSlider.mousePressEvent(_s, ev)
        self.quality_slider.mousePressEvent = _slider_mouse_press
        self.quality_slider.valueChanged.connect(self._update_quality_label)
        sliderRow.addWidget(self.quality_slider, 1)

        self.quality_value_lbl = QLabel("-")
        self.quality_value_lbl.setMinimumWidth(110)
        self.quality_value_lbl.setAlignment(Qt.AlignCenter)
        self.quality_value_lbl.setStyleSheet(
            "background:#1a1a1d; border:1px solid #333; border-radius:6px;"
            "padding:6px 10px; font-weight:600; color:#ff8c1a;"
        )
        sliderRow.addWidget(self.quality_value_lbl)
        cl.addLayout(sliderRow)

        # Buttons row
        btnRow = QHBoxLayout()
        self.dl_default_btn = QPushButton("Download (save to Downloads)")
        self.dl_default_btn.clicked.connect(lambda: self.start_download(choose_path=False))
        btnRow.addWidget(self.dl_default_btn)

        self.dl_choose_btn = QPushButton("Download (save to...)")
        self.dl_choose_btn.setObjectName("Secondary")
        self.dl_choose_btn.clicked.connect(lambda: self.start_download(choose_path=True))
        btnRow.addWidget(self.dl_choose_btn)
        cl.addLayout(btnRow)

        root.addWidget(card)

        # CARD: progress
        prog_card = QFrame(); prog_card.setObjectName("Card")
        pl = QVBoxLayout(prog_card)
        pl.setContentsMargins(24, 16, 24, 16)
        pl.setSpacing(8)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        pl.addWidget(self.progress)

        statusRow = QHBoxLayout()
        self.status_lbl = QLabel("Idle.")
        self.status_lbl.setObjectName("Status")
        statusRow.addWidget(self.status_lbl, 1)

        self.retry_btn = QPushButton("Try again")
        self.retry_btn.setObjectName("Retry")
        self.retry_btn.setMaximumWidth(140)
        self.retry_btn.hide()
        self.retry_btn.clicked.connect(self._on_retry)
        statusRow.addWidget(self.retry_btn)
        pl.addLayout(statusRow)

        # download another button (after success)
        self.another_btn = QPushButton("Download another file")
        self.another_btn.setObjectName("Secondary")
        self.another_btn.hide()
        self.another_btn.clicked.connect(self.back_requested.emit)
        pl.addWidget(self.another_btn)

        root.addWidget(prog_card)
        root.addStretch(1)

    # ------------------------------------------------------------------ data
    def load_info(self, info: dict):
        self.info = info
        self.url = info.get("_source_url") or info.get("webpage_url") or ""
        title = info.get("title", "Unknown title")
        duration = info.get("duration") or 0
        mins = duration // 60; secs = duration % 60
        self.title_lbl.setText(f"{title}   \u2022   {mins}:{secs:02d}")

        formats = info.get("formats") or []

        # --- Video qualities (heights) deduplicated, sorted asc ---
        v_seen: dict[int, dict] = {}
        for f in formats:
            if f.get("vcodec") and f.get("vcodec") != "none":
                h = f.get("height")
                if not h:
                    continue
                # prefer mp4 with audio if available, else best for that height
                cur = v_seen.get(h)
                score = 0
                if f.get("ext") == "mp4": score += 2
                if f.get("acodec") and f.get("acodec") != "none": score += 1
                tbr = f.get("tbr") or 0
                if cur is None or score > cur["_score"] or \
                        (score == cur["_score"] and tbr > cur["_tbr"]):
                    v_seen[h] = {"_score": score, "_tbr": tbr,
                                 "format_id": f.get("format_id"),
                                 "ext": f.get("ext"),
                                 "fps": f.get("fps")}
        self.video_qualities = []
        for h in sorted(v_seen.keys()):
            entry = v_seen[h]
            fps = entry.get("fps")
            label = f"{h}p" + (f"{int(fps)}" if fps and fps > 30 else "")
            self.video_qualities.append({"label": label, "height": h,
                                         "format_id": entry["format_id"]})

        # --- Audio qualities ---
        a_list = []
        for f in formats:
            if (f.get("acodec") and f.get("acodec") != "none"
                    and (not f.get("vcodec") or f.get("vcodec") == "none")):
                abr = f.get("abr") or 0
                a_list.append({"abr": abr, "ext": f.get("ext"),
                               "format_id": f.get("format_id")})
        # dedupe by rounded abr
        a_seen: dict[int, dict] = {}
        for a in a_list:
            key = int(round(a["abr"] / 16) * 16) if a["abr"] else 0
            if key not in a_seen or a["abr"] > a_seen[key]["abr"]:
                a_seen[key] = a
        self.audio_qualities = []
        for k in sorted(a_seen.keys()):
            a = a_seen[k]
            label = f"{int(a['abr'])} kbps" if a["abr"] else "default"
            self.audio_qualities.append({"label": label, "abr": a["abr"],
                                         "format_id": a["format_id"], "ext": a["ext"]})
        if not self.audio_qualities:
            # fallback - bestaudio
            self.audio_qualities = [{"label": "best", "abr": 0,
                                     "format_id": None, "ext": "m4a"}]

        # reset UI
        self.progress.setValue(0)
        self.status_lbl.setText("Idle.")
        self.retry_btn.hide()
        self.another_btn.hide()
        self.format_combo.setCurrentIndex(0)
        self._refresh_quality_widget()

    def _refresh_quality_widget(self):
        is_audio = self.format_combo.currentIndex() == 1
        items = self.audio_qualities if is_audio else self.video_qualities
        if not items:
            self.quality_slider.setMaximum(0)
            self.quality_value_lbl.setText("-")
            return
        self.quality_slider.blockSignals(True)
        self.quality_slider.setMinimum(0)
        self.quality_slider.setMaximum(len(items) - 1)
        self.quality_slider.setValue(len(items) - 1)  # default = best
        self.quality_slider.blockSignals(False)
        self._update_quality_label(self.quality_slider.value())

    def _update_quality_label(self, idx: int):
        is_audio = self.format_combo.currentIndex() == 1
        items = self.audio_qualities if is_audio else self.video_qualities
        if 0 <= idx < len(items):
            self.quality_value_lbl.setText(items[idx]["label"])

    # ------------------------------------------------------------------ download
    def _build_format_selector(self) -> tuple[str, str]:
        """Returns (yt-dlp format selector string, suggested file extension)."""
        is_audio = self.format_combo.currentIndex() == 1
        idx = self.quality_slider.value()
        if is_audio:
            a = self.audio_qualities[idx]
            if a["format_id"]:
                return a["format_id"], "mp3"
            return "bestaudio/best", "mp3"
        else:
            v = self.video_qualities[idx]
            h = v["height"]
            # video at chosen height + best audio, fallback to best mp4 <= h
            sel = (f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/"
                   f"bestvideo[height<={h}]+bestaudio/"
                   f"best[height<={h}]")
            return sel, "mp4"

    def start_download(self, choose_path: bool):
        if not self.info:
            return
        fmt, ext = self._build_format_selector()
        is_audio = self.format_combo.currentIndex() == 1

        # default save dir = user's Downloads folder
        downloads_dir = str(Path.home() / "Downloads")
        os.makedirs(downloads_dir, exist_ok=True)

        safe_title = re.sub(r'[\\/:*?"<>|]', "_", self.info.get("title", "video"))
        suggested = f"{safe_title}.{ext}"

        if choose_path:
            # explorer dialog - lets user choose folder + filename
            filt = "Audio (*.mp3)" if is_audio else "Video (*.mp4)"
            path, _ = QFileDialog.getSaveFileName(
                self, "Save downloaded file",
                os.path.join(downloads_dir, suggested), filt)
            if not path:
                return
            output_dir = os.path.dirname(path)
            output_filename = os.path.basename(path)
        else:
            output_dir = downloads_dir
            output_filename = suggested

        # Audio post-processing requires ffmpeg
        ydl_extra = None
        if is_audio:
            # We pass a synthetic format selector: bestaudio, then PostProcessor to mp3
            fmt = "bestaudio/best"

        self._last_args = dict(url=self.url, fmt=fmt, output_dir=output_dir,
                               output_filename=output_filename, is_audio=is_audio)

        self._launch_download(**self._last_args)

    def _launch_download(self, url, fmt, output_dir, output_filename, is_audio):
        self.progress.setValue(0)
        self.status_lbl.setText("Starting download...")
        self.retry_btn.hide()
        self.another_btn.hide()
        self.dl_default_btn.setEnabled(False)
        self.dl_choose_btn.setEnabled(False)

        # for audio we need a special thread setup -> build inline
        thread = DownloadThread(url, fmt, output_dir, output_filename, self.ffmpeg_path)
        if is_audio:
            # monkey-patch run to add postprocessor
            orig_run = thread.run
            def audio_run():
                try:
                    outtmpl = os.path.join(output_dir, output_filename or "%(title)s.%(ext)s")
                    # strip extension from outtmpl for postprocessor
                    base, _ = os.path.splitext(outtmpl)
                    outtmpl_noext = base + ".%(ext)s"
                    ydl_opts = {
                        "format": "bestaudio/best",
                        "outtmpl": outtmpl_noext,
                        "noplaylist": True,
                        "progress_hooks": [thread._hook],
                        "quiet": True,
                        "no_warnings": True,
                        "postprocessors": [{
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        }],
                    }
                    if self.ffmpeg_path:
                        ydl_opts["ffmpeg_location"] = self.ffmpeg_path
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        final = ydl.prepare_filename(info)
                        base2, _ = os.path.splitext(final)
                        final_mp3 = base2 + ".mp3"
                        if os.path.isfile(final_mp3):
                            final = final_mp3
                    thread.finished_ok.emit(final)
                except Exception as e:
                    thread.failed.emit(f"Audio download error: {e}")
            thread.run = audio_run

        thread.progress.connect(self._on_progress)
        thread.finished_ok.connect(self._on_finished)
        thread.failed.connect(self._on_failed)
        self.download_thread = thread
        thread.start()

    def _on_progress(self, pct: float, txt: str):
        self.progress.setValue(int(pct))
        self.status_lbl.setText(txt)

    def _on_finished(self, path: str):
        self.dl_default_btn.setEnabled(True)
        self.dl_choose_btn.setEnabled(True)
        self.progress.setValue(100)
        self.status_lbl.setText(f"Done! Saved to: {path}")
        self.retry_btn.hide()
        self.another_btn.show()

    def _on_failed(self, msg: str):
        self.dl_default_btn.setEnabled(True)
        self.dl_choose_btn.setEnabled(True)
        self.status_lbl.setText(f"Download failed: {msg}")
        self.status_lbl.setStyleSheet("color:#ff5566; font-weight:600;")
        self.retry_btn.show()

    def _on_retry(self):
        self.retry_btn.hide()
        self.status_lbl.setStyleSheet("")
        if hasattr(self, "_last_args"):
            self._launch_download(**self._last_args)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YOUTUBE SILENXS - Downloader")
        self.resize(900, 760)
        self.setStyleSheet(APP_STYLE)

        ffmpeg_path = get_ffmpeg_path()

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.url_page = UrlPage()
        self.dl_page = DownloadPage(ffmpeg_path)

        self.stack.addWidget(self.url_page)
        self.stack.addWidget(self.dl_page)

        self.url_page.submitted.connect(self._go_download)
        self.dl_page.back_requested.connect(lambda: self.stack.setCurrentIndex(0))

        if ffmpeg_path is None:
            QTimer.singleShot(300, self._warn_ffmpeg)

    def _warn_ffmpeg(self):
        QMessageBox.warning(
            self, "FFmpeg not found",
            "ffmpeg.exe was not found in the ./ffmpeg/ folder.\n\n"
            "Without FFmpeg, high-quality downloads (1080p+) and MP3 conversion "
            "will fail.\n\nDownload from https://www.gyan.dev/ffmpeg/builds/ "
            "and put ffmpeg.exe in the ffmpeg folder next to the program."
        )

    def _go_download(self, info):
        self.dl_page.load_info(info)
        self.stack.setCurrentIndex(1)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
