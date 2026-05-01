@echo off
REM ============================================================
REM  YOUTUBE SILENXS - Build script (Windows)
REM  Produces a single EXE in .\dist\YouTubeSilenxs.exe
REM ============================================================

echo [1/3] Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo [2/3] Checking FFmpeg...
if not exist "ffmpeg\ffmpeg.exe" (
    echo  ERROR: ffmpeg\ffmpeg.exe not found!
    echo  Download "release essentials" build from:
    echo    https://www.gyan.dev/ffmpeg/builds/
    echo  Extract ffmpeg.exe into the .\ffmpeg\ folder, then re-run this script.
    pause
    exit /b 1
)

echo [3/3] Building one-file EXE with PyInstaller...
pyinstaller --onefile --noconsole ^
    --name "YouTubeSilenxs" ^
    --add-binary "ffmpeg\ffmpeg.exe;ffmpeg" ^
    --hidden-import PyQt5 ^
    --hidden-import PyQt5.QtCore ^
    --hidden-import PyQt5.QtGui ^
    --hidden-import PyQt5.QtWidgets ^
    main.py

echo.
echo ============================================================
echo  DONE!  Your EXE is at:  dist\YouTubeSilenxs.exe
echo ============================================================
pause
