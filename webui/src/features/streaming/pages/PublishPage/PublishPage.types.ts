import type { RefObject } from 'react'
import type { Classroom, Seat } from '#/types/classrooms'
import type {
  DetectionResult,
  StreamDiagnosticsSnapshot,
} from '../../types/protocol.types'
import type { StreamingPhase } from '../../types/streaming.types'

export type CameraPreviewProps = {
  videoRef: RefObject<HTMLVideoElement | null>
  canvasRef: RefObject<HTMLCanvasElement | null>
  active: boolean
}

export type SeatSelectorProps = {
  classrooms: Classroom[]
  room: Classroom
  seatId: string | null
  disabled: boolean
  onRoomChange: (id: number) => void
  onSeatChange: (id: string) => void
}

export type PublishControlsProps = {
  canStartCamera: boolean
  canPublish: boolean
  canStop: boolean
  onStart: () => void
  onPublish: () => void
  onStop: () => void
}

export type DetectionStatusProps = {
  detection: DetectionResult | null
  mqttAlertSentRecently: boolean
}

export type ConnectionStatusProps = { phase: StreamingPhase }

export type StreamMetricsProps = { metrics: StreamDiagnosticsSnapshot | null }

export type PublishTokenOverride = { seatId: string; token: string }

export type PublishSelection = {
  room: Classroom | undefined
  seat: Seat | undefined
}
