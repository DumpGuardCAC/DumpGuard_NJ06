(() => {
  'use strict';

  const TFJS = 'lib/tf.min.js';
  const MODEL_URL = 'lib/model.json';
  const CLASSES = ['rigid_plastic', 'soft_plastic_foam', 'cardboard_paper', 'metal', 'glass', 'ewaste_hazard', 'no_object'];
  const SIZE = 224;
  const TEMPERATURE = 1.9;
  const THRESHOLD = 0.65;
  const SMOOTHING = 0.6;
  const LOCK_FRAMES = 4;
  const SCAN_LIMIT_MS = 25000;

  const S = {
    en: {
      scan: 'Scan with camera', stop: 'Stop', upload: 'Or upload a photo',
      reading: 'Getting the camera ready...', hold: 'Hold the camera close to the item', looking: 'Looking at the photo...',
      sure: 'Looks like', unsure: 'Not sure what this is. Pick a category below.', none: 'No item found. Try getting closer, or pick a category below.',
      fail: 'Photo recognition could not start. Pick a category below.', nocam: 'The camera is not available. Allow camera access, or upload a photo.',
      local: 'The photo stays on your device.',
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
        tf.tidy(() => model.predict(tf.zeros([1, SIZE, SIZE, 3])).dataSync());
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
  const decide = probs => {
    const p = calibrate(probs, TEMPERATURE);
    const best = p.indexOf(Math.max(...p));
    return { cls: CLASSES[best], confidence: p[best], sure: p[best] >= THRESHOLD };
  };

  const frame = document.createElement('canvas');
  frame.width = SIZE;
  frame.height = SIZE;
  const frameCtx = frame.getContext('2d', { willReadFrequently: false });

  const predict = async model => {
    const { tf } = window;
    const out = tf.tidy(() => model.predict(tf.browser.fromPixels(frame).toFloat().expandDims(0)));
    const data = await out.data();
    out.dispose();
    return Array.from(data);
  };

  const classifyImage = async img => {
    const model = await loadModel();
    frameCtx.drawImage(img, 0, 0, SIZE, SIZE);
    return decide(await predict(model));
  };

  const init = () => {
    const input = document.getElementById('photo');
    const label = document.getElementById('droptxt');
    if (!input || !label || !window.DumpGuard) return;
    const DG = window.DumpGuard;
    const { h } = DG;
    let mine = 0;
    let scanning = false;
    let stream = null;

    const note = h('p', { class: 'sm', 'aria-live': 'polite' });
    const video = h('video', { playsinline: '', muted: '', autoplay: '', 'aria-hidden': 'true' });
    video.muted = true;
    const status = h('p', { class: 'scan-status' });
    const scanBtn = h('button', { class: 'btn dark full', type: 'button' }, str('scan'));
    const viewer = h('div', { class: 'scan', hidden: '' }, video, h('div', { class: 'scan-frame' }), status);
    const dropLabel = input.parentNode;

    dropLabel.parentNode.insertBefore(scanBtn, dropLabel);
    dropLabel.parentNode.insertBefore(viewer, dropLabel);
    dropLabel.parentNode.insertBefore(note, dropLabel.nextSibling);
    label.textContent = str('upload');

    const stopCamera = () => {
      scanning = false;
      if (stream) stream.getTracks().forEach(t => t.stop());
      stream = null;
      video.srcObject = null;
      viewer.hidden = true;
      scanBtn.textContent = str('scan');
    };

    const finish = r => {
      stopCamera();
      if (r.cls === 'no_object') {
        note.textContent = str('none');
        DG.showCategoryPicker(true);
      } else if (!r.sure) {
        note.textContent = str('unsure');
        DG.showCategoryPicker(true);
      } else {
        note.textContent = `${str('sure')}: ${DG.material(r.cls)} (${Math.round(r.confidence * 100)}%). ${str('local')}`;
        DG.showMaterial(r.cls);
      }
    };

    const scanLoop = async (model, run) => {
      const started = performance.now();
      let smooth = null;
      let streak = 0;
      let last = null;
      while (scanning && run === mine) {
        if (!document.getElementById('v-identify').classList.contains('on')) return stopCamera();
        const w = video.videoWidth;
        const vh = video.videoHeight;
        if (!w || !vh) {
          await new Promise(requestAnimationFrame);
          continue;
        }
        const side = Math.min(w, vh);
        frameCtx.drawImage(video, (w - side) / 2, (vh - side) / 2, side, side, 0, 0, SIZE, SIZE);
        const probs = await predict(model);
        if (!scanning || run !== mine) return;
        smooth = smooth ? probs.map((p, i) => SMOOTHING * smooth[i] + (1 - SMOOTHING) * p) : probs;
        const r = decide(smooth);
        if (r.cls === 'no_object' || !r.sure) {
          status.textContent = str('hold');
          streak = 0;
        } else {
          status.textContent = `${DG.material(r.cls)} ${Math.round(r.confidence * 100)}%`;
          streak = r.cls === last ? streak + 1 : 1;
        }
        last = r.cls;
        if (streak >= LOCK_FRAMES) return finish(r);
        if (performance.now() - started > SCAN_LIMIT_MS) return finish(r);
      }
    };

    const startScan = async () => {
      const run = ++mine;
      DG.showCategoryPicker(false);
      note.className = 'sm';
      note.textContent = str('reading');
      scanBtn.textContent = str('stop');
      try {
        const [model, media] = await Promise.all([
          loadModel(),
          navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: 'environment' }, width: { ideal: 640 }, height: { ideal: 640 } } }),
        ]);
        if (run !== mine) {
          media.getTracks().forEach(t => t.stop());
          return;
        }
        stream = media;
        video.srcObject = media;
        await video.play();
        viewer.hidden = false;
        scanning = true;
        note.textContent = '';
        status.textContent = str('hold');
        await scanLoop(model, run);
      } catch (e) {
        if (run !== mine) return;
        stopCamera();
        note.className = 'err';
        note.textContent = e && (e.name === 'NotAllowedError' || e.name === 'NotFoundError' || !navigator.mediaDevices) ? str('nocam') : str('fail');
        DG.showCategoryPicker(true);
      }
    };

    scanBtn.addEventListener('click', () => {
      if (scanning || stream) {
        ++mine;
        stopCamera();
        note.textContent = '';
        DG.showCategoryPicker(true);
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        note.className = 'err';
        note.textContent = str('nocam');
        return;
      }
      startScan();
    });

    input.addEventListener('change', () => {
      const file = input.files?.[0];
      if (!file) return;
      const run = ++mine;
      stopCamera();
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
          const r = await classifyImage(img);
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
      input.value = '';
    });

    document.addEventListener('visibilitychange', () => {
      if (document.hidden && (scanning || stream)) {
        ++mine;
        stopCamera();
      }
    });
    document.addEventListener('click', e => {
      if ((scanning || stream) && e.target.closest?.('[data-go]')) {
        ++mine;
        stopCamera();
      }
    });

    const warm = () => loadModel().catch(() => {});
    if (navigator.connection?.saveData) return;
    if ('requestIdleCallback' in window) requestIdleCallback(warm, { timeout: 4000 });
    else setTimeout(warm, 2000);
  };

  esReady.then(es => {
    S.es = es.photo ?? S.en;
    init();
  });
})();
