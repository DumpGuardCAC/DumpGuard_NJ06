(() => {
  'use strict';

  const TFJS = 'lib/tf.min.js';
  const MODEL_URL = 'lib/model.json';
  const CLASSES = ['rigid_plastic', 'soft_plastic_foam', 'cardboard_paper', 'metal', 'glass', 'ewaste_hazard', 'no_object'];
  const SIZE = 224;
  const MAX_ZOOM = 4;
  const ZOOM_STEPS = [1, 2, 3];
  const TEMPERATURE = 1.4;
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

  const drawBox = (source, b) => frameCtx.drawImage(source, b.x, b.y, b.s, b.s, 0, 0, SIZE, SIZE);

  const scoreBoxes = async (source, boxes) => {
    const model = await loadModel();
    const { tf } = window;
    const out = tf.tidy(() => {
      const batch = boxes.map(b => {
        drawBox(source, b);
        return tf.browser.fromPixels(frame).toFloat();
      });
      return model.predict(tf.stack(batch));
    });
    const data = await out.data();
    out.dispose();
    return boxes.map((_, i) => calibrate(Array.from(data.slice(i * CLASSES.length, (i + 1) * CLASSES.length)), TEMPERATURE));
  };

  const objectScore = p => Math.max(...p.filter((_, i) => CLASSES[i] !== 'no_object'));

  const overlap = (a, b) => {
    const w = Math.min(a.x + a.s, b.x + b.s) - Math.max(a.x, b.x);
    const d = Math.min(a.y + a.s, b.y + b.s) - Math.max(a.y, b.y);
    if (w <= 0 || d <= 0) return 0;
    return (w * d) / (a.s * a.s + b.s * b.s - w * d);
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
        note.textContent = `${str('sure')}: ${DG.material(r.cls)} (${pct(r.confidence)}). ${str('local')}`;
        DG.showMaterial(r.cls);
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
        boxEl.style.width = boxEl.style.height = `${lastBox.s * k}px`;
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
        if (lastBox) drawBox(video, lastBox);
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
        let delay = 120;
        try {
          if (video.videoWidth && overlay.clientWidth) {
            const boxes = candidates();
            const probs = await scoreBoxes(video, boxes);
            if (!alive) return;
            const scores = probs.map(objectScore);
            const best = Math.max(...scores);
            const near = scores.map((_, i) => i).filter(i => scores[i] >= best - 0.08);
            const pick = near.sort((a, b) => boxes[a].s - boxes[b].s || scores[b] - scores[a])[0];
            const box = boxes[pick];
            const jumped = !lastBox || overlap(lastBox, box) < 0.4;
            smooth = smooth && !jumped ? smooth.map((v, i) => 0.6 * v + 0.4 * probs[pick][i]) : probs[pick];
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
        if (alive) setTimeout(tick, delay);
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
