import { expect, it } from 'vitest'
import { getStreamingErrorMessage } from './streaming'

it('does not reinterpret internal TypeErrors as network errors', () => {
  expect(getStreamingErrorMessage(new TypeError('Internal error'))).toBe(
    'Internal error',
  )
})
