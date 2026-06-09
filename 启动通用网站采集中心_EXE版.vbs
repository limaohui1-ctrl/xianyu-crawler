Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

Function ZH(codes)
    parts = Split(codes, ",")
    text = ""
    For Each part In parts
        text = text & ChrW(CLng("&H" & Trim(part)))
    Next
    ZH = text
End Function

appName = ZH("901A,7528,7F51,7AD9,91C7,96C6,4E2D,5FC3")
exePath = scriptDir & "\" & appName & ".exe"
If Not fso.FileExists(exePath) Then
    exePath = scriptDir & "\dist\" & appName & "\" & appName & ".exe"
End If

If fso.FileExists(exePath) Then
    shell.CurrentDirectory = fso.GetParentFolderName(exePath)
    shell.Run """" & exePath & """", 1, False
Else
    message = ZH("6CA1,6709,627E,5230") & " EXE:" & vbCrLf & exePath & vbCrLf & vbCrLf & ZH("8BF7,5148,91CD,65B0,6253,5305,3002")
    title = ZH("542F,52A8,5931,8D25")
    MsgBox message, 48, title
End If
