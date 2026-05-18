# AI 学术写作助手 - Windows 构建脚本
# 用于在 Windows 上构建可执行文件

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-Step {
    param(
        [string]$Message
    )

    Write-Host ""
    Write-Host $Message -ForegroundColor Yellow
}

function Invoke-CheckedCommand {
    param(
        [string]$Description,
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description 失败，退出码：$LASTEXITCODE"
    }
}

function Reset-Venv {
    param(
        [string]$VenvPath
    )

    if (-not (Test-Path $VenvPath)) {
        return
    }

    $resolved = (Resolve-Path $VenvPath).Path
    if (-not $resolved.StartsWith($ScriptDir, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝删除非项目目录的虚拟环境：$resolved"
    }

    Write-Host "检测到虚拟环境损坏，正在重建：$resolved" -ForegroundColor DarkYellow
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

function Test-VenvPython {
    param(
        [string]$VenvPython
    )

    if (-not (Test-Path $VenvPython)) {
        return $false
    }

    & $VenvPython -c "import sys; print(sys.executable)" *> $null
    return ($LASTEXITCODE -eq 0)
}

function Ensure-VenvReady {
    param(
        [string]$BasePython,
        [string]$VenvPath
    )

    $venvPython = Join-Path $VenvPath 'Scripts\python.exe'

    if (-not (Test-Path $VenvPath)) {
        Write-Host "未检测到虚拟环境，正在创建..." -ForegroundColor DarkYellow
        Invoke-CheckedCommand -Description "创建虚拟环境" -FilePath $BasePython -Arguments @('-m', 'venv', $VenvPath)
    }

    if (-not (Test-VenvPython -VenvPython $venvPython)) {
        Reset-Venv -VenvPath $VenvPath
        Invoke-CheckedCommand -Description "重建虚拟环境" -FilePath $BasePython -Arguments @('-m', 'venv', $VenvPath)
    }

    if (-not (Test-VenvPython -VenvPython $venvPython)) {
        throw "虚拟环境创建失败，未找到可用的 python.exe"
    }

    & $venvPython -m pip --version *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "检测到虚拟环境缺少 pip，正在尝试修复..." -ForegroundColor DarkYellow
        & $venvPython -m ensurepip --upgrade

        if ($LASTEXITCODE -ne 0) {
            Reset-Venv -VenvPath $VenvPath
            Invoke-CheckedCommand -Description "重新创建虚拟环境" -FilePath $BasePython -Arguments @('-m', 'venv', $VenvPath)
            Invoke-CheckedCommand -Description "初始化 pip" -FilePath $venvPython -Arguments @('-m', 'ensurepip', '--upgrade')
        }
    }

    [void](Invoke-CheckedCommand -Description "校验 pip" -FilePath $venvPython -Arguments @('-m', 'pip', '--version'))
    return $venvPython
}

function Remove-ExistingExeIfPossible {
    param(
        [string]$ExePath
    )

    if (-not (Test-Path $ExePath)) {
        return
    }

    try {
        Remove-Item -LiteralPath $ExePath -Force
        return
    } catch {
        $running = Get-Process -ErrorAction SilentlyContinue | Where-Object {
            $_.Path -eq $ExePath -or $_.ProcessName -eq 'AI学术写作助手'
        } | Select-Object Id, ProcessName, Path

        if ($running) {
            $processSummary = ($running | ForEach-Object { "PID=$($_.Id) Path=$($_.Path)" }) -join '; '
            throw "旧版 exe 正在运行并占用输出文件，请先关闭 AI学术写作助手 后再重试。占用进程：$processSummary"
        }

        throw "无法删除旧版 exe：$ExePath。请确认该文件未被占用后重试。"
    }
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "AI 学术写作助手 - Windows 构建脚本" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$PreferredPython = 'D:\python3.x\python.exe'
$PythonExe = $null

if (Test-Path $PreferredPython) {
    $PythonExe = $PreferredPython
} else {
    try {
        $PythonExe = (Get-Command python -ErrorAction Stop).Source
    } catch {
        $PythonExe = $null
    }
}

Write-Step "1. 检查 Python 环境..."
if (-not $PythonExe) {
    throw "未找到 Python，请先安装 Python 3.9+"
}
$pythonVersion = & $PythonExe --version 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Python 不可用：$PythonExe"
}
Write-Host $pythonVersion -ForegroundColor Green
Write-Host "使用 Python: $PythonExe" -ForegroundColor DarkGray

Write-Step "2. 检查 Node.js 环境..."
$NodeExe = (Get-Command node -ErrorAction Stop).Source
$NpmExe = (Get-Command npm -ErrorAction Stop).Source
$nodeVersion = & $NodeExe --version 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Node.js 不可用：$NodeExe"
}
Write-Host $nodeVersion -ForegroundColor Green
Write-Host "使用 Node.js: $NodeExe" -ForegroundColor DarkGray

Write-Step "3. 安装后端依赖..."
$VenvPath = Join-Path $ScriptDir 'venv'
$VenvPython = Ensure-VenvReady -BasePython $PythonExe -VenvPath $VenvPath
Write-Host "使用虚拟环境 Python: $VenvPython" -ForegroundColor DarkGray

Invoke-CheckedCommand -Description "升级 pip/setuptools/wheel" -FilePath $VenvPython -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip', 'setuptools', 'wheel')
Invoke-CheckedCommand -Description "安装后端依赖" -FilePath $VenvPython -Arguments @('-m', 'pip', 'install', '-r', 'requirements.txt')

& $VenvPython -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "检测到虚拟环境缺少 PyInstaller，正在补充安装..." -ForegroundColor DarkYellow
    Invoke-CheckedCommand -Description "安装 PyInstaller" -FilePath $VenvPython -Arguments @('-m', 'pip', 'install', 'pyinstaller==6.3.0')
}

Invoke-CheckedCommand -Description "校验 PyInstaller" -FilePath $VenvPython -Arguments @('-m', 'PyInstaller', '--version')

Write-Step "4. 构建前端..."
Push-Location (Join-Path $ScriptDir 'frontend')
try {
    Invoke-CheckedCommand -Description "安装前端依赖" -FilePath $NpmExe -Arguments @('install')
    $FrontendDist = Join-Path (Get-Location) 'dist'
    if (Test-Path $FrontendDist) {
        Remove-Item -LiteralPath $FrontendDist -Recurse -Force
    }
    Invoke-CheckedCommand -Description "构建前端" -FilePath $NpmExe -Arguments @('run', 'build')
} finally {
    Pop-Location
}

Write-Step "5. 复制前端构建产物..."
$StaticDir = Join-Path $ScriptDir 'static'
if (Test-Path $StaticDir) {
    Remove-Item -LiteralPath $StaticDir -Recurse -Force
}
Copy-Item -Recurse -Force (Join-Path $ScriptDir 'frontend\dist') $StaticDir

Write-Step "6. 使用 PyInstaller 打包..."
$ExePath = Join-Path $ScriptDir 'dist\AI学术写作助手.exe'
Remove-ExistingExeIfPossible -ExePath $ExePath
Invoke-CheckedCommand -Description "PyInstaller 打包" -FilePath $VenvPython -Arguments @('-m', 'PyInstaller', 'app.spec', '--clean')

if (-not (Test-Path $ExePath)) {
    throw "打包完成后未找到输出文件：$ExePath"
}

$ExeInfo = Get-Item $ExePath

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "构建完成!" -ForegroundColor Green
Write-Host "可执行文件位置: $($ExeInfo.FullName)" -ForegroundColor Green
Write-Host "文件大小: $([Math]::Round($ExeInfo.Length / 1MB, 2)) MB" -ForegroundColor Green
Write-Host "更新时间: $($ExeInfo.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "运行方式:" -ForegroundColor Yellow
Write-Host "1. 将 dist\AI学术写作助手.exe 复制到任意目录"
Write-Host "2. 首次运行会自动创建 .env 配置文件"
Write-Host "3. 编辑 .env 文件，填入 API Key 等配置"
Write-Host "4. 再次运行程序，将自动打开浏览器"
Write-Host ""
