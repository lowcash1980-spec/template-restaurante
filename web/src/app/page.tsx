import { getMenu, getInfo, estaAbiertoAhora } from '@/lib/core'
import Navbar from '@/components/Navbar'
import Hero from '@/components/Hero'
import MenuSection from '@/components/MenuSection'
import Nosotros from '@/components/Nosotros'
import HorariosSection from '@/components/HorariosSection'
import Contacto from '@/components/Contacto'
import SmoothScroll from '@/components/SmoothScroll'

export default async function Home() {
  const [menu, info] = await Promise.all([getMenu(), getInfo()])
  const abierto = estaAbiertoAhora(info.horarios || [])

  return (
    <SmoothScroll>
      <Navbar nombre={info.nombre} />
      <main>
        <Hero nombre={info.nombre} eslogan={info.eslogan} abierto={abierto} />
        <MenuSection menu={menu} />
        <Nosotros />
        <HorariosSection horarios={info.horarios || []} abierto={abierto} />
        <Contacto info={info} />
      </main>
    </SmoothScroll>
  )
}
