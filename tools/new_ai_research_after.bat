@echo off
chcp 65001 >nul
if "%~2"=="" (
 echo Usage: new_ai_research_after.bat saved.keiba research.sqlite
 exit /b 1
)
python "%~dp0new_ai_research.py" --keiba "%~1" --stats "%~2" --out "%~dp0..\research\predictions.sqlite" --export-dir "%~dp0..\research\portable" --bundle-dir "%~dp0..\research\bundles"
exit /b %errorlevel%
