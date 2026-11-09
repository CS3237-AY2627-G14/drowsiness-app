import { useState } from 'react'
import type { ChangeEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getLecturerSeats } from '#/api/lecturer.api.ts'
import { useClassrooms } from '#/features/streaming/hooks/useClassrooms.ts'
import type { Seat } from '#/types/classrooms'

const SEATS_PER_ROW = 5

export const LecturerPage = () => {
  const classrooms = useClassrooms()
  const [roomId, setRoomId] = useState<number | null>(null)
  const seatsStatus = useQuery({
    queryKey: ['lecturer-seats'],
    queryFn: ({ signal }) => getLecturerSeats(signal),
    refetchInterval: 2000,
  })

  const rooms = classrooms.data ?? []
  const selectedRoomId = roomId ?? rooms[0]?.id ?? null
  const selectedRoom = rooms.find((room) => room.id === selectedRoomId) ?? null
  const statusBySeatId = new Map(
    (seatsStatus.data?.seats ?? []).map((status) => [status.seat_id, status]),
  )
  const drowsySeatIds = new Set(seatsStatus.data?.drowsy_seats ?? [])

  const handleRoomChange = (event: ChangeEvent<HTMLSelectElement>) => {
    setRoomId(Number(event.currentTarget.value))
  }

  const sortedSeats = [...(selectedRoom?.seats ?? [])].sort(
    (left, right) => left.seat_number - right.seat_number,
  )
  const rows: Seat[][] = []
  for (let index = 0; index < sortedSeats.length; index += SEATS_PER_ROW) {
    rows.push(sortedSeats.slice(index, index + SEATS_PER_ROW))
  }

  return (
    <main className="page-wrap py-6 text-[var(--sea-ink)] sm:py-10">
      <header className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="island-kicker mb-2">Lecturer view</p>
          <h1 className="display-title text-3xl sm:text-4xl">
            Classroom seat status
          </h1>
        </div>
        <div className="min-w-48">
          <label htmlFor="lecturer-room" className="mb-1.5 block text-sm font-medium">
            Classroom
          </label>
          <select
            id="lecturer-room"
            className="form-control"
            value={selectedRoomId ?? ''}
            disabled={rooms.length === 0}
            onChange={handleRoomChange}
          >
            {rooms.map((room) => (
              <option key={room.id} value={room.id}>
                {room.name}
              </option>
            ))}
          </select>
        </div>
      </header>

      {classrooms.isError ? (
        <div role="alert" className="island-shell rounded-2xl p-5 text-sm">
          Could not load classrooms. Please refresh the page.
        </div>
      ) : classrooms.isPending ? (
        <p role="status" className="text-sm text-[var(--sea-ink-soft)]">
          Loading classroom seats…
        </p>
      ) : selectedRoom ? (
        <section className="island-shell overflow-x-auto rounded-2xl p-4 sm:p-8">
          <div className="mx-auto mb-7 max-w-xl border-b-4 border-[var(--sea-ink)] pb-2 text-center text-xs font-bold uppercase tracking-[0.35em] text-[var(--sea-ink-soft)]">
            Front
          </div>

          <div className="mx-auto grid min-w-[480px] max-w-2xl gap-5">
            {rows.map((row, rowIndex) => (
              <div
                className="grid grid-cols-[1.5rem_repeat(5,minmax(58px,1fr))] items-center gap-3"
                key={`${rowIndex}-${row[0]?.id ?? 'empty'}`}
              >
                <span className="text-center text-xs font-bold text-[var(--sea-ink-soft)]">
                  {String.fromCharCode(65 + rowIndex)}
                </span>
                {row.map((seat, seatIndex) => {
                  const status = statusBySeatId.get(seat.id)
                  const unoccupied = status?.present === false
                  const drowsy =
                    !unoccupied &&
                    (status?.drowsy === true || drowsySeatIds.has(seat.id))
                  const hasStatus = status !== undefined && !unoccupied
                  const statusLabel = drowsy
                    ? `Seat ${seat.seat_number}: drowsy`
                    : hasStatus
                      ? `Seat ${seat.seat_number}: awake`
                      : unoccupied
                        ? `Seat ${seat.seat_number}: unoccupied`
                        : `Seat ${seat.seat_number}: no status`
                  const seatClass = drowsy
                    ? 'border-red-500 bg-red-500 text-white shadow-[0_0_0_4px_rgba(239,68,68,0.14)]'
                    : hasStatus
                      ? 'border-emerald-500 bg-emerald-50 text-emerald-900'
                      : 'border-[var(--line)] bg-white/60 text-[var(--sea-ink)]'

                  const column = seatIndex + 2
                  return (
                    <div key={seat.id} style={{ gridColumn: column }}>
                      <div
                        title={statusLabel}
                        className={`mx-auto flex aspect-square max-h-16 max-w-16 items-center justify-center rounded-xl border-2 text-sm font-extrabold transition-colors ${seatClass}`}
                        aria-label={statusLabel.replace(': ', ', ')}
                      >
                        {seat.seat_number}
                      </div>
                    </div>
                  )
                })}
              </div>
            ))}
          </div>

          <div className="mt-8 flex flex-wrap justify-center gap-5 text-xs font-semibold">
            <span className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-red-500" /> Drowsy
            </span>
            <span className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-emerald-500" /> Awake
            </span>
            <span className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full border border-[var(--line)] bg-white" /> Unoccupied / no status
            </span>
          </div>
        </section>
      ) : (
        <p className="text-sm text-[var(--sea-ink-soft)]">
          No classrooms are available.
        </p>
      )}
    </main>
  )
}
