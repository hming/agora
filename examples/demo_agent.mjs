/**
 * demo_agent.mjs — AGORA Node.js external agent demo
 *
 * Usage (ensure the AGORA backend is running, Node.js 18+ required):
 *   node examples/demo_agent.mjs           # single agent
 *   node examples/demo_agent.mjs --multi   # three agents with different capabilities
 *
 * Replace myHandler with a real LLM call to connect any AI capability.
 */

import { AgoraAgent } from '../sdk/nodejs/agora_sdk.mjs'

const AGORA_URL = process.env.AGORA_URL ?? 'http://localhost:8000'

// Your task handling logic — replace the mock with a real LLM call
async function myHandler(task) {
  await new Promise(r => setTimeout(r, 400))   // simulate processing time
  return `[Node.js Agent] Completed: ${(task.description ?? '').slice(0, 100)}`
}

async function runSingle() {
  const agent = new AgoraAgent({
    baseUrl: AGORA_URL,
    capabilities: ['general'],
    pollInterval: 800,
  })

  console.log(`\nAGORA Node.js Agent`)
  console.log(`  server: ${AGORA_URL}`)
  console.log(`  capabilities: ${agent.capabilities.join(', ')}`)
  console.log('  Press Ctrl+C to stop\n')

  process.on('SIGINT', () => { agent.stop() })
  await agent.run(myHandler)
}

async function runMulti() {
  const configs = [
    { capabilities: ['code'],    agentId: 'js-coder' },
    { capabilities: ['search'],  agentId: 'js-searcher' },
    { capabilities: ['code', 'search'], agentId: 'js-fullstack' },
  ]

  console.log(`\nStarting ${configs.length} Node.js agents...\n`)

  const agents = configs.map(c => new AgoraAgent({ baseUrl: AGORA_URL, pollInterval: 600, ...c }))
  process.on('SIGINT', () => agents.forEach(a => a.stop()))
  await Promise.all(agents.map(a => a.run(myHandler)))
}

const multi = process.argv.includes('--multi')
multi ? runMulti() : runSingle()
