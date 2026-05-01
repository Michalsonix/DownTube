# 🎬 DownTube

DownTube is a simple desktop YouTube downloader with GUI built in Python.

## 🚀 Features

- Download videos from YouTube using URL
- Supports **MP4 (video)** and **MP3 (audio)**
- Select video quality from **144p up to 4K**
- Simple and clean GUI interface
- Built with Python and yt-dlp

---

## 🛠 Requirements

- Python 3.10+
- yt-dlp

Install dependencies:
```bash
pip install -r requirements.txt



⚙️ Setup (IMPORTANT)

If you want to run or build the program yourself, you MUST download ffmpeg.exe.

Download it from:
👉 https://www.gyan.dev/ffmpeg/builds/

Then place it in the project like this:


DownTub/
│   build.bat
│   main.py
│   requirements.txt
│
└───ffmpeg
        ffmpeg.exe


▶️ Run

python main.py



📦 Build EXE

Using PyInstaller:

pyinstaller --onefile --windowed main.py

