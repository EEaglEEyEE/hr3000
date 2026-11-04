import { useBrandingQuery } from '../../api/queries/branding'
import { cn } from '../../lib/utils'

/** HR3000-Wortbildmarke; optional darunter/daneben das Firmenlogo des Mandanten
 * (das Firmenlogo ersetzt nie Favicon/App-Icon). */
export function BrandLogo({ showTenantLogo = true, size = 'md' }: { showTenantLogo?: boolean; size?: 'md' | 'lg' }) {
  const brandingQuery = useBrandingQuery()
  const tenantLogo = showTenantLogo ? brandingQuery.data?.logo_data_url : null
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <img src="/logo.svg" alt="" className={cn(size === 'lg' ? 'h-10 w-10' : 'h-8 w-8')} />
        <span
          className={cn(
            'bg-gradient-to-r from-indigo-600 to-teal-600 bg-clip-text font-bold tracking-wide text-transparent',
            size === 'lg' ? 'text-2xl' : 'text-lg',
          )}
        >
          HR3000
        </span>
      </div>
      {tenantLogo && (
        <img
          src={tenantLogo}
          alt={brandingQuery.data?.tenant_name ?? 'Firmenlogo'}
          className={cn('object-contain object-left', size === 'lg' ? 'max-h-14 max-w-56' : 'max-h-10 max-w-40')}
        />
      )}
    </div>
  )
}
