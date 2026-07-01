# Creates a Desktop shortcut that launches FL Connector.
$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root 'Start FL Connector.cmd'
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop 'FL Connector.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lnk)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $root
$shortcut.WindowStyle = 7  # launch minimized (no lingering console)
$shortcut.Description = 'FL Connector desktop'
$shortcut.Save()
Write-Host "Created shortcut: $lnk"
