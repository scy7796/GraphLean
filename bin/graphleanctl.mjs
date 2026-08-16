#!/usr/bin/env node
import { spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)))
const cli = join(packageRoot, 'graphleanctl.py')
const argv = process.argv.slice(2)
const candidates = process.platform === 'win32'
  ? [['py', ['-3']], ['python', []], ['python3', []]]
  : [['python3', []], ['python', []]]

for (const [exe, prefix] of candidates) {
  const result = spawnSync(exe, [...prefix, '-B', cli, ...argv], { stdio: 'inherit' })
  if (result.error?.code === 'ENOENT') continue
  if (result.error) {
    console.error(`graphleanctl: failed to start ${exe}: ${result.error.message}`)
    process.exit(1)
  }
  process.exit(result.status ?? 1)
}

console.error('graphleanctl: Python 3.9+ was not found on PATH.')
process.exit(127)

