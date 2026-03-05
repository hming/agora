/**
 * AGORA SDK for Node.js
 *
 * 用法：
 *   import { AgoraAgent } from './agora_sdk.mjs'
 *
 *   const agent = new AgoraAgent({
 *     baseUrl: 'http://localhost:8000',
 *     capabilities: ['code', 'search'],
 *   })
 *
 *   await agent.run(async (task) => {
 *     // 用任意 LLM 或工具处理任务
 *     return `Completed: ${task.description}`
 *   })
 *
 * 依赖：Node.js 18+（内置 fetch），无需额外安装
 */

import { randomBytes } from 'node:crypto'

export class AgoraAgent {
  /**
   * @param {object} opts
   * @param {string}   [opts.baseUrl='http://localhost:8000']
   * @param {string[]} [opts.capabilities=[]]
   * @param {string}   [opts.agentId]           - 不填则自动生成
   * @param {number}   [opts.pollInterval=1000]  - ms
   * @param {number}   [opts.heartbeatInterval=10000] - ms
   */
  constructor({
    baseUrl = 'http://localhost:8000',
    capabilities = [],
    agentId,
    pollInterval = 1000,
    heartbeatInterval = 10000,
  } = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, '')
    this.capabilities = capabilities
    this.agentId = agentId ?? `ext-${randomBytes(3).toString('hex')}`
    this.pollInterval = pollInterval
    this.heartbeatInterval = heartbeatInterval
    this._running = false
  }

  // ------------------------------------------------------------------ //
  // Low-level API                                                        //
  // ------------------------------------------------------------------ //

  async _post(path, body) {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`POST ${path} → ${res.status}: ${await res.text()}`)
    return res.json()
  }

  async _delete(path) {
    const res = await fetch(`${this.baseUrl}${path}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`DELETE ${path} → ${res.status}`)
    return res.json()
  }

  async register() {
    const data = await this._post('/x/agents/register', {
      agent_id: this.agentId,
      capabilities: this.capabilities,
    })
    this.agentId = data.agent_id
    console.log(`[${this.agentId}] Registered | capabilities=${JSON.stringify(this.capabilities)}`)
  }

  async claim() {
    const data = await this._post(`/x/agents/${this.agentId}/claim`, {})
    return data.task ?? null
  }

  async done(taskId, result) {
    const data = await this._post(`/x/agents/${this.agentId}/tasks/${taskId}/done`, { result })
    return data.unblocked ?? 0
  }

  async failed(taskId, error) {
    await this._post(`/x/agents/${this.agentId}/tasks/${taskId}/failed`, { error: String(error) })
  }

  async heartbeat() {
    const data = await this._post(`/x/agents/${this.agentId}/heartbeat`, {})
    return data.epoch ?? 0
  }

  async vote(proposalId, approve) {
    return this._post(`/x/agents/${this.agentId}/vote`, { proposal_id: proposalId, approve })
  }

  async leave() {
    try {
      await this._delete(`/x/agents/${this.agentId}`)
    } catch { /* ignore on shutdown */ }
    console.log(`[${this.agentId}] Left AGORA`)
  }

  // ------------------------------------------------------------------ //
  // High-level run loop                                                  //
  // ------------------------------------------------------------------ //

  /**
   * 主循环：注册 → 认领任务 → 执行 → 发布结果 → 循环。
   *
   * @param {(task: object) => Promise<string>} handler
   */
  async run(handler) {
    await this.register()
    this._running = true

    const hbTimer = setInterval(async () => {
      try {
        const epoch = await this.heartbeat()
        // console.debug(`[${this.agentId}] Heartbeat epoch=${epoch}`)
      } catch (e) {
        console.warn(`[${this.agentId}] Heartbeat failed: ${e.message}`)
      }
    }, this.heartbeatInterval)

    try {
      while (this._running) {
        const task = await this.claim()
        if (task) {
          const desc = (task.description ?? '').slice(0, 80)
          console.log(`[${this.agentId}] Claimed ${task.id} | ${desc}`)
          try {
            const result = await handler(task)
            const unblocked = await this.done(task.id, result)
            console.log(`[${this.agentId}] Done ${task.id} | unblocked=${unblocked}`)
          } catch (e) {
            console.error(`[${this.agentId}] Failed ${task.id} | ${e.message}`)
            await this.failed(task.id, e.message)
          }
        } else {
          await new Promise(r => setTimeout(r, this.pollInterval))
        }
      }
    } finally {
      clearInterval(hbTimer)
      await this.leave()
    }
  }

  stop() {
    this._running = false
  }
}
