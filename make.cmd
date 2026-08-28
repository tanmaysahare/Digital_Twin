@echo off
rem Windows shim for the Makefile. Same tasks, same steps, no make required.
python "%~dp0tools\tasks.py" %*
