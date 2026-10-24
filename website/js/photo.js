(() => {
  'use strict';

  const TFJS = 'lib/tf.min.js';
  const MODEL_URL = 'lib/model.json';
  const CLASSES = ['rigid_plastic', 'soft_plastic_foam', 'cardboard_paper', 'metal', 'glass', 'ewaste_hazard', 'no_object'];
  const SIZE = 224;
  const TEMPERATURE = 1.9;
  const THRESHOLD = 0.65;

  const S = {
    en: {
      take: 'Take a photo', upload: 'Or upload a photo', looking: 'Looking at the photo...',
      sure: 'Looks like', unsure: 'Not sure what this is. Pick a category below.', none: 'No item found. Try getting closer, or pick a category below.',
      fail: 'Photo recognition could not start. Pick a category below.', local: 'The photo stays on your device.',
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

    const note = h('p', { class: 'sm', 'aria-live': 'polite' });
    const camera = h('input', { type: 'file', accept: 'image/*', capture: 'environment', hidden: '' });
    const takeBtn = h('button', { class: 'btn dark full', type: 'button' }, str('take'));
    const dropLabel = input.parentNode;

    input.removeAttribute('capture');
    dropLabel.parentNode.insertBefore(takeBtn, dropLabel);
    dropLabel.parentNode.insertBefore(camera, dropLabel);
    dropLabel.parentNode.insertBefore(note, dropLabel.nextSibling);
    label.textContent = str('upload');
    takeBtn.addEventListener('click', () => camera.click());

    const finish = r => {
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
