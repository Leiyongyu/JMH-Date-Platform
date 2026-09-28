@echo off
title 报关单系统 - 本机调试
echo 报关单生成系统本机调试服务启动中...
echo 地址: http://127.0.0.1:5000
echo 正式环境请启动 Date-Project backend.main，无需单独运行本文件。
echo.
python "%~dp0server.py"
pause
