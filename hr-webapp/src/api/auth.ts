interface TokenPair {
  access_token: string
  refresh_token: string
}

async function postLogin(endpoint: string, email: string, password: string): Promise<TokenPair> {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(body?.detail ?? 'Login fehlgeschlagen.')
  }

  return response.json() as Promise<TokenPair>
}

export function hrLogin(email: string, password: string): Promise<TokenPair> {
  return postLogin('/api/auth/hr/login', email, password)
}

export function employeeLogin(email: string, password: string): Promise<TokenPair> {
  return postLogin('/api/auth/employee/login', email, password)
}
