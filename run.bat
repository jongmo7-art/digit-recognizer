@echo off
REM Launch the handwritten digit recognizer.
REM Double-click this file to run the app.

setlocal
cd /d "%~dp0"

REM Path to the installed Python interpreter.
set "PY=C:\Users\jongm\AppData\Local\Programs\Python\Python312\python.exe"

if not exist "%PY%" (
    echo [ERROR] Python not found at:
    echo   %PY%
    echo Install Python 3.12 from https://www.python.org/downloads/ and try again.
    pause
    exit /b 1
)

REM Train the model on first run (creates mnist_mlp.joblib).
if not exist "mnist_mlp.joblib" (
    echo Model file not found. Training a new model ^(about 30 seconds^)...
    "%PY%" train_model.py
    if errorlevel 1 (
        echo [ERROR] Training failed.
        pause
        exit /b 1
    )
)

echo Launching digit recognizer...
"%PY%" digit_app.py

endlocal
