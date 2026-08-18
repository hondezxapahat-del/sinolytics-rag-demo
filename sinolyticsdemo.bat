@echo off
:: sinolyticsdemo.bat — double-click this to launch the Sinolytics RAG demo.
:: It just hands off to sinolyticsdemo.ps1 (the real script, next to this
:: file) with PowerShell's script-blocking policy bypassed for this one run
:: only — it does not change any system-wide settings.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sinolyticsdemo.ps1"
pause
