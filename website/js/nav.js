(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const DG = window.DumpGuard;

  const ALIAS = { about: 'home', login: 'gov', signup: 'home', forgot: 'home', dash: 'home' };

  const ORDER = ['home', 'identify', 'pickup', 'report', 'map', 'gov'];
  const root = document.documentElement;
  const tabs = $('tabs');
  let current = null;
  let frame = 0;

  const edge = () => {
    frame = 0;
    root.style.setProperty('--sp', Math.min(1, window.scrollY / 60).toFixed(3));
  };

  const go = name => {
    const view = ALIAS[name] || name;
    const target = $(`v-${view}`) ? view : 'home';
    root.dataset.dir = current && ORDER.indexOf(target) < ORDER.indexOf(current) ? 'b' : 'f';
    current = target;
    document.querySelectorAll('.view').forEach(e => e.classList.toggle('on', e.id === `v-${target}`));
    document.querySelectorAll('nav a, #tabs a').forEach(a => a.classList.toggle('act', a.getAttribute('data-go') === target));
    try { history.replaceState(null, '', `#${target}`); } catch {}
    window.scrollTo({ top: 0, behavior: 'instant' });
    edge();
    const heading = $(`v-${target}`)?.querySelector('h1, h2');
    if (heading) {
      heading.setAttribute('tabindex', '-1');
      heading.focus({ preventScroll: true });
    }
    navStyle();
    if (target === 'map') setTimeout(() => window.dispatchEvent(new Event('resize')), 60);
  };
  const navStyle = () => {
    const home = $('v-home');
    $('nav').classList.toggle('solid', !(home && home.classList.contains('on')) || window.scrollY > window.innerHeight - 120);
  };
  document.addEventListener('click', e => {
    const link = e.target.closest?.('[data-go]');
    if (!link) return;
    e.preventDefault();
    go(link.getAttribute('data-go'));
  });
  window.addEventListener('scroll', () => {
    navStyle();
    if (!frame) frame = requestAnimationFrame(edge);
  }, { passive: true });
  tabs.addEventListener('pointerdown', () => tabs.classList.add('press'));
  ['pointerup', 'pointercancel', 'pointerleave'].forEach(type => tabs.addEventListener(type, () => tabs.classList.remove('press')));

  const govLogin = async () => {
    const err = $('lerr');
    const user = $('le').value.trim();
    const pw = $('lp').value;
    if (!user || !pw) {
      err.textContent = 'Enter the username and password.';
      return;
    }
    $('lgo').disabled = true;
    const r = await DG.staffLogin(user, pw);
    $('lgo').disabled = false;
    if (!r.ok) {
      err.textContent = r.message;
      return;
    }
    err.textContent = '';
    $('le').value = '';
    $('lp').value = '';
  };
  $('lgo').onclick = govLogin;
  $('lp').addEventListener('keydown', e => { if (e.key === 'Enter') govLogin(); });
  $('le').addEventListener('keydown', e => { if (e.key === 'Enter') $('lp').focus(); });

  go(location.hash.slice(1) || 'home');
})();
