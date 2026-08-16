@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_ONE_CLICK.ps1" %*
exit /b %errorlevel%
