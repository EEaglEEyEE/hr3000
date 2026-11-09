import type { components } from '../../api/schema'
import { useAbsenceTypeMap } from '../../api/queries/absenceTypes'
import { absenceColorStyle } from '../../lib/dayCellStyle'
import { ABSENCE_TYPE_LABELS, DAY_STATUS_LABELS } from '../../lib/labels'
import { Badge, type BadgeProps } from '../ui/badge'

type SummaryStatus = components['schemas']['SummaryStatus']
type AbsenceType = components['schemas']['AbsenceType']

const ABSENCE_VARIANT: Record<AbsenceType, BadgeProps['variant']> = {
  VACATION: 'violet',
  SICK: 'warning',
  SPECIAL_LEAVE: 'default',
  UNPAID: 'default',
  TIME_OFF_IN_LIEU: 'info',
  WORK_TIME: 'success',
  PUBLIC_HOLIDAY: 'info',
  CHILD_SICK: 'warning',
  PARENTAL_LEAVE: 'default',
  SHORT_TIME_WORK: 'default',
  UNEXCUSED: 'default',
  CARE_LEAVE: 'default',
}

/** Einheitliche Status-Anzeige für einen Tag – verwendet in Überstundenkonto,
 * Kalenderansicht, globaler Anwesenheitsübersicht und "Zu klären". */
export function DayStatusBadge({
  status,
  absenceType,
  absenceTypeId,
}: {
  status: SummaryStatus
  absenceType?: AbsenceType | null
  absenceTypeId?: number | null
}) {
  const types = useAbsenceTypeMap()
  const custom = absenceTypeId != null ? types.get(absenceTypeId) : undefined
  if (status === 'ABSENCE' && custom) {
    return (
      <Badge className="text-slate-800" style={absenceColorStyle(custom.color)}>
        {custom.name}
      </Badge>
    )
  }
  if (status === 'ABSENCE' && absenceType) {
    return <Badge variant={ABSENCE_VARIANT[absenceType]}>{ABSENCE_TYPE_LABELS[absenceType]}</Badge>
  }
  if (status === 'COMPLETE') {
    return <Badge variant="success">{DAY_STATUS_LABELS.COMPLETE}</Badge>
  }
  if (status === 'PRESENT') {
    return <Badge variant="info">{DAY_STATUS_LABELS.PRESENT}</Badge>
  }
  if (status === 'ON_ERRAND') {
    return <Badge variant="violet">{DAY_STATUS_LABELS.ON_ERRAND}</Badge>
  }
  if (status === 'ON_BREAK') {
    return <Badge variant="orange">{DAY_STATUS_LABELS.ON_BREAK}</Badge>
  }
  if (status === 'ERROR') {
    return <Badge variant="danger">{DAY_STATUS_LABELS.ERROR}</Badge>
  }
  if (status === 'HOLIDAY') {
    return <Badge variant="teal">{DAY_STATUS_LABELS.HOLIDAY}</Badge>
  }
  if (status === 'PLANNED_OFF') {
    return <Badge>{DAY_STATUS_LABELS.PLANNED_OFF}</Badge>
  }
  return <Badge variant="warning">{DAY_STATUS_LABELS.OPEN_MISSING_PUNCH}</Badge>
}
