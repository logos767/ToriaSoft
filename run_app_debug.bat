@echo off
cd /d "%~dp0"
REM -----------------------------------------------------------------
REM  Lanzador de Depuracion de ToriaSoft
REM -----------------------------------------------------------------
REM  Este script hace lo siguiente:
REM  1. Activa el entorno virtual de Python.
REM  2. Inicia el servidor de la aplicacion (usando run.py para Socket.IO)
REM     en una ventana de consola VISIBLE para poder ver los errores.
REM
REM  Usa este script cuando la aplicacion no inicie y necesites
REM  ver el traceback o los mensajes de error.
REM -----------------------------------------------------------------

title Lanzador de Depuracion de ToriaSoft

REM --- Verificar prerrequisitos ---
echo Verificando entorno...
IF NOT EXIST venv\Scripts\activate (
    echo.
    echo ERROR: No se encontro el entorno virtual 'venv'.
    echo Por favor, crealo ejecutando: python -m venv venv
    echo.
    pause
    exit /b
)
IF NOT EXIST requirements.txt (
    echo.
    echo ERROR: No se encontro el archivo 'requirements.txt'.
    echo Este archivo es necesario para instalar las dependencias.
    echo.
    pause
    exit /b
)

REM --- Instalar/Actualizar dependencias ---
echo Asegurando que las dependencias esten instaladas...
venv\Scripts\python.exe -m pip install -r requirements.txt
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Fallo la instalacion de dependencias.
    echo.
    pause
    exit /b
)

REM --- Iniciar el servidor de la aplicacion en modo visible ---
echo Iniciando el servidor de ToriaSoft en modo de depuracion...
echo La ventana de la consola permanecera abierta. Cierrala para detener el servidor.
venv\Scripts\python.exe run.py