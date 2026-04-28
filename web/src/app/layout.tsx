import type { Metadata } from 'next'
import './globals.css'
import { getInfo } from '@/lib/core'

export async function generateMetadata(): Promise<Metadata> {
  const info = await getInfo()
  return {
    title: info.nombre || 'Restaurante',
    description: info.eslogan || '',
  }
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const info = await getInfo()
  return (
    <html lang="es">
      <head>
        <style>{`:root { --accent: ${info.color || '#FF6B35'}; }`}</style>
      </head>
      <body>{children}</body>
    </html>
  )
}
