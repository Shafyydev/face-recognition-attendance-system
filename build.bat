@echo off
echo ============================================================
echo   Building Attendance System .exe
echo ============================================================
echo.
echo   DATA-SAFE BUILD
echo   Production database and known faces are NOT copied.
echo.

:: Check if PyInstaller is installed
where pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] PyInstaller not found. Installing...
    pip install pyinstaller
    echo.
)

:: Clean previous build output
if exist "dist\AttendanceSystem" (
    echo Cleaning previous build...
    rmdir /s /q "dist\AttendanceSystem"
)

echo Building...
echo.

pyinstaller AttendanceSystem.spec --noconfirm

if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo   BUILD SUCCESSFUL
    echo ============================================================
    echo.
    echo   Application build created at:
    echo   dist\AttendanceSystem\
    echo.
    echo   IMPORTANT:
    echo   attendance.db was NOT copied.
    echo   known_faces was NOT copied.
    echo   Production data remains protected.
    echo.
    echo   Output:
    echo   dist\AttendanceSystem\AttendanceSystem.exe
    echo.
) else (
    echo.
    echo ============================================================
    echo   BUILD FAILED
    echo ============================================================
    echo.
    echo   Check the PyInstaller output above.
    echo.
)

pause
