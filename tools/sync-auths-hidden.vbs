' Hidden launcher for the QQBotStack-authsync scheduled task.
'
' Why this file exists: on the operator machine Windows Terminal is the default
' terminal. A console program started directly by Task Scheduler opens a visible
' Terminal window, and "powershell.exe -WindowStyle Hidden" does NOT suppress it
' because the terminal window is created before PowerShell applies that flag.
' WScript.Shell.Run with window style 0 hides the console at creation time.
'
' Task action: wscript.exe //nologo "<repo>\tools\sync-auths-hidden.vbs"
' The path is derived from this script's own location, so the repo can move.

Option Explicit

Dim fso, sh, scriptDir, ps1, cmd

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
ps1 = scriptDir & "\sync-auths.ps1"

cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & ps1 & """"

' 0 = hidden window, True = wait for the script to finish before exiting
sh.Run cmd, 0, True
