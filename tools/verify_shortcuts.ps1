$dir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$shell = New-Object -ComObject WScript.Shell
Get-ChildItem $dir -Filter 'HSR*.lnk' | ForEach-Object {
    $s = $shell.CreateShortcut($_.FullName)
    "{0}`n  target : {1}`n  cwd    : {2}`n  exists : {3}" -f $_.Name, $s.TargetPath, $s.WorkingDirectory, (Test-Path $s.TargetPath)
}
