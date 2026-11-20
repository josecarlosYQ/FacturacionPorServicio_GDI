@echo off
REM Genera dist\FacturacionPacifico.exe (ejecutar en Windows, con Python 3.10+ instalado)
setlocal
cd /d "%~dp0"
python -m pip install -r requirements.txt || goto :error
REM --add-data empaqueta el script SQL (lo lee core/setup_db.py con ruta_recurso)
python -m PyInstaller --noconfirm --onefile --windowed --name FacturacionPacifico --collect-submodules mysql.connector --add-data "sql;sql" main.py || goto :error
echo.
echo Listo: dist\FacturacionPacifico.exe
echo En el primer arranque se mostrara la pantalla de configuracion y se creara config.json junto al .exe.
pause
exit /b 0
:error
echo.
echo Fallo la compilacion.
pause
exit /b 1
