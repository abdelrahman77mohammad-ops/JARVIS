@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo        تشغيل جارفيس...
echo ============================================
echo تثبيت المكتبات لأول مرة (ممكن ياخد دقيقة)...
py -m pip install --quiet --disable-pip-version-check flask
py -m pip install --quiet --disable-pip-version-check pywhatkit 2>nul
echo.
echo جاري التشغيل... هيفتح المتصفح لوحده.
py jarvis.py
pause
