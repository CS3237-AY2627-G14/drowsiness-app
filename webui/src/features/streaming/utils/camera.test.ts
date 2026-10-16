import { expect, it } from 'vitest'
import { calculatePaddedFrameLayout } from './camera'

it('pads landscape without cropping', () => {
  expect(calculatePaddedFrameLayout(1280, 720, 320, 240)).toEqual({
    x: 0,
    y: 30,
    width: 320,
    height: 180,
  })
})
it('pads portrait without cropping', () => {
  expect(calculatePaddedFrameLayout(480, 640, 1280, 720)).toEqual({
    x: 370,
    y: 0,
    width: 540,
    height: 720,
  })
})
