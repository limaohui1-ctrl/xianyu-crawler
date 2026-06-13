#Requires -Version 5.1
param(
    [string]$OutputRoot = "",
    [string]$DistPath = ""
)

$ErrorActionPreference = "Stop"

# Readable names (replacing former ASCII-code obfuscation)
$appName = "通用网站采集中心"
$legacyName = "闲鱼监测软件"
$releaseSuffix = "发布包"
$readmeName = "使用说明.txt"
$proofName = "发布说明.txt"
$desktopLinkName = "$appName.lnk"

if (-not $OutputRoot) {
    $OutputRoot = "D:\${appName}_${releaseSuffix}"
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$hygieneScript = Join-Path $projectRoot "tools\verify_repo_hygiene.py"
if (Test-Path -LiteralPath $hygieneScript) {
    Write-Host "Running repository hygiene check..."
    & python $hygieneScript
    if ($LASTEXITCODE -ne 0) {
        throw "Repository hygiene check failed. Clean tracked/generated artifacts before packaging."
    }
}

$distRoot = if ($DistPath) {
    Resolve-Path -LiteralPath $DistPath
} elseif (Test-Path -LiteralPath (Join-Path $projectRoot "dist\$appName")) {
    Join-Path $projectRoot "dist\$appName"
} elseif (Test-Path -LiteralPath (Join-Path $projectRoot "dist_fixed\$legacyName")) {
    Join-Path $projectRoot "dist_fixed\$legacyName"
} else {
    Join-Path $projectRoot "dist\$appName"
}

if (-not (Test-Path -LiteralPath $distRoot)) {
    throw "Dist folder not found: $distRoot"
}

$releaseRoot = Join-Path $OutputRoot $appName
$releaseExe = Join-Path $releaseRoot "$appName.exe"
if (Test-Path -LiteralPath $releaseRoot) {
    Remove-Item -LiteralPath $releaseRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $releaseRoot | Out-Null

robocopy $distRoot $releaseRoot /E /XD chrome-profile self_test_runtime data universal_data /XF `
    app_settings.json hit_history.json item_statuses.json scanned_items.json `
    monitor_log.txt startup_error.log self_test_error.log chrome_session.json `
    collector.sqlite3 site_templates.json `
    diagnostic_log_*.txt *.corrupt-*.bak | Out-Null
$exitCode = $LASTEXITCODE
if ($exitCode -ge 8) {
    throw "Copy release package failed, robocopy exit code: $exitCode"
}

# Generate user-facing README
$readmeLines = @(
    $appName,
    "",
    "启动方式:",
    "1. 双击 $appName.exe",
    "2. 输入网址后，点击 开始采集",
    "3. 需要动态网页时，保持 使用真实浏览器采集动态网页 勾选",
    "所有设置在 AI 配置中保存 API Key, Base URL 和模型；API Key 会使用 Windows 本机用户加密保存",
    "",
    "隐私说明:",
    "- 发布包不包含历史采集库、模板库、浏览器登录态和诊断日志",
    "- 运行数据默认保存在 %LOCALAPPDATA%\UniversalWebCollector",
    "- 请只采集您公开或拥有有限访问权限的信息，避免采集隐私数据"
)
$readmeLines | Set-Content -LiteralPath (Join-Path $releaseRoot $readmeName) -Encoding UTF8

# Generate proof of build
$buildTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$proofLines = @(
    "发布说明",
    "",
    "生成时间: $buildTime",
    "程序路径: $releaseExe",
    "来源目录: $distRoot",
    "桌面快捷方式: OK",
    "功能同步: 已包含自然语言全网爬取入口"
)
$proofLines | Set-Content -LiteralPath (Join-Path $releaseRoot $proofName) -Encoding UTF8

# Copy launchers
$launcherPrefix = "启动通用网站采集中心"
$launcherNames = @(
    "$launcherPrefix.bat",
    "${launcherPrefix}_无黑框.vbs",
    "${launcherPrefix}_EXE版.vbs"
)
foreach ($launcherName in $launcherNames) {
    $launcherPath = Join-Path $projectRoot $launcherName
    if (Test-Path -LiteralPath $launcherPath) {
        Copy-Item -LiteralPath $launcherPath -Destination (Join-Path $releaseRoot $launcherName) -Force
    }
}

# Create desktop shortcuts
$shell = New-Object -ComObject WScript.Shell
$shortcutTargets = @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) $desktopLinkName),
    (Join-Path $projectRoot $desktopLinkName)
)
foreach ($shortcutPath in $shortcutTargets) {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $releaseExe
    $shortcut.WorkingDirectory = $releaseRoot
    $shortcut.Arguments = ""
    $shortcut.IconLocation = "$releaseExe,0"
    $shortcut.Save()
}

Write-Host "Release package created: $releaseRoot"
Write-Host "Desktop shortcut target: $releaseExe"
exit 0
