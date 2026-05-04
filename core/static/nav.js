// nav.js — Barra de navegación común para el admin del restaurante.
// Inyecta una topbar al inicio del <body> con tabs a las distintas secciones.
// Uso: <script src="/static/nav.js"></script> en cualquier página del admin.

(function() {
  const SECCIONES = [
    { path: '/admin',              label: '🍽️ Carta',         match: ['/admin', '/admin/'] },
    { path: '/admin/cocina',       label: '🍳 Cocina',         match: ['/admin/cocina'] },
    { path: '/admin/distribucion', label: '🗺️ Distribución',  match: ['/admin/distribucion'] },
  ];

  const css = `
    #atn-nav{position:sticky;top:0;left:0;right:0;z-index:1000;background:#0f172a;color:#e2e8f0;
      display:flex;align-items:center;padding:0 16px;height:46px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
      border-bottom:1px solid #1e293b;box-shadow:0 2px 8px rgba(0,0,0,.15)}
    #atn-nav .atn-logo{font-weight:800;font-size:14px;letter-spacing:1px;color:#fbbf24;margin-right:24px;text-transform:uppercase}
    #atn-nav .atn-tabs{display:flex;gap:2px;flex:1}
    #atn-nav .atn-tab{padding:10px 18px;color:#94a3b8;text-decoration:none;font-size:13px;font-weight:600;border-bottom:3px solid transparent;transition:all .15s}
    #atn-nav .atn-tab:hover{color:#e2e8f0;background:rgba(255,255,255,.04)}
    #atn-nav .atn-tab.active{color:#fbbf24;border-bottom-color:#fbbf24}
    #atn-nav .atn-right{font-size:12px;color:#64748b;display:flex;align-items:center;gap:14px}
    #atn-nav .atn-restaurante{color:#cbd5e1;font-weight:600}
    @media(max-width:600px){
      #atn-nav{padding:0 8px;overflow-x:auto}
      #atn-nav .atn-tab{padding:10px 12px;font-size:12px;white-space:nowrap}
      #atn-nav .atn-logo{font-size:12px;margin-right:10px}
      #atn-nav .atn-right{display:none}
    }
  `;

  function build() {
    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    const nav = document.createElement('nav');
    nav.id = 'atn-nav';
    const path = window.location.pathname.replace(/\/$/, '') || '/admin';

    let html = `<div class="atn-logo">⊙ Atenea Admin</div><div class="atn-tabs">`;
    SECCIONES.forEach(s => {
      const active = s.match.some(m => path === m || path.startsWith(m + '/'));
      html += `<a class="atn-tab${active ? ' active' : ''}" href="${s.path}">${s.label}</a>`;
    });
    html += `</div><div class="atn-right" id="atn-restaurante"></div>`;
    nav.innerHTML = html;

    // Insertar al principio del body
    document.body.insertBefore(nav, document.body.firstChild);

    // Cargar nombre del restaurante (no bloqueante)
    fetch('/api/info').then(r => r.ok ? r.json() : null).then(d => {
      if (!d) return;
      const cont = document.getElementById('atn-restaurante');
      if (cont && d.nombre) cont.innerHTML = `<span class="atn-restaurante">${escapeHtml(d.nombre)}</span>`;
    }).catch(()=>{});
  }

  function escapeHtml(s) {
    return String(s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }
})();
