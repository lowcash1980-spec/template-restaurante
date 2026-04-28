'use client'
import { useEffect, useState } from 'react'

export default function Navbar({ nombre }: { nombre: string }) {
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 60)
    window.addEventListener('scroll', handler)
    return () => window.removeEventListener('scroll', handler)
  }, [])

  const links = [
    { href: '#menu', label: 'Menú' },
    { href: '#nosotros', label: 'Nosotros' },
    { href: '#horarios', label: 'Horarios' },
    { href: '#contacto', label: 'Contacto' },
  ]

  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50 transition-all duration-500"
      style={{ background: scrolled ? 'rgba(8,8,8,0.95)' : 'transparent', backdropFilter: scrolled ? 'blur(12px)' : 'none', borderBottom: scrolled ? '1px solid var(--border)' : 'none' }}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <span className="font-serif text-xl font-bold tracking-wide" style={{ color: 'var(--accent)' }}>
          {nombre}
        </span>

        {/* Desktop */}
        <ul className="hidden md:flex items-center gap-8">
          {links.map(l => (
            <li key={l.href}>
              <a href={l.href} className="text-sm font-medium text-[var(--muted)] hover:text-white transition-colors duration-200 tracking-wide uppercase">{l.label}</a>
            </li>
          ))}
          <li>
            <a href="#contacto" className="px-5 py-2 rounded-full text-sm font-semibold transition-all duration-200 hover:opacity-80" style={{ background: 'var(--accent)', color: '#fff' }}>
              Reservar
            </a>
          </li>
        </ul>

        {/* Mobile toggle */}
        <button className="md:hidden text-white" onClick={() => setOpen(!open)} aria-label="Menú">
          <div className="w-6 flex flex-col gap-1.5">
            <span className={`block h-0.5 bg-current transition-all duration-300 ${open ? 'rotate-45 translate-y-2' : ''}`} />
            <span className={`block h-0.5 bg-current transition-all duration-300 ${open ? 'opacity-0' : ''}`} />
            <span className={`block h-0.5 bg-current transition-all duration-300 ${open ? '-rotate-45 -translate-y-2' : ''}`} />
          </div>
        </button>
      </div>

      {/* Mobile menu */}
      {open && (
        <div className="md:hidden px-6 pb-6 pt-2" style={{ background: 'rgba(8,8,8,0.98)' }}>
          {links.map(l => (
            <a key={l.href} href={l.href} onClick={() => setOpen(false)} className="block py-3 text-base font-medium border-b" style={{ borderColor: 'var(--border)', color: 'var(--muted)' }}>
              {l.label}
            </a>
          ))}
          <a href="#contacto" onClick={() => setOpen(false)} className="mt-4 block text-center px-5 py-3 rounded-full font-semibold" style={{ background: 'var(--accent)', color: '#fff' }}>
            Reservar mesa
          </a>
        </div>
      )}
    </nav>
  )
}
