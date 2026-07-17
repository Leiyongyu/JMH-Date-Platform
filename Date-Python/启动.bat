@echo off
chcp 65001 >nul
title 外汇退税数据平台

echo ========================================
echo   外汇退税数据平台
echo ========================================
echo.
echo 首次运行请访问 http://127.0.0.1:5000/setup 初始化数据库
echo.

python app.py
pause
