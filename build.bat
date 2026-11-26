@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo === Compilar ReelForge en local ===
if not exist bin\ffmpeg.exe (
  echo Falta bin\ffmpeg.exe y bin\ffprobe.exe. Descargalos de https://www.gyan.dev/ffmpeg/builds/ ^(release full^)
  pause & exit /b 1
)
python -m pip install -r requirements.txt pyinstaller || (pause & exit /b 1)
pyinstaller --noconfirm --clean --windowed --name ReelForge --collect-all customtkinter --add-data "bin;bin" main.py || (pause & exit /b 1)
xcopy /E /I /Y overlays dist\ReelForge\overlays >nul
echo.
echo Listo: dist\ReelForge\ReelForge.exe
pause
