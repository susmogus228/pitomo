@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\petshop.ps1" -Action Start
set "petshopExit=%ERRORLEVEL%"
if not "%petshopExit%"=="0" pause
endlocal & exit /b %petshopExit%
