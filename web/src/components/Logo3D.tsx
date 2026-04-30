'use client'
import { useEffect, useRef } from 'react'
import { gsap } from 'gsap'

interface Props {
  nombre: string
}

export default function Logo3D({ nombre }: Props) {
  const textRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = textRef.current
    if (!el) return

    // Entrada desde el eje Z con rotación
    gsap.fromTo(
      el,
      { rotateY: -30, rotateX: 12, opacity: 0, scale: 0.75 },
      { rotateY: 0, rotateX: 0, opacity: 1, scale: 1, duration: 1.6, ease: 'power3.out', delay: 0.6 }
    )

    // Float idle suave
    gsap.to(el, {
      rotateY: 4,
      rotateX: -3,
      duration: 3.5,
      ease: 'sine.inOut',
      yoyo: true,
      repeat: -1,
      delay: 2.2,
    })

    // Parallax con el ratón
    const onMouseMove = (e: MouseEvent) => {
      const x = (e.clientX / window.innerWidth - 0.5) * 18
      const y = (e.clientY / window.innerHeight - 0.5) * -12
      gsap.to(el, { rotateY: x, rotateX: y, duration: 0.9, ease: 'power2.out', overwrite: 'auto' })
    }

    window.addEventListener('mousemove', onMouseMove)
    return () => window.removeEventListener('mousemove', onMouseMove)
  }, [])

  return (
    <div style={{ perspective: '900px', perspectiveOrigin: '50% 50%' }}>
      <div
        ref={textRef}
        style={{
          display: 'inline-block',
          fontSize: 'clamp(3rem, 10vw, 8rem)',
          fontFamily: 'serif',
          fontWeight: 900,
          letterSpacing: '-0.02em',
          lineHeight: 1,
          transformStyle: 'preserve-3d',
          color: '#ffffff',
          textShadow: [
            '1px 1px 0 color-mix(in srgb, var(--accent) 95%, #000)',
            '2px 2px 0 color-mix(in srgb, var(--accent) 85%, #000)',
            '3px 3px 0 color-mix(in srgb, var(--accent) 75%, #000)',
            '4px 4px 0 color-mix(in srgb, var(--accent) 65%, #000)',
            '5px 5px 0 color-mix(in srgb, var(--accent) 55%, #000)',
            '6px 6px 0 color-mix(in srgb, var(--accent) 45%, #000)',
            '7px 7px 0 color-mix(in srgb, var(--accent) 35%, #000)',
            '8px 8px 0 color-mix(in srgb, var(--accent) 25%, #000)',
            '10px 10px 20px rgba(0,0,0,0.6)',
          ].join(', '),
        }}
      >
        {nombre}
      </div>
    </div>
  )
}
