import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import {
  getModels,
  getRecording,
  getRecordings,
  getRehearsal,
  saveLabels,
} from '#/api/calibration.api'
import type { LabelInterval, Recording } from '../../../types'
import { useTelemetry } from './useTelemetry'

export const useCalibration = () => {
  const { live, history, connected } = useTelemetry()
  const queryClient = useQueryClient()
  const recordings = useQuery({
    queryKey: ['calibration-recordings'],
    queryFn: getRecordings,
    enabled: live?.storage_ready === true,
    refetchInterval: 3000,
  })
  const models = useQuery({
    queryKey: ['calibration-models'],
    queryFn: getModels,
    enabled: live?.storage_ready === true,
    refetchInterval: 2000,
  })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const rehearsal = useQuery({
    queryKey: ['calibration-rehearsal', selectedId],
    queryFn: () => getRehearsal(selectedId!),
    enabled: selectedId !== null,
    refetchInterval: live?.active_recording === selectedId ? 3000 : false,
  })
  const detail = useQuery({
    queryKey: ['calibration-detail', selectedId],
    queryFn: () => getRecording(selectedId!),
    enabled: selectedId !== null,
  })
  const [participant, setParticipant] = useState('')
  const [notes, setNotes] = useState('')
  const [role, setRole] = useState<Recording['role']>('development')
  const [selected, setSelected] = useState<string[]>([])
  const [label, setLabel] = useState<LabelInterval['label']>('awake')
  const [posture, setPosture] = useState('')
  const [mark, setMark] = useState<LabelInterval | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const run = async (operation: () => Promise<void>) => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await operation()
      await queryClient.invalidateQueries({
        queryKey: ['calibration-recordings'],
      })
      await queryClient.invalidateQueries({ queryKey: ['calibration-models'] })
      await queryClient.invalidateQueries({ queryKey: ['calibration-detail'] })
      await queryClient.invalidateQueries({
        queryKey: ['calibration-rehearsal'],
      })
    } catch (failure) {
      const message = axios.isAxiosError<{ detail: unknown }>(failure)
        ? failure.response?.data.detail
        : null
      setError(typeof message === 'string' ? message : String(failure))
    }
    setBusy(false)
  }
  const finishLabel = async () => {
    const recordingId = live?.active_recording
    if (!mark || !recordingId || !live.sample) return
    const current = await getRecording(recordingId)
    await saveLabels(recordingId, [
      ...current.intervals,
      { ...mark, end: live.sample.received_at },
    ])
    setMark(null)
    setNotice('Label interval saved.')
  }
  const selectedIds = new Set(selected)
  return {
    live,
    history,
    connected,
    recordings,
    models,
    selectedId,
    setSelectedId,
    rehearsal,
    detail,
    participant,
    setParticipant,
    notes,
    setNotes,
    role,
    setRole,
    selected,
    setSelected,
    selectedIds,
    label,
    setLabel,
    posture,
    setPosture,
    mark,
    setMark,
    busy,
    error,
    notice,
    setNotice,
    run,
    finishLabel,
  }
}
