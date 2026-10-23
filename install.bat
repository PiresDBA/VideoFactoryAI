@echo off
chcp 65001 >nul
title VideoFactoryAI - Instalador Automatico
echo ================================================================
echo   VideoFactoryAI - Instalador de Dependencias e Ambiente
echo ================================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH do sistema.
    echo Por favor, instale o Python 3.10 ou superior e marque:
    echo "Add python.exe to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

echo Iniciando configuracao e verificacao do ambiente...
python "%~dp0setup.py"

echo.
pause
