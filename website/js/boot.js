(() => {
  const doc = document.documentElement;
  const failures = [];
  let screen = null;
  let box = null;
  let failed = false;
  let done = false;
  const MIN_INTRO = 1800;
  const started = Date.now();
  const intro = (() => {
    try {
      return matchMedia('(min-width: 900px) and (hover: hover)').matches && !localStorage.getItem('dg-seen');
    } catch {
      return false;
    }
  })();

  const el = (tag, css, text) => {
    const node = document.createElement(tag);
    Object.assign(node.style, css);
    if (text) node.textContent = text;
    return node;
  };

  const button = (label, onClick, primary) => {
    const b = el('button', {
      font: '600 15px Inter, system-ui, sans-serif',
      padding: '12px 20px',
      margin: '6px',
      borderRadius: '10px',
      border: '1px solid #1f3a2a',
      background: primary ? '#1f3a2a' : 'transparent',
      color: primary ? '#fff' : '#1f3a2a',
    }, label);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  };

  const resetAndReload = async () => {
    try {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map(r => r.unregister()));
      const keys = await caches.keys();
      await Promise.all(keys.map(k => caches.delete(k)));
    } catch {}
    location.reload();
  };

  const build = () => {
    screen = el('div', {
      position: 'fixed',
      inset: '0',
      zIndex: '2000',
      background: '#F7FCE8',
      color: '#1f3a2a',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      textAlign: 'center',
      padding: '24px',
      font: '400 16px/1.5 Inter, system-ui, sans-serif',
      transition: 'opacity .25s',
    });
    screen.id = 'boot';
    screen.setAttribute('role', 'status');
    box = el('div', { maxWidth: '380px' });
    const logo = el('img', { width: intro ? '96px' : '72px', height: intro ? '96px' : '72px', marginBottom: '16px' });
    logo.src = 'icon.png';
    logo.alt = '';
    if (intro) {
      const track = el('div', { width: '220px', height: '4px', margin: '20px auto 0', background: 'rgba(31,58,42,.15)', borderRadius: '2px', overflow: 'hidden' });
      const bar = el('div', { height: '100%', width: '100%', background: '#357a4e', transformOrigin: 'left' });
      bar.animate([{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], { duration: MIN_INTRO, easing: 'cubic-bezier(.32,.72,0,1)', fill: 'forwards' });
      track.append(bar);
      box.append(logo, el('div', { font: '700 34px/1.2 Inter, system-ui, sans-serif', letterSpacing: '-0.5px' }, 'DumpGuard'), el('div', { marginTop: '6px', color: '#5b6f60' }, 'Waste management for NJ-06 towns'), track);
      screen.append(box);
      doc.append(screen);
      return;
    }
    const spin = el('div', {
      width: '28px',
      height: '28px',
      margin: '0 auto 14px',
      border: '3px solid rgba(31,58,42,.2)',
      borderTopColor: '#1f3a2a',
      borderRadius: '50%',
    });
    spin.animate([{ transform: 'rotate(0)' }, { transform: 'rotate(360deg)' }], { duration: 900, iterations: Infinity });
    spin.id = 'boot-spin';
    box.append(logo, spin, el('div', { fontWeight: '600' }, 'Loading DumpGuard...'));
    screen.append(box);
    doc.append(screen);
  };

  const showError = (title, detail) => {
    if (done) return;
    if (detail) failures.push(detail);
    if (!screen) build();
    failed = true;
    screen.style.opacity = '1';
    box.replaceChildren();
    const info = el('div', {
      margin: '16px 0',
      padding: '10px 12px',
      background: 'rgba(31,58,42,.08)',
      borderRadius: '8px',
      font: '12px/1.4 ui-monospace, Menlo, monospace',
      textAlign: 'left',
      wordBreak: 'break-word',
      maxHeight: '35vh',
      overflow: 'auto',
    }, failures.join('\n') || 'No details available');
    info.style.whiteSpace = 'pre-wrap';
    const row = el('div', {});
    row.append(button('Reload', () => location.reload(), true), button('Clear saved data and reload', resetAndReload, false));
    box.append(el('div', { fontWeight: '600', fontSize: '18px' }, title), info, row);
  };

  const hide = () => {
    if (!screen || failed) return;
    const wait = intro ? MIN_INTRO - (Date.now() - started) : 0;
    if (wait > 0) return setTimeout(hide, wait);
    done = true;
    try {
      localStorage.setItem('dg-seen', '1');
    } catch {}
    screen.style.opacity = '0';
    setTimeout(() => screen.remove(), 300);
  };

  build();

  window.addEventListener('error', e => {
    if (e.target && e.target !== window) {
      const tag = e.target.tagName;
      if (tag !== 'SCRIPT' && tag !== 'LINK') return;
      const url = e.target.src || e.target.href || '';
      if (!url || /fonts\.(googleapis|gstatic)\.com/.test(url)) return;
      showError('Something did not load', 'Could not load ' + url);
      return;
    }
    showError('Something went wrong', (e.message || 'Script error') + (e.filename ? '\n' + e.filename.split('/').slice(-2).join('/') + ':' + e.lineno : ''));
  }, true);

  window.addEventListener('unhandledrejection', e => {
    const r = e.reason;
    showError('Something went wrong', String((r && (r.stack || r.message)) || r));
  });

  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
      if (failed) return;
      if (doc.classList.contains('gated') || document.querySelector('.view.on')) return hide();
      showError('DumpGuard did not start', 'No page was shown after loading.');
    }, 400);
  });

  setTimeout(() => {
    if (!screen || !screen.isConnected || failed) return;
    box.append(el('div', { marginTop: '12px', fontSize: '14px', opacity: '.8' }, 'This is taking longer than usual.'));
    const row = el('div', { marginTop: '8px' });
    row.append(button('Reload', () => location.reload(), true), button('Clear saved data and reload', resetAndReload, false));
    box.append(row);
  }, 12000);

  const fonts = document.createElement('link');
  fonts.rel = 'stylesheet';
  fonts.href = 'https://fonts.googleapis.com/css2?family=Belleza&family=Inter:wght@300;400;600&display=swap';
  document.head.append(fonts);
})();
