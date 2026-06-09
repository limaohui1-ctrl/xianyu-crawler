Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = scriptDir

pythonwPath = ""
candidatePaths = Array( _
    "D:\Python312\pythonw.exe", _
    "C:\Python312\pythonw.exe", _
    "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\pythonw.exe" _
)

For Each candidatePath In candidatePaths
    If fso.FileExists(candidatePath) Then
        pythonwPath = candidatePath
        Exit For
    End If
Next

If pythonwPath <> "" Then
    shell.Run """" & pythonwPath & """ """ & scriptDir & "\main.py""", 0, False
Else
    shell.Run "pyw -3 """ & scriptDir & "\main.py""", 0, False
End If
