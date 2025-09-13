@echo off
cd /d "%~dp0"
REM -----------------------------------------------------------------
REM  Lanzador de la Aplicacion ToriaSoft
REM -----------------------------------------------------------------
REM  Este script hace lo siguiente:
REM  1. Activa el entorno virtual de Python.
REM  2. Inicia el servidor de la aplicacion (usando run.py para Socket.IO)
REM     en una ventana de consola MINIMIZADA.
REM  3. Abre una pantalla de carga en el navegador que redirige a la
REM     aplicacion.
REM
REM  Coloca este archivo en el directorio raiz del proyecto
REM  (ej. E:\Documentos\GitHub\ToriaSoft\ToriaSoft\)
REM
REM  Prerrequisitos:
REM  1. Python debe estar instalado y en el PATH de tu sistema.
REM  2. Un entorno virtual llamado 'venv' debe existir en este
REM     directorio. Si no existe, ejecuta: python -m venv venv
REM  3. Las dependencias deben estar instaladas. Ejecuta:
REM     venv\Scripts\activate
REM     pip install -r requirements.txt
REM -----------------------------------------------------------------

title Lanzador de ToriaSoft

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
    echo Por favor, crea este archivo o asegurate de que este en el directorio correcto.
    echo.
    pause
    exit /b
)

REM --- Instalar/Actualizar dependencias ---
echo Asegurando que las dependencias esten instaladas (esto puede tardar un momento)...
venv\Scripts\python.exe -m pip install -r requirements.txt
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Fallo la instalacion de dependencias desde requirements.txt.
    echo Por favor, revisa tu conexion a internet y el archivo requirements.txt.
    echo.
    pause
    exit /b
)

REM --- Iniciar el servidor de la aplicacion ---
echo Iniciando el servidor de ToriaSoft en segundo plano...
echo El servidor se ejecutara de forma oculta, sin una ventana de consola visible.
echo.
echo IMPORTANTE: Para detener la aplicacion, deberas ejecutar el archivo 'stop_app.bat'.

REM Se crea y ejecuta un script VBS temporal para lanzar el servidor de Python
REM de forma oculta. Esto evita que la ventana de la consola aparezca.
echo Set WshShell = CreateObject^("WScript.Shell"^) > silent_runner.vbs
echo WshShell.Run "venv\Scripts\python.exe run.py", 0, False >> silent_runner.vbs
cscript //nologo silent_runner.vbs
del silent_runner.vbs

REM --- Abrir la pantalla de carga en el navegador ---
echo Abriendo la aplicacion en el navegador...
echo La pagina de carga inteligente verificara cuando el servidor este listo.
start loader.html

REM --- Finalizar este script ---
echo.
echo El script de inicio ha finalizado. El servidor se esta ejecutando en segundo plano.
exit /b