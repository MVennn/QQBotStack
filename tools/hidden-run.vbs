' Generic hidden runner for QQBotStack scheduled tasks (2026-11-01).
' Usage: wscript.exe //B //Nologo hidden-run.vbs "F:\...\run-X.cmd"
' wscript never allocates a console, and Run(..., 0, True) starts the target
' script with a hidden window. TRUE (synchronous) is deliberate: wscript stays
' alive as the task instance root, so "schtasks /end" still kills the whole
' process tree. With False the service orphans and /end becomes a no-op.
' Service output lands in the .log files each run-*.cmd redirects to.
Option Explicit
If WScript.Arguments.Count < 1 Then WScript.Quit 2
Dim sh
Set sh = CreateObject("WScript.Shell")
sh.Run """" & WScript.Arguments(0) & """", 0, True
