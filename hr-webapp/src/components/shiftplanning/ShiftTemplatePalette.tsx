import type { ShiftTemplate } from '../../api/queries/shiftTemplates'
import { setShiftDragPayload } from '../../lib/shiftDragPayload'

interface ShiftTemplatePaletteProps {
  templates: ShiftTemplate[]
}

export function ShiftTemplatePalette({ templates }: ShiftTemplatePaletteProps) {
  return (
    <div className="flex w-48 flex-shrink-0 flex-col gap-2 rounded-md border border-slate-200 bg-white p-3 print:hidden">
      <p className="text-xs font-medium text-slate-500">
        Vorlage auf einen Tag ziehen, um sie zuzuweisen. Eine zugewiesene Schicht auf einen anderen
        Tag ziehen, um sie zu verschieben.
      </p>
      {templates.map((template) => (
        <div
          key={template.id}
          draggable
          onDragStart={(event) => setShiftDragPayload(event, { kind: 'template', templateId: template.id })}
          className="cursor-grab rounded-md border border-sky-300 bg-sky-100 px-2 py-1.5 text-xs font-medium text-sky-800 active:cursor-grabbing"
        >
          {template.name}
          {template.start_time && template.end_time && (
            <span className="ml-1 font-normal text-sky-600">
              {template.start_time.slice(0, 5)}–{template.end_time.slice(0, 5)}
            </span>
          )}
        </div>
      ))}
      <div
        draggable
        onDragStart={(event) => setShiftDragPayload(event, { kind: 'off' })}
        className="cursor-grab rounded-md border border-indigo-300 bg-indigo-50 px-2 py-1.5 text-xs font-medium text-indigo-700 active:cursor-grabbing"
      >
        Frei (expliziter freier Tag)
      </div>
      {templates.length === 0 && (
        <p className="text-xs text-slate-500">Noch keine Schichtvorlagen angelegt.</p>
      )}
    </div>
  )
}
