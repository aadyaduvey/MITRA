@echo off
rem One-command start for MITRA on Windows. Options: -Reseed  -Smoke  -NoBot  -NoBrowser  -ApiPort N  -WebPort N
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
