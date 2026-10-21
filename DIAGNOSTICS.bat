@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\petshop.ps1" -Action Diagnose
set "petshopExit=%ERRORLEVEL%"
pause
endlocal & exit /b %petshopExit%
