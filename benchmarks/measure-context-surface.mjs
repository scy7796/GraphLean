import { apply } from '../dsh/index.js'
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)))
const defs = []
const events = []
let guards = 0
const ctx = {
  tools: {
    register(def) { defs.push(def) },
    guard(_fn) { guards += 1 },
  },
  on(name, _fn) { events.push(name) },
}
apply(ctx, {})
const visible = defs.map(({name, description, parameters, output}) => ({name, description, parameters, output}))
const modelVisibleJsonBytes = Buffer.byteLength(JSON.stringify(visible), 'utf8')
const graphFiles = [
  ...readdirSync(join(ROOT, 'graph', 'templates')).filter(x => x.endsWith('.json')).map(x => join(ROOT, 'graph', 'templates', x)),
  join(ROOT, 'graph', 'quality', 'quality-improvement.json'),
  join(ROOT, 'graph', 'evolution', 'self-evolution.json'),
]
const hostGraphPayloadBytes = graphFiles.reduce((n, p) => n + readFileSync(p).byteLength, 0)
const result = {
  schemaVersion: 1,
  product: 'GraphLean',
  version: '1.0.0',
  modelVisibleControlTools: visible.length,
  modelVisibleJsonBytes,
  hostGraphTemplates: graphFiles.length,
  hostGraphPayloadBytes,
  systemPromptPolicyInjectionBytes: 0,
  registeredHostGuards: guards,
  registeredHostEvents: [...events].sort(),
  note: 'Byte counts cover GraphLean registered tool metadata and bundled graph JSON only; they are not tokenizer counts and do not include DeepSeek Harness base tools or provider messages.'
}
process.stdout.write(JSON.stringify(result, null, 2) + '\n')

