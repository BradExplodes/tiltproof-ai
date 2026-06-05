@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env
echo Running from source (latest code, TTS enabled via .env)...
..\.venv\Scripts\python.exe -m aicoach --game osu
pause
