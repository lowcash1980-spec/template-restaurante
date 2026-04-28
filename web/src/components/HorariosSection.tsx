'use client'
import { useEffect, useRef } from 'react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import type { Horario } from '@/lib/core'

gsap.registerPlugin(ScrollTrigger)

const NOMBRES = { lunes:'Lunes', martes:'Martes', miercoles:'Miércoles', jueves:'Jueves', viernes:'Viernes', sabado:'Sábado', domingo:'Domingo' } as Record<string,string>

export default function HorariosSection({ horarios, abierto }: { horarios: Horario[]; abierto: boolean }) {
  const sectionRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!sectionRef.current) return
    gsap.from('.horario-row', {
      scrollTrigger: { trigger: sectionRef.current, start: 'top 75%' },
      opacity: 0, x: -30, duration: 0.5, stagger: 0.07, ease: 'power2.out'
    })
  }, [])

  const hoy = ['domingo','lunes','martes','miercoles','jueves','viernes','sabado'][new Date().getDay()]

  return (
    <section id="horarios" ref={sectionRef} className="py-28 px-6">
      <div className="max-w-2xl mx-auto text-center">
        <p className="text-xs uppercase tracking-widest font-semibold mb-4" style={{ color: 'var(--accent)' }}>— Cuándo encontrarnos —</p>
        <h2 className="font-serif text-5xl font-bold mb-4">Horario</h2>

        <div className="inline-flex items-center gap-2 mb-12 px-4 py-2 rounded-full text-sm font-medium" style={{ background: abierto ? 'rgba(34,197,94,.1)' : 'rgba(239,68,68,.1)', color: abierto ? '#4ade80' : '#f87171' }}>
          <span className={`w-2 h-2 rounded-full ${abierto ? 'bg-green-400' : 'bg-red-400'}`} />
          {abierto ? 'Estamos abiertos ahora' : 'En este momento estamos cerrados'}
        </div>

        <div className="rounded-2xl overflow-hidden border" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
          {horarios.map((h, i) => (
            <div
              key={h.dia}
              className={`horario-row flex items-center justify-between px-6 py-4 ${i < horarios.length - 1 ? 'border-b' : ''} ${h.dia === hoy ? 'font-semibold' : ''}`}
              style={{ borderColor: 'var(--border)', background: h.dia === hoy ? 'rgba(255,255,255,0.03)' : 'transparent' }}
            >
              <div className="flex items-center gap-3">
                {h.dia === hoy && <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: 'var(--accent)' }} />}
                <span className={h.dia === hoy ? 'text-white' : ''} style={{ color: h.dia !== hoy ? 'var(--muted)' : undefined }}>
                  {NOMBRES[h.dia] || h.dia}
                </span>
              </div>
              <span style={{ color: h.abierto ? (h.dia === hoy ? 'var(--accent)' : 'var(--muted)') : 'var(--muted)', fontStyle: h.abierto ? 'normal' : 'italic' }}>
                {h.abierto ? `${h.apertura} – ${h.cierre}` : 'Cerrado'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
