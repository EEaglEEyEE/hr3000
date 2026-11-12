import { parsePlainText } from './textBlocks'

/** Einfacher Text sicher als Absätze und Listen. Der Text wird nie als HTML ausgewertet (React
 * maskiert ihn) – kein dangerouslySetInnerHTML. */
export function PlainText({ text, className }: { text: string; className?: string }) {
  const blocks = parsePlainText(text)
  return (
    <div className={className ?? 'flex flex-col gap-3 text-sm text-slate-700'}>
      {blocks.map((block, index) =>
        block.kind === 'list' ? (
          <ul key={index} className="list-disc space-y-1 pl-5">
            {block.items.map((item, itemIndex) => (
              <li key={itemIndex}>{item}</li>
            ))}
          </ul>
        ) : (
          <p key={index}>
            {block.lines.map((line, lineIndex) => (
              <span key={lineIndex}>
                {lineIndex > 0 && <br />}
                {line}
              </span>
            ))}
          </p>
        ),
      )}
    </div>
  )
}
