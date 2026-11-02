import { useEffect, useState } from 'react'
import type { LiveTelemetry, RawSample } from '../../../types'

export const useTelemetry = () => {
  const [live, setLive] = useState<LiveTelemetry | null>(null)
  const [history, setHistory] = useState<RawSample[]>([])
  const [connected, setConnected] = useState(false)
  useEffect(() => {
    const events = new EventSource('/api/calibration/events')
    events.onmessage = (event: MessageEvent<string>) => {
      const next = JSON.parse(event.data) as LiveTelemetry
      setLive(next)
      setConnected(true)
      const sample = next.sample
      if (sample) {
        setHistory((previous) => {
          if (previous.at(-1)?.received_at === sample.received_at)
            return previous
          return [...previous, sample].slice(-120)
        })
      }
    }
    events.onerror = () => setConnected(false)
    return () => events.close()
  }, [])
  return { live, history, connected }
}
