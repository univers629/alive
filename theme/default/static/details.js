(() => {
  const sortSelect = document.getElementById('details-device-sort');
  const deviceList = document.getElementById('details-device-list');
  const activityList = document.getElementById('details-activity-list');
  const appRanking = document.getElementById('details-app-ranking');
  const donut = document.getElementById('details-app-donut');
  const donutLegend = document.getElementById('details-donut-legend');
  const usageBars = document.getElementById('details-usage-bars');
  const periodLabel = document.getElementById('details-activity-period-label');
  const datePickerTrigger = document.getElementById('details-date-picker-trigger');
  const datePickerMenu = document.getElementById('details-date-picker-menu');
  const datePickerGrid = document.getElementById('details-date-picker-grid');
  const datePickerTitle = document.getElementById('details-date-picker-title');
  const activityTabs = [...document.querySelectorAll('[data-activity-category]')];
  const periodTabs = [...document.querySelectorAll('[data-activity-period]')];
  if (!sortSelect || !deviceList || !activityList || !appRanking || !donut || !usageBars) return;

  const deviceIcons = { desktop: '🖥️', laptop: '💻', phone: '📱', tablet: '▣', watch: '⌚', server: '▤', game: '🎮', other: '◇' };
  const stateLabels = { active: '使用中', idle: '在线空闲', offline: '离线' };
  const chartColors = ['#7c5cff', '#28b8f5', '#40d59d', '#ffb75b', '#fa6f9f', '#9a8cff', '#6fcfcd'];
  let payload = null;
  let selectedActivityCategory = 'mobile';
  let selectedPeriod = 'daily';
  let selectedDate = new Date();
  let datePickerLevel = 'year';

  function setText(id, value) { const element = document.getElementById(id); if (element) element.textContent = String(value); }
  function relativeTime(timestamp) {
    const seconds = Math.max(0, Date.now() / 1000 - Number(timestamp || 0));
    if (seconds < 60) return '刚刚更新';
    if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
    return `${Math.floor(seconds / 86400)} 天前`;
  }
  function formatDuration(seconds) {
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    if (total < 60) return total ? '不足 1 分钟' : '0 分钟';
    const hours = Math.floor(total / 3600); const minutes = Math.floor((total % 3600) / 60);
    return hours ? `${hours} 小时${minutes ? ` ${minutes} 分钟` : ''}` : `${minutes} 分钟`;
  }
  function formatActivityTime(timestamp) {
    return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(Number(timestamp) * 1000));
  }
  function apiDate(date) {
    const year = date.getFullYear(); const month = String(date.getMonth() + 1).padStart(2, '0'); const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }
  function earliestActivityDate() { const date = new Date(); date.setHours(0, 0, 0, 0); date.setDate(date.getDate() - 183); return date; }
  function isAvailableDate(date) { const today = new Date(); today.setHours(23, 59, 59, 999); return date >= earliestActivityDate() && date <= today; }
  function monthName(month) { return `${month + 1} 月`; }
  function closeDatePicker() { if (datePickerMenu) datePickerMenu.hidden = true; datePickerTrigger?.setAttribute('aria-expanded', 'false'); }
  function datePickerButton(label, disabled, onClick, selected = false) {
    const button = document.createElement('button'); button.type = 'button'; button.textContent = label; button.disabled = disabled; button.className = selected ? 'is-selected' : '';
    if (!disabled) button.addEventListener('click', (event) => { event.stopPropagation(); onClick(); }); return button;
  }
  function setSelectedYear(year) {
    const month = selectedDate.getMonth(); const day = selectedDate.getDate();
    const lastDay = new Date(year, month + 1, 0).getDate();
    selectedDate = new Date(year, month, Math.min(day, lastDay));
  }
  function setSelectedMonth(month) {
    const year = selectedDate.getFullYear(); const day = selectedDate.getDate();
    const lastDay = new Date(year, month + 1, 0).getDate();
    selectedDate = new Date(year, month, Math.min(day, lastDay));
  }
  function renderDatePicker() {
    if (!datePickerGrid || !datePickerTitle) return;
    datePickerGrid.replaceChildren(); const earliest = earliestActivityDate(); const today = new Date();
    if (datePickerLevel === 'year') {
      datePickerTitle.textContent = '选择年份';
      for (let year = earliest.getFullYear(); year <= today.getFullYear(); year += 1) {
        datePickerGrid.append(datePickerButton(`${year} 年`, false, () => { setSelectedYear(year); datePickerLevel = 'month'; datePickerMenu.hidden = false; renderDatePicker(); }, selectedDate.getFullYear() === year));
      }
    } else if (datePickerLevel === 'month') {
      datePickerTitle.textContent = `${selectedDate.getFullYear()} 年 · 选择月份`;
      for (let month = 0; month < 12; month += 1) {
        const candidate = new Date(selectedDate.getFullYear(), month, 1); const end = new Date(selectedDate.getFullYear(), month + 1, 0, 23, 59, 59);
        datePickerGrid.append(datePickerButton(monthName(month), end < earliest || candidate > today, () => { setSelectedMonth(month); datePickerLevel = 'day'; datePickerMenu.hidden = false; renderDatePicker(); }, selectedDate.getMonth() === month));
      }
    } else {
      datePickerTitle.textContent = `${selectedDate.getFullYear()} 年 ${selectedDate.getMonth() + 1} 月 · 选择日期`;
      const days = new Date(selectedDate.getFullYear(), selectedDate.getMonth() + 1, 0).getDate();
      for (let day = 1; day <= days; day += 1) {
        const candidate = new Date(selectedDate.getFullYear(), selectedDate.getMonth(), day);
        datePickerGrid.append(datePickerButton(String(day), !isAvailableDate(candidate), () => { selectedDate = candidate; closeDatePicker(); refresh(); }, selectedDate.getDate() === day));
      }
    }
  }
  function activityIcon(record, className = 'details-activity-icon') {
    const icon = document.createElement('span');
    icon.className = className; icon.setAttribute('aria-hidden', 'true');
    const fallback = String(record.app_name || '?').trim().slice(0, 1).toUpperCase() || '?';
    if (record.app_icon_url) {
      icon.classList.add('has-image');
      const image = document.createElement('img');
      image.src = record.app_icon_url; image.alt = ''; image.loading = 'lazy'; image.decoding = 'async';
      image.addEventListener('error', () => { image.remove(); icon.classList.remove('has-image'); icon.textContent = fallback; }, { once: true });
      icon.append(image);
    } else icon.textContent = fallback;
    return icon;
  }
  function renderActivities(activity) {
    const records = Array.isArray(activity?.recent) ? activity.recent : [];
    activityList.replaceChildren(); setText('details-activity-record-count', `${records.length} 条`);
    if (!records.length) {
      const empty = document.createElement('p'); empty.className = 'details-empty';
      empty.textContent = selectedActivityCategory === 'mobile' ? '还没有移动设备应用记录。开启无障碍服务后会在这里显示。' : '还没有电脑应用记录。新版桌面客户端开始上报后会在这里显示。';
      activityList.append(empty); return;
    }
    records.forEach((record) => {
      const row = document.createElement('article'); row.className = 'details-activity-row';
      const summary = document.createElement('button'); summary.type = 'button'; summary.className = 'details-activity-summary'; summary.setAttribute('aria-expanded', 'false');
      const copy = document.createElement('div'); copy.className = 'details-activity-copy';
      const name = document.createElement('strong'); name.textContent = record.app_name || '未知应用';
      const source = document.createElement('span'); source.textContent = record.active ? '正在使用 · 点击查看最近事件' : '点击查看最近事件'; copy.append(name, source);
      const meta = document.createElement('div'); meta.className = 'details-activity-meta';
      const duration = document.createElement('strong'); duration.textContent = formatDuration(record.duration_seconds);
      const when = document.createElement('time'); when.dateTime = new Date(Number(record.last_seen_at) * 1000).toISOString();
      when.textContent = record.active ? '使用中' : formatActivityTime(record.last_seen_at); meta.append(duration, when);
      summary.append(activityIcon(record), copy, meta);
      const events = document.createElement('div'); events.className = 'details-activity-events'; events.hidden = true;
      const eventRows = Array.isArray(record.events) ? record.events : [];
      if (!eventRows.length) {
        const empty = document.createElement('span'); empty.textContent = '暂时没有切换或锁屏事件。'; events.append(empty);
      } else eventRows.forEach((event) => {
        const item = document.createElement('div'); const text = document.createElement('span'); const whenEvent = document.createElement('time');
        const labels = {
          app_switch: event.previous_app_name ? `从 ${event.previous_app_name} 切换到此应用` : '切换到此应用',
          screen_locked: '屏幕已锁定', screen_unlocked: '屏幕已解锁', app_open: '打开此应用',
          inactive: '离开此应用', device_offline: '设备已离线',
        };
        text.textContent = labels[event.event_type] || '应用状态已更新';
        whenEvent.dateTime = new Date(Number(event.timestamp) * 1000).toISOString(); whenEvent.textContent = formatActivityTime(event.timestamp);
        item.append(text, whenEvent); events.append(item);
      });
      summary.addEventListener('click', () => {
        const expanded = summary.getAttribute('aria-expanded') === 'true'; summary.setAttribute('aria-expanded', String(!expanded)); events.hidden = expanded;
      });
      row.append(summary, events); activityList.append(row);
    });
  }
  function renderDonut(activity) {
    const apps = Array.isArray(activity?.top_apps) ? activity.top_apps : [];
    const total = Number(activity?.period_seconds || 0); donutLegend.replaceChildren(); setText('details-donut-total', formatDuration(total));
    if (!total || !apps.length) { donut.style.background = 'conic-gradient(var(--alive-border-soft) 0 100%)'; return; }
    const slices = apps.slice(0, 6).map((app) => ({ ...app }));
    const shown = slices.reduce((sum, app) => sum + Number(app.duration_seconds || 0), 0);
    if (total > shown) slices.push({ app_name: '其他应用', duration_seconds: total - shown, app_icon_url: '' });
    let at = 0;
    const stops = slices.map((app, index) => { const end = at + Number(app.duration_seconds || 0) / total * 100; const stop = `${chartColors[index % chartColors.length]} ${at.toFixed(2)}% ${end.toFixed(2)}%`; at = end; return stop; });
    donut.style.background = `conic-gradient(${stops.join(', ')})`;
    slices.forEach((app, index) => {
      const row = document.createElement('div'); row.className = 'details-donut-legend__row';
      const color = document.createElement('i'); color.style.background = chartColors[index % chartColors.length];
      const name = document.createElement('span'); name.textContent = app.app_name || '未知应用';
      const percentage = document.createElement('b'); percentage.textContent = `${Math.round(Number(app.duration_seconds || 0) / total * 100)}%`;
      row.append(color, name, percentage); donutLegend.append(row);
    });
  }
  function renderBars(activity) {
    const series = Array.isArray(activity?.time_series) ? activity.time_series : [];
    const max = Math.max(1, ...series.map((item) => Number(item.seconds || 0)));
    usageBars.replaceChildren();
    const step = selectedPeriod === 'daily' ? 3 : selectedPeriod === 'weekly' ? 1 : 5;
    series.forEach((item, index) => {
      const column = document.createElement('div'); column.className = 'details-usage-bar'; column.title = `${item.label}：${formatDuration(item.seconds)}`;
      const bar = document.createElement('i'); bar.style.height = `${Math.max(Number(item.seconds) ? 6 : 1, Number(item.seconds || 0) / max * 100)}%`;
      const label = document.createElement('span'); label.textContent = index % step === 0 ? item.label : '';
      column.append(bar, label); usageBars.append(column);
    });
    setText('details-trend-caption', selectedPeriod === 'daily' ? '按小时' : selectedPeriod === 'weekly' ? '按星期' : '按日期');
  }
  function renderAppRanking(activity) {
    const apps = Array.isArray(activity?.top_apps) ? activity.top_apps : []; appRanking.replaceChildren();
    if (!apps.length) { const empty = document.createElement('p'); empty.className = 'details-empty'; empty.textContent = '等待客户端记录这个周期的使用时长。'; appRanking.append(empty); return; }
    apps.slice(0, 6).forEach((app, index) => {
      const row = document.createElement('div'); row.className = 'details-app-ranking__row'; const rank = document.createElement('b'); rank.textContent = String(index + 1).padStart(2, '0');
      const name = document.createElement('span'); name.textContent = app.app_name || '未知应用'; const duration = document.createElement('strong'); duration.textContent = formatDuration(app.duration_seconds);
      row.append(rank, name, duration); appRanking.append(row);
    });
  }
  function sortedDevices() {
    const devices = [...(payload?.devices || [])]; const mode = sortSelect.value; const stateRank = { active: 0, idle: 1, offline: 2 };
    if (mode === 'online') devices.sort((left, right) => stateRank[left.public_state] - stateRank[right.public_state] || Number(right.last_updated) - Number(left.last_updated));
    else if (mode === 'updated') devices.sort((left, right) => Number(right.last_updated) - Number(left.last_updated));
    else if (mode === 'name') devices.sort((left, right) => String(left.show_name || left.id).localeCompare(String(right.show_name || right.id), 'zh-CN'));
    else devices.sort((left, right) => Number(left.profile?.sort_order || 0) - Number(right.profile?.sort_order || 0) || String(left.show_name || left.id).localeCompare(String(right.show_name || right.id), 'zh-CN'));
    return devices;
  }
  function renderDevices() {
    deviceList.replaceChildren(); const devices = sortedDevices();
    if (!devices.length) { const empty = document.createElement('p'); empty.className = 'details-empty'; empty.textContent = '还没有公开设备。启动客户端后会显示在这里。'; deviceList.append(empty); return; }
    devices.forEach((device) => {
      const row = document.createElement('article'); row.className = 'details-device-row'; const icon = document.createElement('span'); icon.className = 'details-device-icon'; icon.setAttribute('aria-hidden', 'true');
      if (device.profile?.icon_key === 'bilibili') { const bilibiliIcon = document.createElement('span'); bilibiliIcon.className = 'bilibili-tv-icon'; icon.append(bilibiliIcon); } else icon.textContent = deviceIcons[device.profile?.icon_key] || deviceIcons.other;
      const copy = document.createElement('div'); copy.className = 'details-device-copy'; const name = document.createElement('strong'); name.textContent = device.show_name || device.id;
      const app = document.createElement('span'); app.textContent = device.status || (device.public_state === 'offline' ? '等待设备重新上线' : '暂无活动'); copy.append(name, app);
      const state = document.createElement('div'); state.className = 'details-device-state'; const stateLine = document.createElement('span'); const dot = document.createElement('i'); dot.className = `is-${device.public_state}`; stateLine.append(dot, document.createTextNode(stateLabels[device.public_state] || '未知'));
      const updated = document.createElement('time'); updated.dateTime = new Date(Number(device.last_updated) * 1000).toISOString(); updated.textContent = relativeTime(device.last_updated); state.append(stateLine, updated); row.append(icon, copy, state); deviceList.append(row);
    });
  }
  function render(nextPayload) {
    payload = nextPayload; setText('details-summary', payload.summary);
    setText('details-generated-at', new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(Number(payload.generated_at) * 1000)));
    const activity = payload.activity || { categories: {} }; const selectedActivity = activity.categories?.[selectedActivityCategory] || { period_seconds: 0, total_records: 0, recent: [], top_apps: [], time_series: [] };
    const activeActivities = selectedActivity.recent.filter((record) => record.active).length;
    setText('metric-activity-today', formatDuration(selectedActivity.period_seconds)); setText('metric-activity-records', selectedActivity.total_records); setText('metric-activity-active', activeActivities);
    setText('metric-activity-period-name', selectedPeriod === 'daily' ? '今日使用' : selectedPeriod === 'weekly' ? '本周使用' : '本月使用');
    setText('metric-online', `${payload.device_counts.online} / ${payload.device_counts.total}`); setText('metric-daily', payload.visits.daily); setText('details-activity-period-label', activity.date_label || '当前周期');
    setText('device-active-count', payload.device_counts.active); setText('device-idle-count', payload.device_counts.idle); setText('device-offline-count', payload.device_counts.offline); setText('fact-status', payload.status.name); setText('fact-online', `${payload.device_counts.online} / ${payload.device_counts.total}`);
    setText('fact-music', payload.music.active ? `${payload.music.title} · ${payload.music.artist || '未知艺术家'}` : '当前未播放'); setText('fact-comments', `${payload.comments.total} 条`);
    activityTabs.forEach((tab) => tab.setAttribute('aria-selected', String(tab.dataset.activityCategory === selectedActivityCategory))); periodTabs.forEach((tab) => tab.setAttribute('aria-selected', String(tab.dataset.activityPeriod === selectedPeriod)));
    renderActivities(selectedActivity); renderDonut(selectedActivity); renderBars(selectedActivity); renderAppRanking(selectedActivity); renderDevices();
  }
  async function refresh() {
    try {
      const params = new URLSearchParams({ period: selectedPeriod, date: apiDate(selectedDate) });
      const response = await fetch(`/api/details/query?${params}`, { headers: { Accept: 'application/json' }, cache: 'no-store' }); if (!response.ok) throw new Error('详情读取失败'); render(await response.json());
    } catch (error) { setText('details-summary', '暂时无法读取详情数据，请稍后刷新。'); deviceList.replaceChildren(); activityList.replaceChildren(); }
  }
  function changePeriod(offset) {
    if (selectedPeriod === 'daily') selectedDate.setDate(selectedDate.getDate() + offset);
    else if (selectedPeriod === 'weekly') selectedDate.setDate(selectedDate.getDate() + 7 * offset);
    else selectedDate.setMonth(selectedDate.getMonth() + offset);
    if (selectedDate > new Date()) selectedDate = new Date(); refresh();
  }
  sortSelect.addEventListener('change', renderDevices);
  activityTabs.forEach((tab) => tab.addEventListener('click', () => { selectedActivityCategory = tab.dataset.activityCategory === 'desktop' ? 'desktop' : 'mobile'; if (payload) render(payload); }));
  periodTabs.forEach((tab) => tab.addEventListener('click', () => { selectedPeriod = tab.dataset.activityPeriod || 'daily'; refresh(); }));
  document.getElementById('details-period-prev')?.addEventListener('click', () => changePeriod(-1)); document.getElementById('details-period-next')?.addEventListener('click', () => changePeriod(1));
  datePickerTrigger?.addEventListener('click', (event) => { event.stopPropagation(); if (!datePickerMenu) return; datePickerLevel = 'year'; datePickerMenu.hidden = !datePickerMenu.hidden; datePickerTrigger.setAttribute('aria-expanded', String(!datePickerMenu.hidden)); if (!datePickerMenu.hidden) renderDatePicker(); });
  datePickerMenu?.addEventListener('click', (event) => event.stopPropagation());
  document.getElementById('details-date-picker-back')?.addEventListener('click', (event) => { event.stopPropagation(); if (datePickerLevel === 'day') datePickerLevel = 'month'; else if (datePickerLevel === 'month') datePickerLevel = 'year'; else { closeDatePicker(); return; } renderDatePicker(); });
  document.getElementById('details-date-picker-close')?.addEventListener('click', (event) => { event.stopPropagation(); closeDatePicker(); });
  document.addEventListener('click', (event) => { if (datePickerMenu && !datePickerMenu.hidden && !event.target.closest('.details-date-picker')) closeDatePicker(); });
  refresh(); window.setInterval(() => { if (!document.hidden) refresh(); }, 10000);
})();
