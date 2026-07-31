(() => {
  const sortSelect = document.getElementById('details-device-sort');
  const deviceList = document.getElementById('details-device-list');
  if (!sortSelect || !deviceList) return;

  const deviceIcons = {
    desktop: '🖥️',
    laptop: '💻',
    phone: '📱',
    tablet: '▣',
    watch: '⌚',
    server: '▤',
    game: '🎮',
     other: '◇',
  };
  const stateLabels = {
    active: '使用中',
    idle: '在线空闲',
    offline: '离线',
  };
  let payload = null;

  function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = String(value);
  }

  function relativeTime(timestamp) {
    const seconds = Math.max(0, Date.now() / 1000 - Number(timestamp || 0));
    if (seconds < 60) return '刚刚更新';
    if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
    return `${Math.floor(seconds / 86400)} 天前`;
  }

  function sortedDevices() {
    const devices = [...(payload?.devices || [])];
    const mode = sortSelect.value;
    const stateRank = { active: 0, idle: 1, offline: 2 };
    if (mode === 'online') {
      devices.sort((left, right) =>
        stateRank[left.public_state] - stateRank[right.public_state]
        || Number(right.last_updated) - Number(left.last_updated));
    } else if (mode === 'updated') {
      devices.sort((left, right) => Number(right.last_updated) - Number(left.last_updated));
    } else if (mode === 'name') {
      devices.sort((left, right) =>
        String(left.show_name || left.id).localeCompare(String(right.show_name || right.id), 'zh-CN'));
    } else {
      devices.sort((left, right) =>
        Number(left.profile?.sort_order || 0) - Number(right.profile?.sort_order || 0)
        || String(left.show_name || left.id).localeCompare(String(right.show_name || right.id), 'zh-CN'));
    }
    return devices;
  }

  function renderDevices() {
    deviceList.replaceChildren();
    const devices = sortedDevices();
    if (!devices.length) {
      const empty = document.createElement('p');
      empty.className = 'details-empty';
      empty.textContent = '还没有公开设备。启动客户端后会显示在这里。';
      deviceList.append(empty);
      return;
    }

    devices.forEach((device) => {
      const row = document.createElement('article');
      row.className = 'details-device-row';

      const icon = document.createElement('span');
      icon.className = 'details-device-icon';
      icon.setAttribute('aria-hidden', 'true');
      if (device.profile?.icon_key === 'bilibili') {
        const bilibiliIcon = document.createElement('span');
        bilibiliIcon.className = 'bilibili-tv-icon';
        icon.append(bilibiliIcon);
      } else {
        icon.textContent = deviceIcons[device.profile?.icon_key] || deviceIcons.other;
      }

      const copy = document.createElement('div');
      copy.className = 'details-device-copy';
      const name = document.createElement('strong');
      name.textContent = device.show_name || device.id;
      const app = document.createElement('span');
      app.textContent = device.status || (device.public_state === 'offline' ? '等待设备重新上线' : '暂无活动');
      copy.append(name, app);

      const state = document.createElement('div');
      state.className = 'details-device-state';
      const stateLine = document.createElement('span');
      const dot = document.createElement('i');
      dot.className = `is-${device.public_state}`;
      stateLine.append(dot, document.createTextNode(stateLabels[device.public_state] || '未知'));
      const updated = document.createElement('time');
      updated.dateTime = new Date(Number(device.last_updated) * 1000).toISOString();
      updated.textContent = relativeTime(device.last_updated);
      state.append(stateLine, updated);

      row.append(icon, copy, state);
      deviceList.append(row);
    });
  }

  function render(nextPayload) {
    payload = nextPayload;
    setText('details-summary', payload.summary);
    setText(
      'details-generated-at',
      new Intl.DateTimeFormat('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      }).format(new Date(Number(payload.generated_at) * 1000)),
    );
    setText('metric-daily', payload.visits.daily);
    setText('metric-weekly', payload.visits.weekly);
    setText('metric-monthly', payload.visits.monthly);
    setText('metric-total', payload.visits.total);
    setText('metric-comments', payload.comments.today);
    setText('metric-comments-total', `历史 ${payload.comments.total} 条`);

    setText('device-active-count', payload.device_counts.active);
    setText('device-idle-count', payload.device_counts.idle);
    setText('device-offline-count', payload.device_counts.offline);
    setText('fact-status', payload.status.name);
    setText('fact-online', `${payload.device_counts.online} / ${payload.device_counts.total}`);
    setText(
      'fact-music',
      payload.music.active
        ? `${payload.music.title} · ${payload.music.artist || '未知艺术家'}`
        : '当前未播放',
    );
    setText('fact-comments', `${payload.comments.total} 条`);
    renderDevices();
  }

  async function refresh() {
    try {
      const response = await fetch('/api/details/query', {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      });
      if (!response.ok) throw new Error('详情读取失败');
      render(await response.json());
    } catch (error) {
      setText('details-summary', '暂时无法读取详情数据，请稍后刷新。');
      deviceList.innerHTML = '<p class="details-empty">详情连接失败。</p>';
    }
  }

  sortSelect.addEventListener('change', renderDevices);
  refresh();
  window.setInterval(() => {
    if (!document.hidden) refresh();
  }, 10000);
})();
