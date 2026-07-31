(() => {
  const controllers = new WeakMap();
  let openController = null;
  let menuSequence = 0;

  function closeOpenMenu({ restoreFocus = false } = {}) {
    if (!openController) return;
    openController.close(restoreFocus);
  }

  function enhance(select) {
    if (!(select instanceof HTMLSelectElement) || select.multiple || controllers.has(select)) return;

    const measuredWidth = Math.ceil(select.getBoundingClientRect().width);
    const wrapper = document.createElement('span');
    wrapper.className = 'glass-select';
    const originalWidth = select.style.width;
    if (originalWidth) wrapper.style.width = originalWidth;
    else if (measuredWidth > 1) wrapper.style.width = `${measuredWidth}px`;

    const trigger = document.createElement('button');
    trigger.className = 'glass-select__trigger';
    trigger.type = 'button';
    trigger.setAttribute('role', 'combobox');
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');

    const value = document.createElement('span');
    value.className = 'glass-select__value';
    const chevron = document.createElement('span');
    chevron.className = 'glass-select__chevron';
    chevron.setAttribute('aria-hidden', 'true');
    trigger.append(value, chevron);

    const menu = document.createElement('div');
    const menuId = `glass-select-menu-${++menuSequence}`;
    menu.className = 'glass-select__menu';
    menu.id = menuId;
    menu.hidden = true;
    menu.setAttribute('role', 'listbox');
    trigger.setAttribute('aria-controls', menuId);

    select.parentNode.insertBefore(wrapper, select);
    wrapper.append(select, trigger);
    document.body.append(menu);

    function options() {
      return [...select.options];
    }

    function setOptionContent(element, option) {
      element.replaceChildren();
      if (option?.value === 'bilibili') {
        const icon = document.createElement('span');
        icon.className = 'bilibili-tv-icon';
        icon.setAttribute('aria-hidden', 'true');
        const label = document.createElement('span');
        label.textContent = option.textContent;
        element.append(icon, label);
      } else {
        element.textContent = option?.textContent || '';
      }
    }

    function sync() {
      const selected = select.selectedOptions[0] || options()[0];
      setOptionContent(value, selected);
      trigger.disabled = select.disabled;
      trigger.setAttribute('aria-label', select.getAttribute('aria-label') || selected?.textContent || '选择');
      [...menu.children].forEach((item) => {
        item.setAttribute('aria-selected', String(item.dataset.value === select.value));
      });
    }

    function buildMenu() {
      menu.replaceChildren();
      options().forEach((option, index) => {
        const item = document.createElement('button');
        item.className = 'glass-select__option';
        item.type = 'button';
        item.role = 'option';
        item.dataset.value = option.value;
        item.dataset.index = String(index);
        setOptionContent(item, option);
        item.disabled = option.disabled;
        item.setAttribute('aria-selected', String(option.selected));
        item.addEventListener('click', () => {
          if (option.disabled) return;
          select.value = option.value;
          select.dispatchEvent(new Event('change', { bubbles: true }));
          controller.close(true);
        });
        item.addEventListener('keydown', (event) => {
          const items = [...menu.querySelectorAll('.glass-select__option:not(:disabled)')];
          const position = items.indexOf(item);
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            const delta = event.key === 'ArrowDown' ? 1 : -1;
            items[(position + delta + items.length) % items.length]?.focus();
          } else if (event.key === 'Home' || event.key === 'End') {
            event.preventDefault();
            items[event.key === 'Home' ? 0 : items.length - 1]?.focus();
          } else if (event.key === 'Escape' || event.key === 'Tab') {
            if (event.key === 'Escape') event.preventDefault();
            controller.close(event.key === 'Escape');
          }
        });
        menu.append(item);
      });
    }

    function positionMenu() {
      const rect = trigger.getBoundingClientRect();
      const gap = 7;
      const viewportPadding = 8;
      const width = Math.max(rect.width, Math.min(260, window.innerWidth - viewportPadding * 2));
      menu.style.width = `${width}px`;
      menu.style.left = `${Math.min(rect.left, window.innerWidth - width - viewportPadding)}px`;
      menu.hidden = false;
      const menuHeight = menu.offsetHeight;
      const below = window.innerHeight - rect.bottom - gap;
      const top = below >= Math.min(menuHeight, 180)
        ? rect.bottom + gap
        : Math.max(viewportPadding, rect.top - menuHeight - gap);
      menu.style.top = `${top}px`;
    }

    const controller = {
      open(focusOption = false) {
        if (select.disabled) return;
        if (openController && openController !== controller) closeOpenMenu();
        buildMenu();
        positionMenu();
        trigger.setAttribute('aria-expanded', 'true');
        openController = controller;
        if (focusOption) {
          const selected = menu.querySelector('[aria-selected="true"]');
          (selected || menu.querySelector('.glass-select__option:not(:disabled)'))?.focus();
        }
      },
      close(restoreFocus = false) {
        menu.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
        if (openController === controller) openController = null;
        if (restoreFocus) trigger.focus();
      },
      sync,
      destroy() {
        if (openController === controller) openController = null;
        menu.remove();
      },
    };

    controllers.set(select, controller);
    select.addEventListener('change', sync);
    select.addEventListener('focus', () => trigger.focus());
    trigger.addEventListener('click', (event) => {
      event.preventDefault();
      if (trigger.getAttribute('aria-expanded') === 'true') controller.close(true);
      else controller.open();
    });
    trigger.addEventListener('keydown', (event) => {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) {
        event.preventDefault();
        controller.open(true);
      } else if (event.key === 'Escape') {
        controller.close();
      }
    });
    sync();
  }

  function scan(root = document) {
    if (root instanceof HTMLSelectElement) enhance(root);
    root.querySelectorAll?.('select:not([multiple])').forEach(enhance);
  }

  function cleanup(root) {
    if (!(root instanceof Element)) return;
    const removedSelects = root instanceof HTMLSelectElement
      ? [root]
      : [...root.querySelectorAll('select')];
    removedSelects.forEach((select) => {
      if (!select.isConnected) controllers.get(select)?.destroy();
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    scan();
    const observer = new MutationObserver((records) => {
      records.forEach((record) => {
        record.addedNodes.forEach((node) => {
          if (node instanceof Element) scan(node);
        });
        record.removedNodes.forEach(cleanup);
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  });

  document.addEventListener('pointerdown', (event) => {
    if (!openController || event.target.closest('.glass-select__menu, .glass-select__trigger')) return;
    closeOpenMenu();
  });
  window.addEventListener('resize', () => closeOpenMenu());
  window.addEventListener('scroll', (event) => {
    if (event.target instanceof Element && event.target.closest('.glass-select__menu')) return;
    closeOpenMenu();
  }, true);

  window.AliveGlassSelect = {
    enhance,
    sync(select) {
      controllers.get(select)?.sync();
    },
  };
})();
