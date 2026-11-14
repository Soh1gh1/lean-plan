param([string]$OutputPath = 'test-results\geometry\visible-window.png')
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
public static class LeanVisibleCapture {
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hwnd, int command);
    [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
}
'@
$oldContext = [LeanVisibleCapture]::SetThreadDpiAwarenessContext([IntPtr](-4))
try {
    [void][LeanVisibleCapture]::ShowWindow($appProcess.MainWindowHandle, 9)
    [void][LeanVisibleCapture]::SetForegroundWindow($appProcess.MainWindowHandle)
    Start-Sleep -Milliseconds 400
    $rect = New-Object LeanVisibleCapture+Rect
    [void][LeanVisibleCapture]::GetWindowRect($appProcess.MainWindowHandle, [ref]$rect)
    $bitmap = New-Object System.Drawing.Bitmap ($rect.Right-$rect.Left), ($rect.Bottom-$rect.Top)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bitmap.Size)
        $destination = Join-Path $projectRoot $OutputPath
        $bitmap.Save($destination, [System.Drawing.Imaging.ImageFormat]::Png)
        Write-Output $destination
    } finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
} finally {
    [void][LeanVisibleCapture]::SetThreadDpiAwarenessContext($oldContext)
}
