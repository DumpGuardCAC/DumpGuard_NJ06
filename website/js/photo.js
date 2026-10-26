(() => {
  'use strict';

  const TFJS = 'lib/tf.min.js';
  const MODEL_URL = 'lib/model.json';
  const CLASSES = ['rigid_plastic', 'soft_plastic_foam', 'cardboard_paper', 'metal', 'glass', 'ewaste_hazard', 'no_object'];
  const SIZE = 224;
  const MAX_ZOOM = 4;
  const ZOOM_STEPS = [1, 2, 3];
  const TEMPERATURE = 1.4;
  const TICK_MS = 200;
  const THRESHOLD = 0.55;
  const HAZARD_THRESHOLD = 0.75;

  const S = {
    en: {
      scan: 'Scan with camera', upload: 'Or upload a photo', looking: 'Looking at the photo...',
      sure: 'Looks like', unsure: 'Not sure. Tap the closest match.', none: 'No item found. Try getting closer.',
      fail: 'Photo recognition could not start. Pick a category below.', local: 'The photo stays on your device.',
      use: 'Use this', close: 'Close', hint: 'Point at one item',
      camFail: 'The camera is not available. Allow camera access or upload a photo.',
    },
  };
  const str = key => (S[window.DumpGuard.lang()] || S.en)[key];

  let tfPromise = null;
  let modelPromise = null;
  const loadScript = src => new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    script.crossOrigin = 'anonymous';
    script.integrity = 'sha384-L8voclkoniuFcRcupWcIj6Z2X9BjaujQTgwjRJl5LjC7tJ/By8Kkl+nf64+2IVjS';
    script.onload = resolve;
    script.onerror = () => reject(new Error('script'));
    document.head.appendChild(script);
  });
  const loadModel = () => {
    modelPromise ||= (async () => {
      try {
        if (!window.tf) await (tfPromise ||= loadScript(TFJS));
        const { tf } = window;
        await tf.ready();
        if (tf.getBackend() !== 'webgl') await tf.setBackend('webgl').catch(() => {});
        const model = await tf.loadGraphModel(MODEL_URL);
        const warmup = tf.tidy(() => model.predict(tf.zeros([1, SIZE, SIZE, 3])));
        await warmup.data();
        warmup.dispose();
        return model;
      } catch (e) {
        modelPromise = null;
        tfPromise = null;
        throw e;
      }
    })();
    return modelPromise;
  };

  const calibrate = (probs, temperature) => {
    const logits = probs.map(p => Math.log(Math.max(p, 1e-9)) / temperature);
    const max = Math.max(...logits);
    const exps = logits.map(l => Math.exp(l - max));
    const sum = exps.reduce((a, b) => a + b, 0);
    return exps.map(e => e / sum);
  };
  const PLASTICS = ['rigid_plastic', 'soft_plastic_foam'];
  const summarize = p => {
    const scores = {};
    CLASSES.forEach((c, i) => {
      const key = PLASTICS.includes(c) ? 'plastic' : c;
      scores[key] = (scores[key] || 0) + p[i];
    });
    const ranked = Object.entries(scores).sort((a, b) => b[1] - a[1]);
    const [cls, confidence] = ranked[0];
    const top = ranked.filter(([c]) => c !== 'no_object').slice(0, 3).map(([c, v]) => ({ cls: c, p: v }));
    return { cls, confidence, sure: confidence >= (cls === 'ewaste_hazard' ? HAZARD_THRESHOLD : THRESHOLD), top };
  };

  const frame = document.createElement('canvas');
  frame.width = SIZE;
  frame.height = SIZE;
  const frameCtx = frame.getContext('2d', { willReadFrequently: false });

  const scoreSource = async (source, w, h, size = Math.min(w, h)) => {
    const model = await loadModel();
    const { tf } = window;
    frameCtx.drawImage(source, (w - size) / 2, (h - size) / 2, size, size, 0, 0, SIZE, SIZE);
    const out = tf.tidy(() => model.predict(tf.browser.fromPixels(frame).toFloat().expandDims(0)));
    const data = await out.data();
    out.dispose();
    return calibrate(Array.from(data), TEMPERATURE);
  };

  const drawBox = (source, b) => frameCtx.drawImage(source, b.x, b.y, b.w, b.h, 0, 0, SIZE, SIZE);

  const BATCH = 8;
  const scoreBoxes = async (source, boxes) => {
    const model = await loadModel();
    const { tf } = window;
    const probs = [];
    for (let i = 0; i < boxes.length; i += BATCH) {
      const part = boxes.slice(i, i + BATCH);
      const out = tf.tidy(() => {
        const batch = part.map(b => {
          drawBox(source, b);
          return tf.browser.fromPixels(frame).toFloat();
        });
        return model.predict(tf.stack(batch));
      });
      const data = await out.data();
      out.dispose();
      part.forEach((_, j) => probs.push(calibrate(Array.from(data.slice(j * CLASSES.length, (j + 1) * CLASSES.length)), TEMPERATURE)));
    }
    return probs;
  };

  const objectScore = p => Math.max(...p.filter((_, i) => CLASSES[i] !== 'no_object'));

  const overlap = (a, b) => {
    const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
    const d = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
    if (w <= 0 || d <= 0) return 0;
    return (w * d) / (a.w * a.h + b.w * b.h - w * d);
  };

  const PROBE = 64;
  const probe = document.createElement('canvas');
  const probeCtx = probe.getContext('2d', { willReadFrequently: true });

  const otsu = (vals, bins, max) => {
    const hist = new Array(bins).fill(0);
    vals.forEach(v => { hist[Math.min(bins - 1, Math.floor((v / max) * bins))]++; });
    let sum = 0;
    hist.forEach((c, i) => { sum += i * c; });
    let wb = 0;
    let sb = 0;
    let bestVar = -1;
    let cut = 0;
    for (let i = 0; i < bins; i++) {
      wb += hist[i];
      if (!wb) continue;
      const wf = vals.length - wb;
      if (!wf) break;
      sb += i * hist[i];
      const v = wb * wf * (sb / wb - (sum - sb) / wf) ** 2;
      if (v > bestVar) { bestVar = v; cut = i; }
    }
    return ((cut + 1) / bins) * max;
  };

  const tighten = (source, box, vw, vh) => {
    const pad = 0.35;
    const ex = Math.max(0, box.x - box.w * pad);
    const ey = Math.max(0, box.y - box.h * pad);
    const ew = Math.min(vw, box.x + box.w * (1 + pad)) - ex;
    const eh = Math.min(vh, box.y + box.h * (1 + pad)) - ey;
    const sc = PROBE / Math.max(ew, eh);
    const pw = Math.max(8, Math.round(ew * sc));
    const ph = Math.max(8, Math.round(eh * sc));
    probe.width = pw;
    probe.height = ph;
    probeCtx.drawImage(source, ex, ey, ew, eh, 0, 0, pw, ph);
    const px = probeCtx.getImageData(0, 0, pw, ph).data;
    const ring = [[], [], []];
    for (let y = 0; y < ph; y++) {
      for (let x = 0; x < pw; x++) {
        if (x > 1 && y > 1 && x < pw - 2 && y < ph - 2) continue;
        const i = (y * pw + x) * 4;
        for (let c = 0; c < 3; c++) ring[c].push(px[i + c]);
      }
    }
    const bg = ring.map(r => r.sort((a, b) => a - b)[r.length >> 1]);
    const diff = new Float32Array(pw * ph);
    let top = 0;
    for (let i = 0; i < diff.length; i++) {
      const d = Math.hypot(px[i * 4] - bg[0], px[i * 4 + 1] - bg[1], px[i * 4 + 2] - bg[2]);
      diff[i] = d;
      if (d > top) top = d;
    }
    if (top < 40) return null;
    const cut = Math.max(22, otsu(diff, 64, top));
    const ox0 = (box.x - ex) * sc;
    const oy0 = (box.y - ey) * sc;
    const ox1 = ox0 + box.w * sc;
    const oy1 = oy0 + box.h * sc;
    const seen = new Uint8Array(diff.length);
    let found = null;
    let foundScore = 0;
    for (let start = 0; start < diff.length; start++) {
      if (seen[start] || diff[start] <= cut) continue;
      const stack = [start];
      seen[start] = 1;
      let area = 0;
      let inside = 0;
      let x0 = pw;
      let y0 = ph;
      let x1 = 0;
      let y1 = 0;
      while (stack.length) {
        const i = stack.pop();
        const x = i % pw;
        const y = (i - x) / pw;
        area++;
        if (x >= ox0 && x < ox1 && y >= oy0 && y < oy1) inside++;
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
        if (x > 0 && !seen[i - 1] && diff[i - 1] > cut) { seen[i - 1] = 1; stack.push(i - 1); }
        if (x < pw - 1 && !seen[i + 1] && diff[i + 1] > cut) { seen[i + 1] = 1; stack.push(i + 1); }
        if (y > 0 && !seen[i - pw] && diff[i - pw] > cut) { seen[i - pw] = 1; stack.push(i - pw); }
        if (y < ph - 1 && !seen[i + pw] && diff[i + pw] > cut) { seen[i + pw] = 1; stack.push(i + pw); }
      }
      if (inside > foundScore) { foundScore = inside; found = { x0, y0, x1, y1 }; }
    }
    if (!found) return null;
    const clipped = (found.x0 <= 0 && ex > 0) || (found.y0 <= 0 && ey > 0) || (found.x1 >= pw - 1 && ex + ew < vw) || (found.y1 >= ph - 1 && ey + eh < vh);
    if (clipped) {
      const cx = box.x + box.w / 2;
      const cy = box.y + box.h / 2;
      const gw = Math.min(vw, box.w * 1.6);
      const gh = Math.min(vh, box.h * 1.6);
      const gx = Math.min(Math.max(0, cx - gw / 2), vw - gw);
      const gy = Math.min(Math.max(0, cy - gh / 2), vh - gh);
      return { x: gx, y: gy, w: gw, h: gh };
    }
    const grow = 0.5;
    const w = (found.x1 - found.x0 + 1 + grow * 2) / sc;
    const h = (found.y1 - found.y0 + 1 + grow * 2) / sc;
    const fit = {
      x: Math.max(0, ex + (found.x0 - grow) / sc),
      y: Math.max(0, ey + (found.y0 - grow) / sc),
      w,
      h,
    };
    fit.w = Math.min(fit.w, vw - fit.x);
    fit.h = Math.min(fit.h, vh - fit.y);
    const ratio = (fit.w * fit.h) / (box.w * box.h);
    return ratio > 0.12 && ratio < 4 ? fit : null;
  };

  const RECTS = [[1, 0.75], [0.75, 1], [0.85, 0.55], [0.55, 0.85], [0.7, 0.7], [1, 0.5]];
  const refinements = sq => {
    const out = [];
    for (const [fw, fh] of RECTS) {
      const w = sq.w * fw;
      const h = sq.h * fh;
      const nx = sq.w - w > sq.w * 0.2 ? 3 : 1;
      const ny = sq.h - h > sq.h * 0.2 ? 3 : 1;
      for (let i = 0; i < nx; i++) {
        for (let j = 0; j < ny; j++) {
          out.push({
            x: sq.x + (nx === 1 ? (sq.w - w) / 2 : ((sq.w - w) * i) / (nx - 1)),
            y: sq.y + (ny === 1 ? (sq.h - h) / 2 : ((sq.h - h) * j) / (ny - 1)),
            w,
            h,
          });
        }
      }
    }
    return out;
  };

  const init = () => {
    const input = document.getElementById('photo');
    const label = document.getElementById('droptxt');
    if (!input || !label || !window.DumpGuard) return;
    const DG = window.DumpGuard;
    const { h } = DG;
    let mine = 0;

    const note = h('p', { class: 'sm', 'aria-live': 'polite' });
    const chipsBox = h('div', { class: 'chips' });
    const camera = h('input', { type: 'file', accept: 'image/*', capture: 'environment', hidden: '' });
    const scanBtn = h('button', { class: 'btn dark full', type: 'button' }, str('scan'));
    const dropLabel = input.parentNode;

    input.removeAttribute('capture');
    dropLabel.parentNode.insertBefore(scanBtn, dropLabel);
    dropLabel.parentNode.insertBefore(camera, dropLabel);
    dropLabel.parentNode.insertBefore(note, dropLabel.nextSibling);
    dropLabel.parentNode.insertBefore(chipsBox, note.nextSibling);
    label.textContent = str('upload');

    const pct = p => `${Math.round(p * 100)}%`;
    const renderChips = (box, top, onChoose, active) => {
      box.replaceChildren(...top.map(c => {
        const chip = h('button', { class: 'chip', type: 'button', 'data-cls': c.cls, 'aria-pressed': String(c.cls === active) }, `${DG.material(c.cls)} ${pct(c.p)}`);
        chip.addEventListener('click', () => onChoose(c.cls));
        return chip;
      }));
    };
    const showChips = (r, active) => renderChips(chipsBox, r.top, cls => {
      chipsBox.querySelectorAll('.chip').forEach(chip => chip.setAttribute('aria-pressed', String(chip.dataset.cls === cls)));
      DG.showMaterial(cls);
    }, active);

    const finish = r => {
      chipsBox.replaceChildren();
      if (r.cls === 'no_object') {
        note.textContent = str('none');
        return;
      }
      if (r.sure) {
        note.textContent = `${DG.material(r.cls)}. ${str('local')}`;
        DG.showMaterial(r.cls);
        return;
      } else {
        note.textContent = str('unsure');
      }
      showChips(r, r.sure ? r.cls : '');
    };

    const openCamera = async () => {
      if (!navigator.mediaDevices?.getUserMedia) return camera.click();
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } }, audio: false });
      } catch {
        note.className = 'err';
        note.textContent = str('camFail');
        return;
      }
      note.className = 'sm';
      note.textContent = '';
      const video = h('video', { playsinline: '', autoplay: '' });
      video.muted = true;
      video.srcObject = stream;
      video.play().catch(() => {});
      const live = h('div', { class: 'cam-chips', 'aria-live': 'polite' });
      const useBtn = h('button', { class: 'cam-use', type: 'button', disabled: '' }, str('use'));
      const closeBtn = h('button', { class: 'cam-close', type: 'button' }, str('close'));
      const tag = h('span', {});
      const boxEl = h('div', { class: 'cam-box idle' }, tag);
      const zoomBtns = ZOOM_STEPS.map(z => {
        const btn = h('button', { class: 'cam-z', type: 'button', 'aria-label': `${z}x` }, `${z}x`);
        btn.addEventListener('click', () => setZoom(z, true));
        return btn;
      });
      const overlay = h('div', { class: 'cam', role: 'dialog', 'aria-modal': 'true', 'aria-label': str('scan') },
        video, boxEl,
        h('div', { class: 'cam-top' }, closeBtn, h('span', {}, str('hint'))),
        h('div', { class: 'cam-bottom' }, h('div', { class: 'cam-zoom' }, ...zoomBtns), live, useBtn));
      let alive = true;
      let zoom = 1;
      let smooth = null;
      let last = null;
      let lastBox = null;
      let square = null;

      const geometry = () => {
        const vw = video.videoWidth;
        const vh = video.videoHeight;
        const cw = overlay.clientWidth;
        const ch = overlay.clientHeight;
        return { vw, vh, cw, ch, k: Math.max(cw / vw, ch / vh) * zoom };
      };
      const placeBox = () => {
        if (!lastBox || !video.videoWidth) return;
        const { vw, vh, cw, ch, k } = geometry();
        boxEl.style.width = `${lastBox.w * k}px`;
        boxEl.style.height = `${lastBox.h * k}px`;
        boxEl.style.transform = `translate(${cw / 2 + (lastBox.x - vw / 2) * k}px, ${ch / 2 + (lastBox.y - vh / 2) * k}px)`;
      };
      const setZoom = (z, eased) => {
        zoom = Math.min(MAX_ZOOM, Math.max(1, z));
        video.style.transition = eased ? 'transform .25s ease' : 'none';
        video.style.transform = `scale(${zoom})`;
        zoomBtns.forEach((btn, i) => btn.setAttribute('aria-pressed', String(Math.abs(ZOOM_STEPS[i] - zoom) < 0.3)));
        smooth = null;
        placeBox();
      };
      const candidates = () => {
        const { vw, vh, cw, ch, k } = geometry();
        const W = Math.min(cw / k, vw);
        const H = Math.min(ch / k, vh);
        const m = Math.min(W, H);
        const aw = Math.min(W, m * 1.2);
        const ah = Math.min(H, m * 1.2);
        const out = [];
        for (const f of [0.5, 0.75, 1]) {
          const s = m * f;
          const nx = Math.max(1, Math.ceil((aw - s) / (s / 2)) + 1);
          const ny = Math.max(1, Math.ceil((ah - s) / (s / 2)) + 1);
          for (let i = 0; i < nx; i++) {
            for (let j = 0; j < ny; j++) {
              out.push({
                x: vw / 2 - aw / 2 + (nx === 1 ? (aw - s) / 2 : ((aw - s) * i) / (nx - 1)),
                y: vh / 2 - ah / 2 + (ny === 1 ? (ah - s) / 2 : ((ah - s) * j) / (ny - 1)),
                s,
                w: s,
                h: s,
              });
            }
          }
        }
        return out;
      };

      const pointers = new Map();
      let pinchBase = 0;
      const spread = () => {
        const [a, b] = [...pointers.values()];
        return Math.hypot(a.x - b.x, a.y - b.y);
      };
      overlay.addEventListener('pointerdown', e => {
        if (e.target.closest('button')) return;
        pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (pointers.size === 2) pinchBase = spread() / zoom;
      });
      overlay.addEventListener('pointermove', e => {
        if (!pointers.has(e.pointerId)) return;
        pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (pointers.size === 2 && pinchBase) setZoom(spread() / pinchBase, false);
      });
      const release = e => {
        pointers.delete(e.pointerId);
        pinchBase = 0;
      };
      overlay.addEventListener('pointerup', release);
      overlay.addEventListener('pointercancel', release);
      overlay.addEventListener('wheel', e => {
        e.preventDefault();
        setZoom(zoom * Math.exp(-e.deltaY * 0.002), false);
      }, { passive: false });

      const onKey = e => { if (e.key === 'Escape') stop(); };
      const onHide = () => { if (document.hidden) stop(); };
      const stop = () => {
        alive = false;
        stream.getTracks().forEach(track => track.stop());
        overlay.remove();
        document.documentElement.classList.remove('cam-on');
        document.removeEventListener('keydown', onKey);
        document.removeEventListener('visibilitychange', onHide);
      };
      const accept = cls => {
        const r = last;
        if (square) drawBox(video, square);
        DG.clear(label).appendChild(h('img', { src: frame.toDataURL('image/jpeg', 0.85), alt: '' }));
        stop();
        note.textContent = `${str('sure')}: ${DG.material(cls)} (${pct(r.top.find(c => c.cls === cls).p)}). ${str('local')}`;
        showChips(r, cls);
        DG.showMaterial(cls);
      };
      closeBtn.addEventListener('click', stop);
      useBtn.addEventListener('click', () => {
        if (last && last.cls !== 'no_object') accept(last.top[0].cls);
      });
      document.addEventListener('keydown', onKey);
      document.addEventListener('visibilitychange', onHide);
      document.documentElement.classList.add('cam-on');
      document.body.appendChild(overlay);
      setZoom(1, false);
      closeBtn.focus();

      const tick = async () => {
        if (!alive) return;
        const started = performance.now();
        let delay = 0;
        try {
          if (video.videoWidth && overlay.clientWidth) {
            const boxes = candidates();
            const probs = await scoreBoxes(video, boxes);
            if (!alive) return;
            const scores = probs.map(objectScore);
            const best = Math.max(...scores);
            const near = scores.map((_, i) => i).filter(i => scores[i] >= best - 0.08);
            const pick = near.sort((a, b) => boxes[a].s - boxes[b].s || scores[b] - scores[a])[0];
            let box = boxes[pick];
            let chosen = probs[pick];
            let top = scores[pick];
            const tight = refinements(box);
            const tightProbs = await scoreBoxes(video, tight);
            if (!alive) return;
            tight.forEach((t, i) => {
              const sc = objectScore(tightProbs[i]);
              if (sc >= top - 0.06 && t.w * t.h < box.w * box.h) {
                box = t;
                chosen = tightProbs[i];
                top = Math.max(top, sc);
              }
            });
            square = boxes[pick];
            let fit = null;
            for (let pass = 0, from = square; pass < 5; pass++) {
              const next = tighten(video, from, video.videoWidth, video.videoHeight);
              if (!next) break;
              const change = Math.abs(next.w * next.h - from.w * from.h) / (from.w * from.h);
              fit = next;
              from = next;
              if (change < 0.08) break;
            }
            if (fit) box = fit;
            const jumped = !lastBox || overlap(lastBox, box) < 0.4;
            if (!jumped) box = { x: (lastBox.x + box.x) / 2, y: (lastBox.y + box.y) / 2, w: (lastBox.w + box.w) / 2, h: (lastBox.h + box.h) / 2 };
            smooth = smooth && !jumped ? smooth.map((v, i) => 0.6 * v + 0.4 * chosen[i]) : chosen;
            lastBox = box;
            last = summarize(smooth);
            const idle = last.cls === 'no_object' || best < 0.35;
            boxEl.classList.toggle('idle', idle);
            placeBox();
            if (idle) {
              tag.textContent = '';
              live.textContent = str('none');
              useBtn.disabled = true;
            } else {
              tag.textContent = `${DG.material(last.top[0].cls)} ${pct(last.top[0].p)}`;
              renderChips(live, last.top, accept, last.top[0].cls);
              useBtn.disabled = false;
            }
          }
        } catch {
          live.textContent = str('fail');
          delay = 2000;
        }
        if (alive) setTimeout(tick, Math.max(delay, TICK_MS - (performance.now() - started)));
      };
      tick();
    };
    scanBtn.addEventListener('click', openCamera);

    const onPick = source => () => {
      const file = source.files?.[0];
      if (!file) return;
      const run = ++mine;
      DG.showCategoryPicker(false);
      note.className = 'sm';
      note.textContent = str('looking');
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onerror = () => {
        URL.revokeObjectURL(url);
        note.textContent = str('fail');
        DG.showCategoryPicker(true);
      };
      img.onload = async () => {
        if (run !== mine) return;
        DG.clear(label).appendChild(h('img', { src: url, alt: '' }));
        try {
          const r = summarize(await scoreSource(img, img.naturalWidth, img.naturalHeight));
          if (run !== mine) return;
          finish(r);
        } catch {
          if (run !== mine) return;
          note.className = 'err';
          note.textContent = str('fail');
          DG.showCategoryPicker(true);
        }
      };
      img.src = url;
      source.value = '';
    };
    input.addEventListener('change', onPick(input));
    camera.addEventListener('change', onPick(camera));

    const warm = () => loadModel().catch(() => {});
    if (navigator.connection?.saveData) return;
    warm();
  };

  esReady.then(es => {
    S.es = es.photo ?? S.en;
    init();
  });
})();
