/** Entschärft Zellen, die Excel als Formel interpretieren würde (=, +, -, @, Tab, CR). */
function sanitize(value: string): string {
  return /^[=+\-@\t\r]/.test(value) ? `'${value}` : value
}

function cell(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return ''
  const text = typeof value === 'number' ? String(value).replace('.', ',') : sanitize(value)
  return /[;"\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/** Lädt Zeilen als CSV (Semikolon, UTF-8-BOM, deutsches Dezimalkomma) herunter. */
export function downloadCsv(filename: string, header: string[], rows: (string | number | null | undefined)[][]): void {
  const lines = [header, ...rows].map((row) => row.map(cell).join(';'))
  const blob = new Blob([`﻿${lines.join('\r\n')}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
