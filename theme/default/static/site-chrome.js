(() => {
  const toggle = document.getElementById('site-menu-toggle');
  const drawer = document.getElementById('site-drawer');
  const closeButton = document.getElementById('site-drawer-close');
  const backdrop = document.getElementById('site-drawer-backdrop');
  if (!toggle || !drawer || !closeButton || !backdrop) return;

  let previousFocus = null;

  function focusableItems() {
    return [...drawer.querySelectorAll('a[href], button:not([disabled])')];
  }

  function setOpen(open) {
    if (open) drawer.inert = false;
    document.body.classList.toggle('site-drawer-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? '关闭更多菜单' : '打开更多菜单');
    drawer.setAttribute('aria-hidden', String(!open));
    if (open) {
      previousFocus = document.activeElement;
      window.setTimeout(() => focusableItems()[0]?.focus(), 30);
    } else if (previousFocus instanceof HTMLElement) {
      previousFocus.focus();
    }
    if (!open) drawer.inert = true;
  }

  toggle.addEventListener('click', () => {
    setOpen(!document.body.classList.contains('site-drawer-open'));
  });
  closeButton.addEventListener('click', () => setOpen(false));
  backdrop.addEventListener('click', () => setOpen(false));
  drawer.querySelectorAll('a[href]').forEach((link) => {
    link.addEventListener('click', () => setOpen(false));
  });

  document.addEventListener('keydown', (event) => {
    if (!document.body.classList.contains('site-drawer-open')) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key !== 'Tab') return;
    const items = focusableItems();
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
})();
