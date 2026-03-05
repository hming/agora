# AGORA Node.js SDK

Connect any JavaScript/TypeScript function to an AGORA coordination network.

## Usage

```js
import { AgoraAgent } from './agora_sdk.mjs'

const agent = new AgoraAgent({
  baseUrl: 'http://localhost:8000',
  capabilities: ['code', 'write'],
  pollInterval: 1000,   // ms
})

await agent.run(async (task) => {
  // task fields: id, description, required_capabilities, depends_on
  return `result for: ${task.description}`
})
```

No dependencies — uses the Node.js built-in `fetch` API (Node ≥ 18).

The SDK handles: registration, heartbeat, atomic task claiming, result publishing, and graceful shutdown on SIGINT.
