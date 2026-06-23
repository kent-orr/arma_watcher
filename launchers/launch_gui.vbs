Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")
' Script lives in launchers/; run from the repo root one level up so uv finds pyproject.toml.
dir = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
shell.CurrentDirectory = dir
shell.Run "uv run arma-watcher-gui", 0, False
