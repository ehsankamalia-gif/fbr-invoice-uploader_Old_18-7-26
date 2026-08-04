Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

repoRoot = fso.GetParentFolderName(WScript.ScriptFullName)
scriptPath = repoRoot & "\dev_launcher\start_fastapi.ps1"
configPath = repoRoot & "\dev_launcher\config\local-dev.json"
debugEnvPath = repoRoot & "\.dbg\api-autostart-failure.env"

Function JsonEscape(value)
    value = Replace(value, "\", "\\")
    value = Replace(value, """", "\""")
    value = Replace(value, "/", "\/")
    value = Replace(value, vbCrLf, "\n")
    value = Replace(value, vbCr, "\n")
    value = Replace(value, vbLf, "\n")
    JsonEscape = value
End Function

Sub SendDebugEvent(hypothesisId, location, message, dataJson)
    On Error Resume Next

    debugServerUrl = "http://127.0.0.1:7777/event"
    debugSessionId = "api-autostart-failure"

    If fso.FileExists(debugEnvPath) Then
        Set envFile = fso.OpenTextFile(debugEnvPath, 1)
        envContent = envFile.ReadAll
        envFile.Close
        envContent = Replace(envContent, vbCrLf, vbLf)
        envLines = Split(envContent, vbLf)

        For Each envLine In envLines
            If Left(envLine, 17) = "DEBUG_SERVER_URL=" Then
                debugServerUrl = Mid(envLine, 18)
            ElseIf Left(envLine, 17) = "DEBUG_SESSION_ID=" Then
                debugSessionId = Mid(envLine, 18)
            End If
        Next
    End If

    payload = "{""sessionId"":""" & JsonEscape(debugSessionId) & """,""runId"":""pre-fix"",""hypothesisId"":""" & JsonEscape(hypothesisId) & """,""location"":""" & JsonEscape(location) & """,""msg"":""[DEBUG] " & JsonEscape(message) & """,""data"":" & dataJson & ",""ts"":" & CLng(Timer() * 1000) & "}"

    Set xhr = CreateObject("WinHttp.WinHttpRequest.5.1")
    xhr.Open "POST", debugServerUrl, False
    xhr.SetRequestHeader "Content-Type", "application/json"
    xhr.Send payload

    On Error GoTo 0
End Sub

If Not fso.FileExists(scriptPath) Then
    ' #region debug-point A:missing-script
    Call SendDebugEvent("A", "start_system_silent.vbs:scriptPath", "Silent startup script is missing.", "{""scriptPath"":""" & JsonEscape(scriptPath) & """}")
    ' #endregion
    WScript.Quit 1
End If

If Not fso.FileExists(configPath) Then
    ' #region debug-point A:missing-config
    Call SendDebugEvent("A", "start_system_silent.vbs:configPath", "Silent startup config is missing.", "{""configPath"":""" & JsonEscape(configPath) & """}")
    ' #endregion
    WScript.Quit 1
End If

' Delay auto-start slightly after Windows sign-in so Laragon services
' have time to initialize on slower boots.
' #region debug-point E:startup-entry
Call SendDebugEvent("E", "start_system_silent.vbs:beforeSleep", "Silent startup entered and is waiting before launching PowerShell.", "{""repoRoot"":""" & JsonEscape(repoRoot) & """,""delayMs"":120000}")
' #endregion
WScript.Sleep 120000

WshShell.CurrentDirectory = repoRoot
command = "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & chr(34) & scriptPath & chr(34) & " -ConfigPath " & chr(34) & configPath & chr(34)
' #region debug-point A:powershell-launch
Call SendDebugEvent("A", "start_system_silent.vbs:beforeRun", "Silent startup is launching the PowerShell supervisor.", "{""scriptPath"":""" & JsonEscape(scriptPath) & """,""configPath"":""" & JsonEscape(configPath) & """}")
' #endregion
WshShell.Run command, 0, False
' #region debug-point A:launch-dispatched
Call SendDebugEvent("A", "start_system_silent.vbs:afterRun", "Silent startup dispatched the PowerShell supervisor command.", "{""command"":""" & JsonEscape(command) & """}")
' #endregion

Set fso = Nothing
Set WshShell = Nothing
