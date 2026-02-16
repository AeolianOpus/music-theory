@echo off
REM Build Music Theory Scale Finder as a Windows executable.
REM Run this from the project root: build.bat
REM
REM Prerequisites:
REM   pip install pyinstaller
REM   A SoundFont file in soundfonts/

echo Building Music Theory Scale Finder...

pyinstaller ^
    --name "MusicTheoryScaleFinder" ^
    --windowed ^
    --onedir ^
    --icon=NONE ^
    --add-data "data;data" ^
    --add-data "soundfonts;soundfonts" ^
    --add-data "saves;saves" ^
    --hidden-import=PySide6.QtSvg ^
    --hidden-import=PySide6.QtSvgWidgets ^
    app.py

echo.
echo Build complete! Output in dist/MusicTheoryScaleFinder/
echo Run dist/MusicTheoryScaleFinder/MusicTheoryScaleFinder.exe to launch.
pause
