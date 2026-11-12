import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PlainText } from './PlainText'
import { parsePlainText } from './textBlocks'
import { careerPath, jobIdFromParam } from './labels'

describe('parsePlainText', () => {
  it('trennt Absätze an Leerzeilen und erkennt Aufzählungen', () => {
    expect(parsePlainText('Hallo\nWelt\n\n- eins\n* zwei\n• drei\n\nEnde')).toEqual([
      { kind: 'paragraph', lines: ['Hallo', 'Welt'] },
      { kind: 'list', items: ['eins', 'zwei', 'drei'] },
      { kind: 'paragraph', lines: ['Ende'] },
    ])
  })

  it('wechselt innerhalb eines Absatzes zwischen Text und Liste', () => {
    expect(parsePlainText('Aufgaben:\n- A\n- B\nDanach')).toEqual([
      { kind: 'paragraph', lines: ['Aufgaben:'] },
      { kind: 'list', items: ['A', 'B'] },
      { kind: 'paragraph', lines: ['Danach'] },
    ])
  })

  it('ignoriert leere Eingaben und Windows-Zeilenenden', () => {
    expect(parsePlainText('')).toEqual([])
    expect(parsePlainText('   \n\n  ')).toEqual([])
    expect(parsePlainText('a\r\n\r\nb')).toEqual([
      { kind: 'paragraph', lines: ['a'] },
      { kind: 'paragraph', lines: ['b'] },
    ])
  })

  it('ein Bindestrich ohne Leerzeichen ist keine Aufzählung', () => {
    expect(parsePlainText('-5 Grad')).toEqual([{ kind: 'paragraph', lines: ['-5 Grad'] }])
  })
})

describe('PlainText', () => {
  it('zeigt HTML als Text statt es auszuführen', () => {
    const { container } = render(<PlainText text={'<script>alert(1)</script>\n\n- <b>fett</b>'} />)
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(screen.getByText('<script>alert(1)</script>')).toBeInTheDocument()
    expect(screen.getByRole('listitem')).toHaveTextContent('<b>fett</b>')
  })

  it('setzt Zeilenumbrüche innerhalb eines Absatzes', () => {
    const { container } = render(<PlainText text={'Zeile 1\nZeile 2'} />)
    expect(container.querySelectorAll('p')).toHaveLength(1)
    expect(container.querySelectorAll('br')).toHaveLength(1)
  })
})

describe('Adressen der Karriereseite', () => {
  it('baut den Pfad aus ID und Slug und liest die ID zurück', () => {
    expect(careerPath({ id: 12, slug: 'lagerist' })).toBe('/karriere/12-lagerist')
    expect(jobIdFromParam('12-lagerist')).toBe(12)
    expect(jobIdFromParam('7')).toBe(7)
  })

  it('weist ungültige Angaben ab', () => {
    for (const value of [undefined, '', 'abc', '0-x', '-3', '12abc', '99999999999999999999']) {
      expect(jobIdFromParam(value)).toBeNull()
    }
  })
})
