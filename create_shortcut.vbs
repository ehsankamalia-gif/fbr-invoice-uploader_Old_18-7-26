Set WshShell = WScript.CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get paths
strDesktop = WshShell.SpecialFolders("Desktop")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
targetScript = currentDir & "\run_silent.vbs"
pythonwPath = currentDir & "\venv\Scripts\pythonw.exe"
mainScript = currentDir & "\main.pyw"

' Check if target exists
If Not fso.FileExists(targetScript) Then
    MsgBox "run_silent.vbs not found!", 16, "Error"
    WScript.Quit
End If

' Create Shortcut
' Always launch through run_silent.vbs rather than pointing straight at
' venv\Scripts\pythonw.exe. A shortcut to the environment's interpreter breaks
' with "did not find executable at ..." as soon as that Python is upgraded,
' uninstalled, or the project is copied elsewhere; run_silent.vbs detects the
' installed Python and repairs the environment instead.
Set oShellLink = WshShell.CreateShortcut(strDesktop & "\Honda FBR Uploader.lnk")
oShellLink.TargetPath = "wscript.exe"
oShellLink.Arguments = chr(34) & targetScript & chr(34)
oShellLink.WorkingDirectory = currentDir
oShellLink.WindowStyle = 1
oShellLink.Description = "Launch Honda FBR Uploader (Silent)"

' Try to find an icon
iconPath = currentDir & "\assets\splash.png"
' Icons usually need .ico or .exe. PNG might not work on all Windows versions. 
' Falling back to python executable for icon if available
If fso.FileExists(currentDir & "\venv\Scripts\python.exe") Then
    oShellLink.IconLocation = currentDir & "\venv\Scripts\python.exe, 0"
End If

oShellLink.Save

MsgBox "Shortcut created on Desktop successfully!", 64, "Success"
