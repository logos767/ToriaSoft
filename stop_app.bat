@echo off
title Detener ToriaSoft

echo.
echo Intentando detener el servidor de ToriaSoft...
echo.

REM Busca y termina el proceso de Python que esta ejecutando el archivo "run.py".
REM El comando "wmic" encuentra el proceso y lo termina.
wmic process where "name='python.exe' and commandline like '%%run.py%%'" call terminate > nul

REM Una pequena pausa para asegurar que el proceso se ha cerrado.
timeout /t 2 /nobreak > nul

echo.
echo El servidor deberia haberse detenido.
echo Si la aplicacion sigue respondiendo en el navegador, es posible que deba cerrar el proceso manualmente desde el Administrador de Tareas.
echo.
pause