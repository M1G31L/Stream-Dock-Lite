# Desinstalador de Stream Dock Lite
Add-Type -AssemblyName System.Windows.Forms
$Dest = Join-Path $env:LOCALAPPDATA 'Programs\StreamDockLite'

$r = [System.Windows.Forms.MessageBox]::Show('¿Desinstalar Stream Dock Lite?', 'Stream Dock Lite', 'YesNo', 'Question')
if ($r -ne 'Yes') { exit 0 }

Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*StreamDockLite*app.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) 'Stream Dock Lite') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Stream Dock Lite.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Startup')) 'StreamDockLite.cmd') -Force -ErrorAction SilentlyContinue
Remove-Item 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\StreamDockLite' -Recurse -Force -ErrorAction SilentlyContinue

$r = [System.Windows.Forms.MessageBox]::Show('¿Borrar también tu configuración, iconos y copias de seguridad?' +
     "`n(Elige No si piensas volver a instalarla.)", 'Stream Dock Lite', 'YesNo', 'Question')
if ($r -eq 'Yes') {
    Remove-Item (Join-Path $env:APPDATA 'StreamDockLite') -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $env:LOCALAPPDATA 'StreamDockLite') -Recurse -Force -ErrorAction SilentlyContinue
}

# La carpeta del programa se borra cuando este script termina
Start-Process cmd.exe -ArgumentList "/c timeout /t 2 /nobreak >nul & rmdir /s /q `"$Dest`"" -WindowStyle Hidden
[System.Windows.Forms.MessageBox]::Show('Stream Dock Lite se desinstaló.', 'Stream Dock Lite') | Out-Null
