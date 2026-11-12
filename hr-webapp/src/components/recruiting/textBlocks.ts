/** Einfacher Text in Absätze und Listen zerlegen: Leerzeilen trennen Absätze, Zeilen mit „- “,
 * „* “ oder „• “ am Anfang werden zu Aufzählungen. */
export type Block = { kind: 'paragraph'; lines: string[] } | { kind: 'list'; items: string[] }

const BULLET = /^\s*[-*•]\s+/

export function parsePlainText(text: string): Block[] {
  const blocks: Block[] = []
  for (const chunk of text.replace(/\r\n?/g, '\n').split(/\n\s*\n/)) {
    const lines = chunk.split('\n').map((line) => line.trimEnd()).filter((line) => line.trim() !== '')
    let current: Block | null = null
    for (const line of lines) {
      const isItem = BULLET.test(line)
      if (isItem) {
        if (current?.kind !== 'list') {
          current = { kind: 'list', items: [] }
          blocks.push(current)
        }
        current.items.push(line.replace(BULLET, ''))
      } else {
        if (current?.kind !== 'paragraph') {
          current = { kind: 'paragraph', lines: [] }
          blocks.push(current)
        }
        current.lines.push(line.trim())
      }
    }
  }
  return blocks
}
