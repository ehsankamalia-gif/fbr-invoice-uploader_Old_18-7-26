(function () {
  const root = document.getElementById("init-progress-root");
  const bar = document.getElementById("init-progress-bar");
  const label = document.getElementById("init-progress-label");
  const a11y = document.getElementById("init-progress-a11y");

  if (!root || !bar || !label || !a11y) {
    return;
  }

  const t0 = performance.now();

  const weights = {
    dom: 0.2,
    render: 0.1,
    load: 0.2,
    fonts: 0.05,
    images: 0.15,
    fetch: 0.25,
    custom: 0.05,
  };

  const state = {
    domDone: document.readyState !== "loading",
    renderDone: false,
    loadDone: document.readyState === "complete",
    fontsDone: false,
    imagesTotal: 0,
    imagesDone: 0,
    fetchInFlight: 0,
    fetchDone: 0,
    customTasks: new Map(),
    error: false,
    progress: 0,
    finished: false,
    updateQueued: false,
    metrics: { initMs: 0 },
  };

  function clamp(n, min, max) {
    return Math.max(min, Math.min(max, n));
  }

  function computeProgress() {
    const dom = state.domDone ? 1 : 0;
    const render = state.renderDone ? 1 : 0;
    const load = state.loadDone ? 1 : 0;
    const fonts = state.fontsDone ? 1 : 0;

    const images =
      state.imagesTotal > 0 ? state.imagesDone / state.imagesTotal : 1;

    const fetchTotalKnown = state.fetchDone + state.fetchInFlight;
    const fetch = fetchTotalKnown > 0 ? state.fetchDone / fetchTotalKnown : 1;

    const customTotal = state.customTasks.size;
    let customDone = 0;
    for (const v of state.customTasks.values()) {
      if (v.status === "done") customDone += 1;
    }
    const custom = customTotal > 0 ? customDone / customTotal : 1;

    const fraction =
      dom * weights.dom +
      render * weights.render +
      load * weights.load +
      fonts * weights.fonts +
      images * weights.images +
      fetch * weights.fetch +
      custom * weights.custom;

    return clamp(Math.round(fraction * 100), 0, 100);
  }

  function applyUI(pct) {
    bar.style.width = pct + "%";
    label.textContent = pct + "%";
    a11y.setAttribute("aria-valuenow", String(pct));
    a11y.textContent = "Loading " + pct + "%";
  }

  function queueUpdate() {
    if (state.updateQueued || state.finished) return;
    state.updateQueued = true;
    requestAnimationFrame(() => {
      state.updateQueued = false;
      const next = computeProgress();
      const monotonic = Math.max(state.progress, next);
      state.progress = monotonic;
      applyUI(state.progress);
      if (state.progress >= 100) finish();
    });
  }

  function finish() {
    if (state.finished) return;
    state.finished = true;
    applyUI(100);
    setTimeout(() => {
      root.style.opacity = "0";
      setTimeout(() => {
        root.style.display = "none";
      }, 250);
    }, 200);
  }

  function markError() {
    if (state.error) return;
    state.error = true;
    root.setAttribute("data-state", "error");
  }

  function trackRender() {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        state.renderDone = true;
        queueUpdate();
      });
    });
  }

  function trackFonts() {
    const fonts = document.fonts;
    if (!fonts || !fonts.ready) {
      state.fontsDone = true;
      queueUpdate();
      return;
    }

    fonts.ready
      .then(() => {
        state.fontsDone = true;
        queueUpdate();
      })
      .catch(() => {
        state.fontsDone = true;
        markError();
        queueUpdate();
      });
  }

  function trackImages() {
    const imgs = Array.from(document.images || []);
    state.imagesTotal = imgs.length;
    state.imagesDone = 0;

    if (state.imagesTotal === 0) {
      queueUpdate();
      return;
    }

    function onDone() {
      state.imagesDone += 1;
      queueUpdate();
    }

    for (const img of imgs) {
      if (img.complete) {
        onDone();
        continue;
      }
      img.addEventListener("load", onDone, { once: true });
      img.addEventListener(
        "error",
        () => {
          markError();
          onDone();
        },
        { once: true }
      );
    }

    queueUpdate();
  }

  function wrapFetch() {
    if (typeof window.fetch !== "function") return;
    if (window.fetch.__initProgressWrapped) return;

    const originalFetch = window.fetch.bind(window);
    const wrapped = function (...args) {
      state.fetchInFlight += 1;
      queueUpdate();
      return originalFetch(...args)
        .then((res) => {
          state.fetchInFlight -= 1;
          state.fetchDone += 1;
          queueUpdate();
          return res;
        })
        .catch((err) => {
          state.fetchInFlight -= 1;
          state.fetchDone += 1;
          markError();
          queueUpdate();
          throw err;
        });
    };

    wrapped.__initProgressWrapped = true;
    window.fetch = wrapped;
  }

  function registerTask(name, promise) {
    if (!name || !promise || typeof promise.then !== "function") return;
    state.customTasks.set(String(name), { status: "pending" });
    queueUpdate();
    promise
      .then(() => {
        state.customTasks.set(String(name), { status: "done" });
        queueUpdate();
      })
      .catch(() => {
        state.customTasks.set(String(name), { status: "done" });
        markError();
        queueUpdate();
      });
  }

  window.__initProgress = {
    registerTask,
    getState: () => ({
      progress: state.progress,
      error: state.error,
      fetchInFlight: state.fetchInFlight,
      fetchDone: state.fetchDone,
      imagesDone: state.imagesDone,
      imagesTotal: state.imagesTotal,
      domDone: state.domDone,
      renderDone: state.renderDone,
      loadDone: state.loadDone,
      fontsDone: state.fontsDone,
      customTasks: state.customTasks.size,
      metrics: state.metrics,
    }),
  };

  applyUI(0);
  wrapFetch();
  trackRender();
  trackFonts();

  if (!state.domDone) {
    document.addEventListener(
      "DOMContentLoaded",
      () => {
        state.domDone = true;
        trackImages();
        queueUpdate();
      },
      { once: true }
    );
  } else {
    trackImages();
  }

  window.addEventListener(
    "load",
    () => {
      state.loadDone = true;
      queueUpdate();
    },
    { once: true }
  );

  if (state.loadDone) {
    queueUpdate();
  }

  setTimeout(() => {
    if (!state.finished) {
      markError();
      finish();
    }
  }, 20000);

  state.metrics.initMs = performance.now() - t0;
  queueUpdate();
})();
