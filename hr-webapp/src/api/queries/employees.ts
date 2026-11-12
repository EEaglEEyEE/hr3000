import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, unwrap } from '../client'
import type { components } from '../schema'

export type Employee = components['schemas']['EmployeeResponse']
export type EmployeeCreateRequest = components['schemas']['EmployeeCreateRequest']
export type EmployeeUpdateRequest = components['schemas']['EmployeeUpdateRequest']
export type HrRole = components['schemas']['HrRole']

interface EmployeeFilters {
  search?: string
  locationId?: number
  active?: boolean
  /** Abteilung samt Unterabteilungen */
  departmentId?: number
  withoutDepartment?: boolean
}

export function useEmployeesQuery(filters: EmployeeFilters = {}) {
  return useQuery({
    queryKey: ['employees', filters],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees', {
          params: {
            query: {
              search: filters.search || undefined,
              location_id: filters.locationId,
              active: filters.active,
              department_id: filters.departmentId,
              without_department: filters.withoutDepartment || undefined,
            },
          },
        }),
      ),
  })
}

export function useEmployeeQuery(employeeId: number | undefined) {
  return useQuery({
    queryKey: ['employees', employeeId],
    queryFn: async () =>
      unwrap(
        await apiClient.GET('/employees/{employee_id}', {
          params: { path: { employee_id: employeeId! } },
        }),
      ),
    enabled: employeeId !== undefined,
  })
}

export function useCreateEmployeeMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: EmployeeCreateRequest) =>
      unwrap(await apiClient.POST('/employees', { body: payload })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['employees'] })
    },
  })
}

export function useUpdateEmployeeMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      employeeId,
      payload,
    }: {
      employeeId: number
      payload: EmployeeUpdateRequest
    }) =>
      unwrap(
        await apiClient.PATCH('/employees/{employee_id}', {
          params: { path: { employee_id: employeeId } },
          body: payload,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['employees'] })
      // Abteilung oder Führungskraft können sich geändert haben
      void queryClient.invalidateQueries({ queryKey: ['org-chart'] })
      void queryClient.invalidateQueries({ queryKey: ['departments'] })
    },
  })
}

export function useAnonymizeEmployeeMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (employeeId: number) =>
      unwrap(
        await apiClient.POST('/employees/{employee_id}/anonymize', {
          params: { path: { employee_id: employeeId } },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['employees'] })
    },
  })
}

export function useResetEmployeePasswordMutation() {
  return useMutation({
    mutationFn: async ({ employeeId, sendEmail }: { employeeId: number; sendEmail: boolean }) =>
      unwrap(
        await apiClient.POST('/employees/{employee_id}/reset-password', {
          params: { path: { employee_id: employeeId } },
          body: { send_email: sendEmail },
        }),
      ),
  })
}

/** Admin setzt die Zwei-Faktor-Anmeldung eines Mitarbeiters zurück (z. B. Handy verloren). */
export function useResetEmployeeTwoFactorMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (employeeId: number) => {
      const result = await apiClient.POST('/employees/{employee_id}/2fa-reset', { params: { path: { employee_id: employeeId } } })
      if (result.error) unwrap(result)
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['employees'] }),
  })
}

export function useUpdateEmployeeHrRoleMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      employeeId,
      hrRole,
      payrollAccess,
      customRoleId,
    }: {
      employeeId: number
      hrRole: HrRole | null
      payrollAccess?: boolean
      /** Eigene Rolle (nur HR): undefined = unverändert, null = keine */
      customRoleId?: number | null
    }) =>
      unwrap(
        await apiClient.PATCH('/employees/{employee_id}/hr-role', {
          params: { path: { employee_id: employeeId } },
          body: {
            hr_role: hrRole,
            ...(payrollAccess === undefined ? {} : { payroll_access: payrollAccess }),
            ...(customRoleId === undefined ? {} : { custom_role_id: customRoleId }),
          },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['employees'] })
      void queryClient.invalidateQueries({ queryKey: ['roles'] })
    },
  })
}
