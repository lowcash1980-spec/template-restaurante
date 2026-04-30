'use client'
import { useEffect, useRef } from 'react'
import { gsap } from 'gsap'
import Logo3D from './Logo3D'

interface Props {
  nombre: string
  eslogan: string
  abierto: boolean
}

export default function Hero({ nombre, eslogan, abierto }: Props) {
  const subRef = useRef<HTMLParagraphElement>(null)
  const ctaRef = useRef<HTMLDivElement>(null)
  const badgeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const tl = gsap.timeline({ defaults: { ease: 'power3.out' } })
    tl.from(badgeRef.current, { opacity: 0, y: -20, duration: 0.6, delay: 0.3 })
      .from(subRef.current, { opacity: 0, y: 30, duration: 0.8 }, '-=0.3')
      .from(ctaRef.current, { opacity: 0, y: 20, duration: 0.6 }, '-=0.4')
  }, [])

  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden">
      {/* Animated gradient background */}
      <div className="absolute inset-0 z-0" style={{
        background: 'radial-gradient(ellipse at 20% 50%, color-mix(in srgb, var(--accent) 25%, transparent) 0%, transparent 60%), radial-gradient(ellipse at 80% 20%, color-mix(in srgb, var(--accent) 15%, transparent) 0%, transparent 50%), var(--bg)',
      }} />

      {/* Gradient overlay */}
      <div className="absolute inset-0 z-10" style={{ background: 'radial-gradient(ellipse at center, transparent 30%, rgba(8,8,8,0.85) 100%)' }} />
      <div className="absolute bottom-0 left-0 right-0 h-48 z-10" style={{ background: 'linear-gradient(to top, var(--bg), transparent)' }} />

      {/* Content */}
      <div className="relative z-20 text-center px-6 max-w-4xl mx-auto">
        <div ref={badgeRef} className="inline-flex items-center gap-2 mb-8 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest border" style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}>
          <span className={`w-2 h-2 rounded-full ${abierto ? 'bg-green-400' : 'bg-red-400'}`} style={{ boxShadow: abierto ? '0 0 6px #4ade80' : 'none' }} />
          {abierto ? 'Abierto ahora' : 'Cerrado ahora'}
        </div>

        {/* Logo 3D */}
        <div className="mb-6">
          <Logo3D nombre={nombre} />
        </div>

        <p ref={subRef} className="text-lg md:text-2xl font-light mb-10 max-w-xl mx-auto" style={{ color: 'var(--muted)' }}>
          {eslogan}
        </p>

        <div ref={ctaRef} className="flex flex-wrap gap-4 justify-center">
          <a href="#menu" className="px-8 py-4 rounded-full font-semibold text-base transition-all duration-300 hover:scale-105 hover:shadow-lg" style={{ background: 'var(--accent)', color: '#fff', boxShadow: '0 0 30px color-mix(in srgb, var(--accent) 40%, transparent)' }}>
            Ver carta
          </a>
          <a href="#contacto" className="px-8 py-4 rounded-full font-semibold text-base border transition-all duration-300 hover:scale-105" style={{ borderColor: 'rgba(255,255,255,0.2)', color: '#fff', backdropFilter: 'blur(8px)' }}>
            Reservar mesa
          </a>
        </div>
      </div>

      {/* Scroll indicator */}
      <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-20 flex flex-col items-center gap-2 opacity-40">
        <span className="text-xs uppercase tracking-widest" style={{ color: 'var(--muted)' }}>Scroll</span>
        <div className="w-px h-12 relative overflow-hidden" style={{ background: 'var(--border)' }}>
          <div className="absolute top-0 w-full h-4 animate-bounce" style={{ background: 'var(--accent)' }} />
        </div>
      </div>
    </section>
  )
}
