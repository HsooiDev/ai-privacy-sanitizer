' AI Privacy Sanitizer — Windows Zero-Console Portable Launcher (Smart App Control Friendly)
' Double-click this script to launch Sanitizer using official Python (pythonw.exe) with no black console window.
Option Explicit

Dim shell, fso, repoDir, venvPyw, cmd, args, i, arg
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

repoDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = repoDir

args = ""
For i = 0 To WScript.Arguments.Count - 1
    arg = WScript.Arguments(i)
    If InStr(arg, " ") > 0 Then
        args = args & " """ & arg & """"
    Else
        args = args & " " & arg
    End If
Next

venvPyw = repoDir & "\.venv\Scripts\pythonw.exe"
If fso.FileExists(venvPyw) Then
    cmd = """" & venvPyw & """ -m src.main" & args
    shell.Run cmd, 0, False
    WScript.Quit 0
End If

On Error Resume Next
Dim rc
rc = shell.Run("pyw -3 -m src.main" & args, 0, False)
If Err.Number = 0 Then
    WScript.Quit 0
End If
Err.Clear

rc = shell.Run("pythonw -m src.main" & args, 0, False)
If Err.Number = 0 Then
    WScript.Quit 0
End If
On Error GoTo 0

MsgBox "Python (pythonw.exe) was not found." & vbCrLf & vbCrLf & _
       "Please install official Python 3.11+ from https://www.python.org/downloads/ " & _
       "or create .venv first (run: python -m venv .venv && .venv\Scripts\pip install -r requirements.txt).", _
       vbExclamation, "Sanitizer Launcher"
WScript.Quit 1
