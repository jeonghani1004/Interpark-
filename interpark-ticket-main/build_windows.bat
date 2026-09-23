@echo off
REM ============================================================
REM  在 Windows 上把抢票工具打包成单个 exe。
REM  用法：把整个项目文件夹拷到 Windows，双击本文件即可。
REM  前提：Windows 已装 Python 3（安装时勾选 Add to PATH）。
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

echo [0/3] 检测 Python 命令...
set PY=py
%PY% --version >nul 2>&1
if errorlevel 1 set PY=python
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo 找不到 Python，请确认已安装并勾选 Add to PATH。
    pause
    exit /b 1
)
echo 使用 %PY%

echo [1/3] 安装依赖 (selenium requests pyinstaller)...
%PY% -m pip install --upgrade pip
%PY% -m pip install selenium requests pyinstaller
if errorlevel 1 (
    echo 依赖安装失败，请确认能联网。
    pause
    exit /b 1
)

echo [2/3] 打包中...
REM --add-data 用分号分隔（Windows 专用），把 shows 目录一起打进 exe
%PY% -m PyInstaller --noconfirm --onefile --windowed ^
    --name InterparkTicket ^
    --add-data "shows;shows" ^
    gui.py
if errorlevel 1 (
    echo 打包失败，请把上面的报错发给我。
    pause
    exit /b 1
)

echo [3/3] 拷贝配置到 exe 同目录...
REM settings.json（含已填好的百度 Key）要和 exe 放一起，运行时才读得到
if exist settings.json copy /y settings.json dist\settings.json >nul
REM 顺带把 shows 目录也放一份到 exe 旁，方便以后加新场次
if not exist dist\shows mkdir dist\shows
copy /y shows\*.py dist\shows\ >nul

echo 完成！
echo exe 在 dist\InterparkTicket.exe（已自带百度 Key）
echo 双击它就能打开填信息的窗口。
pause
