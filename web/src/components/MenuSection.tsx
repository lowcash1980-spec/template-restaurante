'use client'
import { useEffect, useRef, useState } from 'react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import type { Categoria, Plato } from '@/lib/core'

gsap.registerPlugin(ScrollTrigger)

export default function MenuSection({ menu }: { menu: Categoria[] }) {
  const [activeCat, setActiveCat] = useState(0)
  const sectionRef = useRef<HTMLElement>(null)
  const cardsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!sectionRef.current) return
    gsap.from('.menu-title', {
      scrollTrigger: { trigger: sectionRef.current, start: 'top 80%' },
      opacity: 0, y: 50, duration: 1, ease: 'power3.out'
    })
  }, [])

  useEffect(() => {
    if (!cardsRef.current) return
    gsap.from(cardsRef.current.querySelectorAll('.plato-card'), {
      opacity: 0, y: 40, duration: 0.6, stagger: 0.08, ease: 'power2.out'
    })
  }, [activeCat])

  const platos = menu[activeCat]?.platos || []

  return (
    <section id="menu" ref={sectionRef} className="py-28 px-6">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="text-center mb-16 menu-title">
          <p className="text-xs uppercase tracking-widest font-semibold mb-4" style={{ color: 'var(--accent)' }}>— Nuestra carta —</p>
          <h2 className="font-serif text-5xl md:text-6xl font-bold">Lo que cocinamos</h2>
        </div>

        {/* Category tabs */}
        <div className="flex gap-2 flex-wrap justify-center mb-12">
          {menu.map((cat, i) => (
            <button
              key={cat.id}
              onClick={() => setActiveCat(i)}
              className="px-5 py-2.5 rounded-full text-sm font-semibold transition-all duration-300"
              style={{
                background: activeCat === i ? 'var(--accent)' : 'var(--surface)',
                color: activeCat === i ? '#fff' : 'var(--muted)',
                border: activeCat === i ? 'none' : '1px solid var(--border)',
              }}
            >
              {cat.icono} {cat.nombre}
            </button>
          ))}
        </div>

        {/* Dishes */}
        <div ref={cardsRef} className="grid gap-4 md:grid-cols-2">
          {platos.filter(p => p.disponible).map((plato) => (
            <PlatoCard key={plato.id} plato={plato} />
          ))}
          {platos.filter(p => !p.disponible).map((plato) => (
            <PlatoCard key={plato.id} plato={plato} agotado />
          ))}
        </div>

        {platos.length === 0 && (
          <p className="text-center py-16" style={{ color: 'var(--muted)' }}>Sin platos en esta categoría</p>
        )}
      </div>
    </section>
  )
}

function PlatoCard({ plato, agotado }: { plato: Plato; agotado?: boolean }) {
  return (
    <div className={`plato-card flex gap-4 p-4 rounded-2xl border transition-all duration-300 ${agotado ? 'opacity-40' : 'hover:border-[var(--accent)]'}`} style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
      {plato.foto_url && (
        <img
          src={plato.foto_url}
          alt={plato.nombre}
          className="w-20 h-20 rounded-xl object-cover flex-shrink-0"
          onError={(e) => (e.currentTarget.style.display = 'none')}
        />
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold text-base leading-tight">
              {plato.nombre}
              {plato.es_especial ? <span className="ml-2 text-xs" style={{ color: 'var(--accent)' }}>⭐ Especial</span> : null}
            </p>
            {agotado && <span className="text-xs font-medium" style={{ color: 'var(--muted)' }}>No disponible hoy</span>}
          </div>
          <span className="font-bold text-base flex-shrink-0" style={{ color: 'var(--accent)' }}>
            {plato.precio.toFixed(2)} €
          </span>
        </div>
        {plato.descripcion && (
          <p className="text-sm mt-1 leading-relaxed" style={{ color: 'var(--muted)' }}>{plato.descripcion}</p>
        )}
      </div>
    </div>
  )
}
