import { expect, it } from 'vitest'
import { router } from '#/router'
import { validatePublishSearch } from './utils/validatePublishSearch'
import { resolvePublishSelection } from './PublishPage.logic'

it.each(['1', '001', '1e3', 'true', 'A1'])(
  'preserves seat ID %s through URL serialization and selection',
  (id) => {
    const query = router.options.stringifySearch({ room: 101, seat: id })
    const search = validatePublishSearch(router.options.parseSearch(query))
    expect(search).toEqual({ room: 101, seat: id })
    const seat = { id, room_id: 101, seat_number: 2 }
    const classrooms = [{ id: 101, name: 'Room', seats: [seat] }]
    expect(
      resolvePublishSelection(classrooms, search.room, search.seat).seat,
    ).toBe(seat)
  },
)

it.each(['', 'A-1', 'A/B', 'A 1', 'Ａ1'])(
  'falls back for invalid seat ID %s',
  (seat) => {
    expect(validatePublishSearch({ seat }).seat).toBeUndefined()
  },
)
