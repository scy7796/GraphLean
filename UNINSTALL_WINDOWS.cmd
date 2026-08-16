@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0UNINSTALL_ONE_CLICK.ps1" %*
exit /b %errorlevel%

