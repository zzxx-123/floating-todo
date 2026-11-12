Option Explicit

' Floating Todo - silent launcher.
' Double-click this file to show the cards. Launching it again brings the
' already-running cards back to the front instead of starting a second copy.

Dim fso, shell, launchersDir, projectDir, appFile

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

launchersDir = fso.GetParentFolderName(WScript.ScriptFullName)
projectDir = fso.GetParentFolderName(launchersDir)
appFile = fso.BuildPath(projectDir, "app.pyw")

If Not fso.FileExists(appFile) Then
    MsgBox "app.pyw was not found:" & vbCrLf & appFile, 16, "Floating Todo"
    WScript.Quit 1
End If

shell.CurrentDirectory = projectDir

On Error Resume Next
shell.Run "pythonw.exe " & Chr(34) & appFile & Chr(34), 0, False
If Err.Number <> 0 Then
    Err.Clear
    shell.Run "pyw.exe -3 " & Chr(34) & appFile & Chr(34), 0, False
End If
If Err.Number <> 0 Then
    MsgBox "Python 3 was not found. Install Python 3 and make sure pythonw.exe is on PATH.", 16, "Floating Todo"
    WScript.Quit 1
End If
