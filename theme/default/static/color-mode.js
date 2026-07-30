(() => {
  const toggle = document.getElementById('color-mode-toggle');
  if (!toggle) return;

  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const savedMode = () => {
    try {
      return localStorage.getItem('alive.colorMode');
    } catch (error) {
      return null;
    }
  };

  function applyMode(mode, persist = false) {
    const normalized = mode === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.colorMode = normalized;
    document.documentElement.style.colorScheme = normalized;
    const dark = normalized === 'dark';
    toggle.setAttribute('aria-pressed', String(dark));
    toggle.setAttribute('aria-label', dark ? '切换为浅色模式' : '切换为深色模式');
    toggle.title = dark ? '当前为深色，点击切换为浅色' : '当前为浅色，点击切换为深色';
    if (persist) {
      try {
        localStorage.setItem('alive.colorMode', normalized);
      } catch (error) {
        // Storage may be unavailable in strict privacy modes; the current page
        // still switches correctly without persistence.
      }
    }
  }

  toggle.addEventListener('click', () => {
    applyMode(
      document.documentElement.dataset.colorMode === 'dark' ? 'light' : 'dark',
      true,
    );
  });

  media.addEventListener('change', (event) => {
    if (!savedMode()) applyMode(event.matches ? 'dark' : 'light');
  });

  applyMode(document.documentElement.dataset.colorMode || (media.matches ? 'dark' : 'light'));
})();
