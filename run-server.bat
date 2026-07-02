@echo off
cd /d "%~dp0"
py manage.py runserver %*
