@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0.."

echo [1/3] 安装打包依赖...
python -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1

echo [2/3] 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] 生成 exe...
python -m PyInstaller cascon-sync.spec --noconfirm
if errorlevel 1 exit /b 1

echo.
echo 打包完成: dist\cascon-sync.exe
echo.
echo 使用示例:
echo   dist\cascon-sync.exe -d database.xlsx -s "D:\Cascon" -o "Z:\database" --dry-run

endlocal
