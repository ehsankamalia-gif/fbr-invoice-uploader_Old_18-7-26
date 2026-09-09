' Silent launcher for the Ehsan Trader FBR System.
'
' A virtual environment stores the absolute path of the Python that created it.
' When that Python is upgraded, uninstalled, or the project is copied to another
' computer, launching it fails with "did not find executable at ...".
' This script detects that case and repairs the environment automatically
' instead of showing that error.

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)

WshShell.CurrentDirectory = strPath

venvPythonW = strPath & "\venv\Scripts\pythonw.exe"
venvPython = strPath & "\venv\Scripts\python.exe"
mainScript = strPath & "\main.pyw"
launcher = strPath & "\launch_app.bat"

' Fast path: use the existing environment when it actually runs.
' Tested with python.exe, never pythonw.exe, because a broken environment shows
' a blocking message box instead of returning an error.
healthy = False
If fso.FileExists(venvPython) And fso.FileExists(venvPythonW) Then
    On Error Resume Next
    exitCode = WshShell.Run("""" & venvPython & """ -c ""import sys""", 0, True)
    If Err.Number = 0 And exitCode = 0 Then healthy = True
    On Error Goto 0
End If

If healthy Then
    WshShell.Run """" & venvPythonW & """ """ & mainScript & """", 0, False
    Set WshShell = Nothing
    WScript.Quit
End If

' Slow path: detect Python and repair or build the environment. Shown in a
' window so the progress of a rebuild is visible rather than appearing frozen.
If Not fso.FileExists(launcher) Then
    MsgBox "Cannot start: launch_app.bat is missing from" & vbCrLf & strPath, 16, "Ehsan Trader FBR System"
    WScript.Quit 1
End If

WshShell.Run """" & launcher & """", 1, False
Set WshShell = Nothing
