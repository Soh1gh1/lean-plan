param([string]$OutputPath = 'test-results\geometry\native-window.png')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.runtime\pythonw.exe'
$appProcess = Get-Process -Name pythonw -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowTitle -eq 'Lean Plan' -and $_.Path -eq $pythonPath
} | Select-Object -First 1
if (-not $appProcess) { throw 'The Lean Plan window is not open.' }
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class LeanWindowCapture {
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint flags);
}
'@
$rect = New-Object LeanWindowCapture+Rect
[void][LeanWindowCapture]::GetWindowRect($appProcess.MainWindowHandle, [ref]$rect)
$bitmap = New-Object System.Drawing.Bitmap ($rect.Right-$rect.Left), ($rect.Bottom-$rect.Top)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$context = $graphics.GetHdc()
try { $captured = [LeanWindowCapture]::PrintWindow($appProcess.MainWindowHandle, $context, 2) }
finally { $graphics.ReleaseHdc($context) }
if (-not $captured) { throw 'Windows could not capture this window.' }
$destination = Join-Path $projectRoot $OutputPath
$bitmap.Save($destination, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
Write-Output $destination
