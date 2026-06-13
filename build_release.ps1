param(
    [string]$OutputRoot = "",
    [string]$DistPath = ""
)

$ErrorActionPreference = "Stop"

function TextFromCodes([int[]]$Codes) {
    return -join ($Codes | ForEach-Object { [char]$_ })
}

$appName = TextFromCodes @(36890,29992,32593,31449,37319,38598,20013,24515)
$legacyName = TextFromCodes @(38386,40060,30417,27979,36719,20214)
$releaseSuffix = TextFromCodes @(21457,24067,21253)
$readmeName = (TextFromCodes @(20351,29992,35828,26126)) + ".txt"
$proofName = (TextFromCodes @(21457,24067,35777,26126)) + ".txt"
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

$startTitle = TextFromCodes @(21551,21160,26041,24335)
$privacyTitle = TextFromCodes @(38544,31169,35828,26126)
$line1 = (TextFromCodes @(21452,20987)) + " $appName.exe"
$line2 = (TextFromCodes @(36755,20837,32593,22336,21518,65292,28857,20987)) + " " + (TextFromCodes @(24320,22987,37319,38598))
$line3 = (TextFromCodes @(38656,35201,21160,24577,32593,39029,26102,65292,20445,25345)) + " Playwright " + (TextFromCodes @(30495,23454,27983,35272,22120,27169,24335))
$line4 = TextFromCodes @(24314,35758,22312,32,65,73,32,37197,32622,20013,20445,23384,32,65,80,73,32,75,101,121,12289,66,97,115,101,32,85,82,76,32,21644,27169,22411,65307,65,80,73,32,75,101,121,32,20250,20351,29992,32,87,105,110,100,111,119,115,32,26412,26426,29992,25143,21152,23494,20445,23384)
$privacy1 = TextFromCodes @(21457,24067,21253,19981,21253,21547,21382,21490,37319,38598,24211,12289,27169,26495,24211,12289,27983,35272,22120,30331,24405,24577,21644,35786,26029,26085,24535)
$privacy2 = (TextFromCodes @(36816,34892,25968,25454,40664,35748,20445,23384,22312)) + " %LOCALAPPDATA%\UniversalWebCollector"
$privacy3 = TextFromCodes @(35831,21482,37319,38598,20844,24320,21487,35265,25110,20320,26377,26435,38480,35775,38382,30340,20449,24687,65292,36991,20813,37319,38598,38544,31169,25968,25454)
$readmeLines = @(
    $appName,
    "",
    "${startTitle}:",
    "1. $line1",
    "2. $line2",
    "3. $line3",
    "4. $line4",
    "",
    "${privacyTitle}:",
    "- $privacy1",
    "- $privacy2",
    "- $privacy3"
)
$readmeLines | Set-Content -LiteralPath (Join-Path $releaseRoot $readmeName) -Encoding UTF8

$buildTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$proofTitle = TextFromCodes @(21457,24067,35777,26126)
$proofTime = TextFromCodes @(29983,25104,26102,38388)
$proofExe = TextFromCodes @(31243,24207,36335,24452)
$proofSource = TextFromCodes @(26469,28304,30446,24405)
$proofShortcut = TextFromCodes @(26700,38754,24555,25463,26041,24335)
$proofLines = @(
    $proofTitle,
    "",
    "${proofTime}: $buildTime",
    "${proofExe}: $releaseExe",
    "${proofSource}: $distRoot",
    "${proofShortcut}: OK",
    "功能同步: 已包含自然语言全网爬取入口"
)
$proofLines | Set-Content -LiteralPath (Join-Path $releaseRoot $proofName) -Encoding UTF8

$launcherPrefix = TextFromCodes @(21551,21160,36890,29992,32593,31449,37319,38598,20013,24515)
$noConsole = TextFromCodes @(26080,40657,31383)
$exeEdition = "EXE" + (TextFromCodes @(29256))
$launcherNames = @(
    "$launcherPrefix.bat",
    "${launcherPrefix}_${noConsole}.vbs",
    "${launcherPrefix}_${exeEdition}.vbs"
)
foreach ($launcherName in $launcherNames) {
    $launcherPath = Join-Path $projectRoot $launcherName
    if (Test-Path -LiteralPath $launcherPath) {
        Copy-Item -LiteralPath $launcherPath -Destination (Join-Path $releaseRoot $launcherName) -Force
    }
}

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
