@echo off

uvx --with pyinstaller ^
    --with numpy ^
    --with opencv-python-headless ^
    --with keyboard ^
    pyinstaller --clean --console --noconfirm --onedir --collect-all cv2 main.py

if %errorlevel% neq 0 (
    echo PyInstaller build failed
    exit /b %errorlevel%
)

if exist "dist\main\assets" (
    rmdir /s /q "dist\main\assets"
)

echo Moving assets folder to dist root...
xcopy "assets" "dist\main\assets" /E /I /Y
if %errorlevel% neq 0 (
    echo Failed to copy assets folder
    exit /b %errorlevel%
)