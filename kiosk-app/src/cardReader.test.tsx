/** USB-/Bluetooth-Chipleser im Tastatur-Modus: schnelle Tastenfolge + Enter = Chip.
 * Menschliches Tippen (z.B. in der Namenssuche) darf nie als Chip erkannt werden. */
import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { normalizeCardUid, useKeyboardCardReader } from './cardReader'

let clock = 0
function type(text: string, gapMs: number) {
  for (const key of text) {
    clock += gapMs
    window.dispatchEvent(new KeyboardEvent('keydown', { key }))
  }
}
function enter(gapMs = 5) {
  clock += gapMs
  const event = new KeyboardEvent('keydown', { key: 'Enter', cancelable: true })
  window.dispatchEvent(event)
  return event
}

function setup(enabled = true) {
  clock = 1000
  vi.spyOn(performance, 'now').mockImplementation(() => clock)
  const onCard = vi.fn()
  const hook = renderHook(({ on }) => useKeyboardCardReader(onCard, on), { initialProps: { on: enabled } })
  return { onCard, hook }
}

describe('normalizeCardUid', () => {
  it.each([
    ['04:A2:3B:FF', '04a23bff'],
    [' 04-a2-3b-ff ', '04a23bff'],
    ['04 A2 3B FF', '04a23bff'],
    ['0012345678', '0012345678'],
  ])('%s -> %s', (input, expected) => {
    expect(normalizeCardUid(input)).toBe(expected)
  })
})

describe('Tastatur-Chipleser', () => {
  it('erkennt eine schnell "getippte" Kartennummer mit Enter', () => {
    const { onCard } = setup()
    type('0012345678', 5)
    const event = enter()
    expect(onCard).toHaveBeenCalledWith('0012345678')
    expect(event.defaultPrevented).toBe(true)
  })

  it('ignoriert menschlich langsames Tippen', () => {
    const { onCard } = setup()
    type('max', 150)
    enter(150)
    expect(onCard).not.toHaveBeenCalled()
  })

  it('verwirft eine abgebrochene Eingabe und erkennt die nächste Karte sauber', () => {
    const { onCard } = setup()
    type('0099', 5)
    clock += 500 // Pause: Rest gehört nicht mehr dazu
    type('04A23BFF', 5)
    enter()
    expect(onCard).toHaveBeenCalledTimes(1)
    expect(onCard).toHaveBeenCalledWith('04A23BFF')
  })

  it('ignoriert zu kurze Nummern und lässt Enter dann normal durch', () => {
    const { onCard } = setup()
    type('123', 5)
    const event = enter()
    expect(onCard).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })

  it('übernimmt nur erlaubte Zeichen (Ziffern, Buchstaben, ":" und "-")', () => {
    const { onCard } = setup()
    type('04:A2-3B!?', 5)
    enter()
    expect(onCard).toHaveBeenCalledWith('04:A2-3B')
  })

  it('liest zwei Karten nacheinander unabhängig voneinander', () => {
    const { onCard } = setup()
    type('11111111', 5)
    enter()
    type('22222222', 5)
    enter()
    expect(onCard.mock.calls).toEqual([['11111111'], ['22222222']])
  })

  it('reagiert nicht, solange er ausgeschaltet ist, und hört nach dem Ausschalten auf', () => {
    const { onCard, hook } = setup(false)
    type('0012345678', 5)
    enter()
    expect(onCard).not.toHaveBeenCalled()

    hook.rerender({ on: true })
    type('0012345678', 5)
    enter()
    expect(onCard).toHaveBeenCalledTimes(1)

    hook.rerender({ on: false })
    type('0012345678', 5)
    enter()
    expect(onCard).toHaveBeenCalledTimes(1)
  })
})
