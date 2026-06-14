param(
    [string]$ReleaseRoot = "",
    [switch]$UseProjectLauncher,
    [switch]$UpdateProjectShortcut
)

$ErrorActionPreference = "Stop"

function TextFromCodes([int[]]$Codes) {
    return -join ($Codes | ForEach-Object { [char]$_ })
}

$appName = TextFromCodes @(36890,29992,32593,31449,37319,38598,20013,24515)
$desktopLinkName = "$appName.lnk"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutTargets = @(
    (Join-Path $desktopPath $desktopLinkName)
)
if ($UpdateProjectShortcut) {
    $shortcutTargets += (Join-Path $projectRoot $desktopLinkName)
}

if ($UseProjectLauncher) {
    $targetPath = Join-Path $projectRoot "启动通用网站采集中心_无黑窗.vbs"
    if (-not (Test-Path -LiteralPath $targetPath)) {
        throw "未找到源码启动器：$targetPath"
    }
    $workingDirectory = $projectRoot
    $iconLocation = "$env:SystemRoot\System32\SHELL32.dll,220"
} else {
    if (-not $ReleaseRoot) {
        $releaseRootCandidate = Join-Path "D:\" $appName
        if (Test-Path -LiteralPath $releaseRootCandidate) {
            $ReleaseRoot = $releaseRootCandidate
        }
    }
    if (-not $ReleaseRoot) {
        throw "未提供 ReleaseRoot，且默认发布目录不存在。可用 -UseProjectLauncher 直接指向当前最新源码版。"
    }
    $targetPath = Join-Path $ReleaseRoot ($appName + ".exe")
    if (-not (Test-Path -LiteralPath $targetPath)) {
        throw "未找到 EXE：$targetPath"
    }
    $workingDirectory = $ReleaseRoot
    $iconLocation = "$targetPath,0"
}

$shell = New-Object -ComObject WScript.Shell
foreach ($shortcutPath in $shortcutTargets) {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $targetPath
    $shortcut.WorkingDirectory = $workingDirectory
    $shortcut.Arguments = ""
    $shortcut.IconLocation = $iconLocation
    $shortcut.Description = "通用网站采集中心（最新版本）"
    $shortcut.Save()
    Write-Host "Shortcut synced: $shortcutPath"
}
Write-Host "Target: $targetPath"
