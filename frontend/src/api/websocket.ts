/** WebSocket 客户端 — 单例 + 自动重连 */

import type {
  ServerEvent,
} from '@/types'

export type MessageHandler = (msg: ServerEvent) => void

class WsClient {
  private ws: WebSocket | null = null
  private handler: MessageHandler | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private retries = 0
  private maxRetries = 5
  private url = ''

  connect(threadId: string) {
    this.disconnect()
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    this.url = `${proto}//${location.host}/ws/${threadId}`
    this.retries = 0
    this._open()
  }

  private _open() {
    this.ws = new WebSocket(this.url)

    this.ws.onopen = () => {
      this.retries = 0
    }

    this.ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data) as ServerEvent
        this.handler?.(msg)
      } catch {
        console.error('[WS] 解析消息失败', e.data)
      }
    }

    this.ws.onclose = () => {
      this._scheduleReconnect()
    }

    this.ws.onerror = () => {
      this.ws?.close()
    }
  }

  private _scheduleReconnect() {
    if (this.retries >= this.maxRetries) return
    const delay = Math.min(1000 * 2 ** this.retries, 10000)
    this.retries++
    this.reconnectTimer = setTimeout(() => this._open(), delay)
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      this.ws.onclose = null
      this.ws.close()
      this.ws = null
    }
  }

  send(data: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }

  onMessage(handler: MessageHandler) {
    this.handler = handler
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

export const wsClient = new WsClient()
