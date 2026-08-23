
@echo off
cd /d "%~dp0"
call venv\Scripts\activate
python manage.py shell < fix_portal_passwords.py
