$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $Python = @('py','-3') }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $Python = @('python') }
else { throw 'Python 3.9+ was not found on PATH.' }
$exe = $Python[0]; $prefix = @(); if ($Python.Length -gt 1) { $prefix = $Python[1..($Python.Length-1)] }
& $exe @prefix "$Root\UNINSTALL.py" @args
exit $LASTEXITCODE
