import { useState } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import {
  resolvePublishSelection,
  resolvePublishToken,
} from '../PublishPage.logic'
import type { PublishTokenOverride } from '../PublishPage.types'
import type { Classroom } from '#/types/classrooms'

export const usePublishTarget = (classrooms: Classroom[]) => {
  const { room: selectedRoomId, seat: selectedSeatId } = useSearch({
    from: '/streaming',
  })
  const navigate = useNavigate({ from: '/streaming' })
  const [tokenOverride, setTokenOverride] =
    useState<PublishTokenOverride | null>(null)
  const { room, seat } = resolvePublishSelection(
    classrooms,
    selectedRoomId,
    selectedSeatId,
  )
  const token = resolvePublishToken(seat, tokenOverride)

  const selectRoom = (roomId: number) => {
    const nextRoom = classrooms.find((classroom) => classroom.id === roomId)
    void navigate({ search: { room: roomId, seat: nextRoom?.seats[0]?.id } })
    setTokenOverride(null)
  }
  const selectSeat = (seatId: number) => {
    if (!room) return
    void navigate({ search: { room: room.id, seat: seatId } })
    setTokenOverride(null)
  }
  const setToken = (value: string) => {
    if (seat) setTokenOverride({ seatId: seat.id, token: value })
  }
  return { room, seat, token, selectRoom, selectSeat, setToken }
}
