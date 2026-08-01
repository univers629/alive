(() => {
  const body = document.body;
  const background = body?.dataset.pageBackground?.trim();
  if (!body || !background) return;

  const applyBackground = () => {
    const image = new Image();
    image.decoding = 'async';
    image.fetchPriority = 'low';
    image.onload = () => {
      body.style.backgroundImage = `url("${background.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}")`;
      body.style.backgroundPosition = 'center center';
      body.style.backgroundRepeat = 'no-repeat';
      body.style.backgroundSize = 'cover';
      body.style.backgroundAttachment = 'fixed';
      body.classList.add('page-background-ready');
    };
    image.src = background;
  };

  const schedule = () => {
    if ('requestIdleCallback' in window) window.requestIdleCallback(applyBackground, { timeout: 1200 });
    else window.setTimeout(applyBackground, 350);
  };
  if (document.readyState === 'complete') schedule();
  else window.addEventListener('load', schedule, { once: true });
})();
