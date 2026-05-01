@echo off
REM ============================================================
REM  DownTube - Build script (Windows)
REM ============================================================

echo [1/3] Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo [2/3] Checking FFmpeg...
if not exist "ffmpeg\ffmpeg.exe" (
    echo  ERROR: ffmpeg\ffmpeg.exe not found!
    echo  Download from:
    echo    https://www.gyan.dev/ffmpeg/builds/
    pause
    exit /b 1
)

echo [3/3] Building EXE with icon...
pyinstaller --onefile --noconsole ^
    --name "DownTube" ^
    --icon "DownTub.ico" ^
    --add-binary "ffmpeg\ffmpeg.exe;ffmpeg" ^
    --hidden-import PyQt5 ^
    --hidden-import PyQt5.QtCore ^
    --hidden-import PyQt5.QtGui ^
    --hidden-import PyQt5.QtWidgets ^
    main.py

echo.
echo ============================================================
echo  DONE!  Your EXE is at:  dist\DownTube.exe
echo ============================================================
pause
