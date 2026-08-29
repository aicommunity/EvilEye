@echo off
rem EvilEye docker host-cli
setlocal
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%evileye-launch.ps1" %*
exit /b %ERRORLEVEL%
