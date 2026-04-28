'use client'
import { useEffect, useRef } from 'react'
import dynamic from 'next/dynamic'
import { gsap } from 'gsap'

const Spline = dynamic(() => import('@splinetool/react-spline'), { ssr: false })

// ── AJUSTAR: reemplaza esta URL con la escena Spline del cliente ──
const SPLINE_URL = 'https://prod.spline.design/placeholder-scene/scene.splinecode'

interface Props {
  nombre: string
  eslogan: string
  abierto: boolean
}

export default function Hero({ nombre, eslogan, abierto }: Props) {
  const titleRef = useRef<HTMLHeadingElement>(null)
  const subRef = useRef<HTMLParagraphElement>(null)
  const ctaRef = useRef<HTMLDivElement>(null)
  const badgeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const tl = gsap.timeline({ defaults: { ease: 'power3.out' } })
    tl.from(badgeRef.current, { opacity: 0, y: -20, duration: 0.6, delay: 0.3 })
      .from(titleRef.current, { opacity: 0, y: 60, duration: 1 }, '-=0.2')
      .from(subRef.current, { opacity: 0, y: 30, duration: 0.8 }, '-=0.5')
      .from(ctaRef.current, { opacity: 0, y: 20, duration: 0.6 }, '-=0.4')
  }, [])

  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden">
      {/* Spline 3D background */}
      <div className="absolute inset-0 z-0 opacity-60">
        <Spline scene={SPLINE_URL} />
      </div>

      {/* Gradient overlay */}
      <div className="absolute inset-0 z-10" style={{ background: 'radial-gradient(ellipse at center, transparent 30%, rgba(8,8,8,0.85) 100%)' }} />
      <div className="absolute bottom-0 left-0 right-0 h-48 z-10" style={{ background: 'linear-gradient(to top, var(--bg), transparent)' }} />

      {/* Content */}
      <div className="relative z-20 text-center px-6 max-w-4xl mx-auto">
        <div ref={badgeRef} className="inline-flex items-center gap-2 mb-8 px-4 py-1.5 rounded-full text-xs font-semibold uppercase tracking-widest border" style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}>
          <span className={`w-2 h-2 rounded-full ${abierto ? 'bg-green-400' : 'bg-red-400'}`} style={{ boxShadow: abierto ? '0 0 6px #4ade80' : 'none' }} />
          {abierto ? 'Abierto ahora' : 'Cerrado ahora'}
        </div>

        <h1 ref={titleRef} className="font-serif font-black leading-none mb-6" style={{ fontSize: 'clamp(3rem, 10vw, 8rem)', letterSpacing: '-0.02em' }}>
          {nombre}
        </h1>

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
