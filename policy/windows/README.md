# Windows native diagnostics for OpenCode 1.18.32

This is a **narrow project-local native permission fragment**, independent of Linux P0.
It permits only the exact PowerShell command patterns `Get-Date -Format o`,
`[System.Environment]::OSVersion.VersionString`, and `Get-Location`.
The `bash: {"*": "ask"}` fallback is required because the built-in agent
defaults to `"*": "allow"` when no rule matches. A compound command is
allowed only when every extracted command pattern matches an allow rule.
No external-directory or safety/guard permission is changed.

Run from the `opencode_permissions` checkout on Windows:

```powershell
py -3 tools\windows_native_diagnostics.py status --project C:\Users\Dima\Projects\LanFabricRoot
py -3 tools\windows_native_diagnostics.py enable --project C:\Users\Dima\Projects\LanFabricRoot
```

Start a new OpenCode session in that workspace, then check the real prompt.
The installer requires exactly version 1.18.32, creates only
`<project>\opencode.json`, and refuses existing project `opencode.json`
or `opencode.jsonc`. It never edits the global OpenCode config.
To remove its unchanged file:

```powershell
py -3 tools\windows_native_diagnostics.py disable --project C:\Users\Dima\Projects\LanFabricRoot
```

This is not a general permission profile: other shell commands can still ask.
Agent-specific rules and other effective layers may override these project
rules, so an installed file alone is not proof of reduced visible prompts.
Do not use `Allow always` as a substitute: OpenCode 1.18.32 creates reusable
prefix rules from that reply.
