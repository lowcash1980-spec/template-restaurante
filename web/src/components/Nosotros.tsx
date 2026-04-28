'use client'
import { useEffect, useRef } from 'react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

gsap.registerPlugin(ScrollTrigger)

// ── AJUSTAR: textos e imagen de cada cliente ──
const TEXTO_PRINCIPAL = 'Somos más que un restaurante. Somos el lugar donde cada plato cuenta una historia, donde los ingredientes de temporada se convierten en experiencias que perduran.'
const TEXTO_SECUNDARIO = 'Fundados con la pasión de ofrecer lo mejor de la cocina mediterránea, llevamos años convirtiendo cada visita en un momento especial.'
const IMAGEN_URL = '/nosotros.jpg' // reemplazar con foto real del restaurante
const STATS = [
  { numero: '15+', label: 'Años de experiencia' },
  { numero: '200+', label: 'Platos creados' },
  { numero: '4.9', label: 'Valoración media' },
]

export default function Nosotros() {
  const sectionRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!sectionRef.current) return
    const tl = gsap.timeline({
      scrollTrigger: { trigger: sectionRef.current, start: 'top 70%' }
    })
    tl.from('.nos-text', { opacity: 0, x: -60, duration: 1, ease: 'power3.out', stagger: 0.15 })
      .from('.nos-img', { opacity: 0, x: 60, scale: 0.95, duration: 1, ease: 'power3.out' }, '-=0.8')
      .from('.nos-stat', { opacity: 0, y: 30, duration: 0.6, stagger: 0.1, ease: 'power2.out' }, '-=0.5')
  }, [])

  return (
    <section id="nosotros" ref={sectionRef} className="py-28 px-6" style={{ background: 'var(--surface)' }}>
      <div className="max-w-5xl mx-auto">
        <div className="grid md:grid-cols-2 gap-16 items-center">
          {/* Text */}
          <div>
            <p className="nos-text text-xs uppercase tracking-widest font-semibold mb-6" style={{ color: 'var(--accent)' }}>— Nuestra historia —</p>
            <h2 className="nos-text font-serif text-4xl md:text-5xl font-bold leading-tight mb-8">
              Cocina con alma,<br />
              <em className="italic" style={{ color: 'var(--accent)' }}>sabor con memoria</em>
            </h2>
            <p className="nos-text text-base leading-relaxed mb-4" style={{ color: 'var(--muted)' }}>{TEXTO_PRINCIPAL}</p>
            <p className="nos-text text-sm leading-relaxed" style={{ color: 'var(--muted)' }}>{TEXTO_SECUNDARIO}</p>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-6 mt-12">
              {STATS.map(s => (
                <div key={s.label} className="nos-stat text-center">
                  <div className="font-serif text-3xl font-black mb-1" style={{ color: 'var(--accent)' }}>{s.numero}</div>
                  <div className="text-xs" style={{ color: 'var(--muted)' }}>{s.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Image */}
          <div className="nos-img relative">
            <div className="absolute -top-4 -right-4 w-full h-full rounded-3xl border opacity-20" style={{ borderColor: 'var(--accent)' }} />
            <img
              src={IMAGEN_URL}
              alt="Nuestro restaurante"
              className="w-full h-[500px] object-cover rounded-3xl"
              onError={(e) => {
                e.currentTarget.style.background = 'var(--border)'
                e.currentTarget.style.display = 'flex'
                e.currentTarget.removeAttribute('src')
              }}
            />
          </div>
        </div>
      </div>
    </section>
  )
}
