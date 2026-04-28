'use client'
import { useEffect, useRef } from 'react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import type { InfoRestaurante } from '@/lib/core'

gsap.registerPlugin(ScrollTrigger)

// ── AJUSTAR: coordenadas de Google Maps para cada cliente ──
const MAP_EMBED = 'https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d...' // reemplazar

export default function Contacto({ info }: { info: InfoRestaurante }) {
  const sectionRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!sectionRef.current) return
    gsap.from('.contacto-item', {
      scrollTrigger: { trigger: sectionRef.current, start: 'top 75%' },
      opacity: 0, y: 30, duration: 0.6, stagger: 0.1, ease: 'power2.out'
    })
  }, [])

  return (
    <section id="contacto" ref={sectionRef} className="py-28 px-6" style={{ background: 'var(--surface)' }}>
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <p className="text-xs uppercase tracking-widest font-semibold mb-4" style={{ color: 'var(--accent)' }}>— Encuéntranos —</p>
          <h2 className="font-serif text-5xl font-bold">Contacto</h2>
        </div>

        <div className="grid md:grid-cols-2 gap-12 items-start">
          {/* Info */}
          <div className="space-y-6">
            <div className="contacto-item p-6 rounded-2xl border" style={{ background: 'var(--bg)', borderColor: 'var(--border)' }}>
              <p className="text-xs uppercase tracking-widest mb-1" style={{ color: 'var(--accent)' }}>Dirección</p>
              <p className="font-medium">{info.direccion}</p>
            </div>

            <div className="contacto-item p-6 rounded-2xl border" style={{ background: 'var(--bg)', borderColor: 'var(--border)' }}>
              <p className="text-xs uppercase tracking-widest mb-1" style={{ color: 'var(--accent)' }}>Teléfono</p>
              <a href={`tel:${info.telefono}`} className="font-medium hover:underline">{info.telefono}</a>
            </div>

            <div className="contacto-item flex gap-3">
              {info.telefono && (
                <a href={`tel:${info.telefono}`} className="flex-1 flex items-center justify-center gap-2 py-4 rounded-2xl font-semibold transition-all duration-300 hover:opacity-80" style={{ background: 'var(--accent)', color: '#fff' }}>
                  📞 Llamar
                </a>
              )}
              {info.whatsapp && (
                <a href={`https://wa.me/${info.whatsapp}`} target="_blank" rel="noopener noreferrer" className="flex-1 flex items-center justify-center gap-2 py-4 rounded-2xl font-semibold border transition-all duration-300 hover:scale-105" style={{ borderColor: '#25d366', color: '#25d366' }}>
                  💬 WhatsApp
                </a>
              )}
            </div>
          </div>

          {/* Map */}
          <div className="contacto-item rounded-2xl overflow-hidden border h-80" style={{ borderColor: 'var(--border)' }}>
            {MAP_EMBED.includes('!1m18') ? (
              <iframe
                src={MAP_EMBED}
                width="100%"
                height="100%"
                style={{ border: 0, filter: 'invert(90%) hue-rotate(180deg)' }}
                allowFullScreen
                loading="lazy"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center" style={{ background: 'var(--bg)', color: 'var(--muted)' }}>
                📍 {info.direccion}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="mt-20 pt-8 border-t text-center text-xs" style={{ borderColor: 'var(--border)', color: 'var(--muted)' }}>
          <p>{info.nombre} · {info.direccion}</p>
          <p className="mt-1">© {new Date().getFullYear()} Todos los derechos reservados</p>
        </div>
      </div>
    </section>
  )
}
