import type { ConnectionStatusProps } from '../PublishPage.types'
import { phaseLabels } from '../utils/phaseLabels'

export const ConnectionStatus = ({ phase }: ConnectionStatusProps) => {
  const isLive = phase === 'live'
  const statusColors = isLive
    ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
    : 'border-[var(--line)] bg-white/80 text-[var(--sea-ink-soft)]'
  const statusClassName = `inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-semibold ${statusColors}`
  const indicatorColor = isLive ? 'bg-emerald-500' : 'bg-slate-400'
  const indicatorClassName = `size-2 rounded-full ${indicatorColor}`
  const label = phaseLabels[phase]
  return (
    <span role="status" className={statusClassName}>
      <span aria-hidden="true" className={indicatorClassName} />
      {label}
    </span>
  )
}
