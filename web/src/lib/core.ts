const CORE_URL = process.env.CORE_URL || 'http://localhost:8000'

export interface Plato {
  id: number
  nombre: string
  descripcion: string
  precio: number
  foto_url: string
  disponible: number
  es_especial: number
}

export interface Categoria {
  id: number
  nombre: string
  icono: string
  platos: Plato[]
}

export interface Horario {
  dia: string
  abierto: number
  apertura: string
  cierre: string
}

export interface InfoRestaurante {
  nombre: string
  eslogan: string
  direccion: string
  telefono: string
  whatsapp: string
  color: string
  horarios: Horario[]
}

export async function getMenu(): Promise<Categoria[]> {
  try {
    const res = await fetch(`${CORE_URL}/api/menu`, { next: { revalidate: 30 } })
    return res.ok ? res.json() : []
  } catch { return [] }
}

export async function getInfo(): Promise<InfoRestaurante> {
  try {
    const res = await fetch(`${CORE_URL}/api/info`, { next: { revalidate: 60 } })
    return res.ok ? res.json() : {}
  } catch {
    return { nombre: 'Restaurante', eslogan: '', direccion: '', telefono: '', whatsapp: '', color: '#FF6B35', horarios: [] }
  }
}

export function estaAbiertoAhora(horarios: Horario[]): boolean {
  const ahora = new Date()
  const dias = ['domingo','lunes','martes','miercoles','jueves','viernes','sabado']
  const hoy = dias[ahora.getDay()]
  const h = horarios.find(x => x.dia === hoy)
  if (!h || !h.abierto) return false
  const [hA, mA] = h.apertura.split(':').map(Number)
  const [hC, mC] = h.cierre.split(':').map(Number)
  const mins = ahora.getHours() * 60 + ahora.getMinutes()
  const abre = hA * 60 + mA
  let cierra = hC * 60 + mC
  if (cierra < abre) cierra += 1440
  return mins >= abre && mins < cierra
}
