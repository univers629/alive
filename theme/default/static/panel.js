// 全局变量
let statusList = [];
let currentStatus = { 'color': 'sleeping', 'desc': '', 'id': -1, 'name': '未知' };
let deviceData = {};
let deviceOrder = [];
let commentsData = [];
let privateMode = false;
let panelLoadSequence = 0;
let displaySettings = {
    visit_display_mode: 'total',
    danmaku_enabled: true,
    health_section_enabled: true,
    comment_display_limit: 8,
    danmaku_replay_count: 1,
    danmaku_replay_interval: 30,
    page_name: 'Alive',
    page_title: 'Alive',
    music_library: '/alive/music-library',
    online_status_desc: '',
    offline_status_desc: ''
};

const SOCIAL_PLATFORMS = [
    ['website', '个人网站', 'https://example.com'],
    ['github', 'GitHub', 'https://github.com/username'],
    ['gitlab', 'GitLab', 'https://gitlab.com/username'],
    ['bilibili', '哔哩哔哩', 'https://space.bilibili.com/'],
    ['weibo', '微博', 'https://weibo.com/username'],
    ['xiaohongshu', '小红书', 'https://www.xiaohongshu.com/user/profile/'],
    ['douyin', '抖音', 'https://www.douyin.com/user/'],
    ['zhihu', '知乎', 'https://www.zhihu.com/people/username'],
    ['qq', 'QQ', 'https://qm.qq.com/'],
    ['wechat', '微信', 'https://weixin.qq.com/'],
    ['telegram', 'Telegram', 'https://t.me/username'],
    ['discord', 'Discord', 'https://discord.gg/'],
    ['x', 'X', 'https://x.com/username'],
    ['bluesky', 'Bluesky', 'https://bsky.app/profile/username'],
    ['mastodon', 'Mastodon', 'https://mastodon.social/@username'],
    ['instagram', 'Instagram', 'https://instagram.com/username'],
    ['youtube', 'YouTube', 'https://youtube.com/@username'],
    ['linkedin', 'LinkedIn', 'https://linkedin.com/in/username'],
    ['steam', 'Steam', 'https://steamcommunity.com/id/username'],
    ['email', '邮箱', 'name@example.com']
];

async function postJSON(url, body = {}) {
    return fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
}

function setPanelLoading(loading, message = '') {
    const status = document.getElementById('panel-loading-status');
    document.body.dataset.loading = loading ? 'true' : 'false';
    document.body.setAttribute('aria-busy', String(loading));
    if (status) status.textContent = message;
}

// 初始化页面
async function initPage() {
    const loadSequence = ++panelLoadSequence;
    setPanelLoading(true, '正在同步状态、设备和评论…');
    try {
        const [statusResponse, queryResponse] = await Promise.all([
            fetch('/api/status/list', { headers: { Accept: 'application/json' }, cache: 'no-store' }),
            fetch('/api/admin/snapshot', {
                credentials: 'same-origin',
                headers: { Accept: 'application/json' },
                cache: 'no-store',
            }),
        ]);
        if (!statusResponse.ok || !queryResponse.ok) {
            throw new Error('后台会话已失效或服务器暂时不可用');
        }
        const [statusListResp, queryData] = await Promise.all([
            statusResponse.json(),
            queryResponse.json(),
        ]);
        if (loadSequence !== panelLoadSequence) return;
        statusList = statusListResp.status_list;
        currentStatus = queryData.status;
        deviceData = queryData.devices;
        deviceOrder = Array.isArray(queryData.device_order) ? queryData.device_order : Object.keys(deviceData);
        commentsData = queryData.comments || [];
        privateMode = queryData.private_mode || false;
        displaySettings = queryData.settings || displaySettings;

        // 在同一帧内更新 UI，避免按接口响应顺序反复重排。
        renderStatusSelector();
        updateCurrentStatus();
        renderDeviceList();
        renderComments();
        document.getElementById('private-mode-toggle').checked = privateMode;
        const healthSectionToggle = document.getElementById('health-section-toggle');
        if (healthSectionToggle) healthSectionToggle.checked = displaySettings.health_section_enabled !== false;
        const visitDisplayMode = document.getElementById('visit-display-mode');
        if (visitDisplayMode) {
            visitDisplayMode.value = displaySettings.visit_display_mode || 'total';
            visitDisplayMode.dispatchEvent(new Event('change', { bubbles: true }));
        }
        const pageName = document.getElementById('page-name');
        if (pageName) pageName.value = displaySettings.page_name || 'Alive';
        const pageTitle = document.getElementById('page-title');
        if (pageTitle) pageTitle.value = displaySettings.page_title || 'Alive';
        const danmakuEnabled = document.getElementById('danmaku-enabled');
        if (danmakuEnabled) danmakuEnabled.checked = displaySettings.danmaku_enabled !== false;
        const commentDisplayLimit = document.getElementById('comment-display-limit');
        if (commentDisplayLimit) commentDisplayLimit.value = displaySettings.comment_display_limit || 8;
        const danmakuReplayCount = document.getElementById('danmaku-replay-count');
        if (danmakuReplayCount) danmakuReplayCount.value = displaySettings.danmaku_replay_count || 1;
        const danmakuReplayInterval = document.getElementById('danmaku-replay-interval');
        if (danmakuReplayInterval) danmakuReplayInterval.value = displaySettings.danmaku_replay_interval || 30;
        const musicLibrary = document.getElementById('music-library');
        if (musicLibrary) musicLibrary.value = displaySettings.music_library || '/alive/music-library';
        renderSocialLinksEditor(displaySettings.social_links || []);
        const onlineStatusDesc = document.getElementById('online-status-desc');
        if (onlineStatusDesc) onlineStatusDesc.value = displaySettings.online_status_desc || statusList[0]?.desc || '';
        const offlineStatusDesc = document.getElementById('offline-status-desc');
        if (offlineStatusDesc) offlineStatusDesc.value = displaySettings.offline_status_desc || statusList[1]?.desc || '';
        const onlineStatusLabel = document.getElementById('online-status-label');
        if (onlineStatusLabel) onlineStatusLabel.textContent = `${statusList[0]?.name || '在线'}状态文案`;
        const offlineStatusLabel = document.getElementById('offline-status-label');
        if (offlineStatusLabel) offlineStatusLabel.textContent = `${statusList[1]?.name || '离线'}状态文案`;
        // 如果启用了统计功能，获取统计数据
        if (document.getElementById('metrics-container')) {
            void fetchMetrics();
        }
        setPanelLoading(false, '');
    } catch (error) {
        if (loadSequence !== panelLoadSequence) return;
        console.error('初始化失败:', error);
        setPanelLoading(false, '加载失败，可点击“刷新数据”重试。');
        alert(`加载数据失败，请检查网络连接或重新登录\n${error}`);
    }
}

function renderSocialLinksEditor(savedLinks) {
    const container = document.getElementById('social-links-editor');
    if (!container) return;
    const configured = new Map(savedLinks.map((item) => [item.platform, item.url]));
    container.replaceChildren();
    SOCIAL_PLATFORMS.forEach(([platform, label, placeholder]) => {
        const row = document.createElement('label');
        row.className = 'social-link-editor-row';
        const toggle = document.createElement('span');
        toggle.className = 'social-link-editor-toggle';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.dataset.platform = platform;
        checkbox.checked = configured.has(platform);
        const name = document.createElement('span');
        name.textContent = label;
        toggle.append(checkbox, name);
        const input = document.createElement('input');
        input.className = 'panel-input';
        input.type = platform === 'email' ? 'email' : 'url';
        input.inputMode = platform === 'email' ? 'email' : 'url';
        input.dataset.socialUrl = platform;
        input.maxLength = 2048;
        input.placeholder = placeholder;
        input.value = configured.get(platform) || '';
        checkbox.addEventListener('change', () => {
            if (checkbox.checked) input.focus();
        });
        row.append(toggle, input);
        container.appendChild(row);
    });
}

// 渲染状态选择器
function renderStatusSelector() {
    const container = document.getElementById('status-selector');
    container.innerHTML = '';

    let status;
    for (let index = 0; index < statusList.length; index++) {
        status = statusList[index];
        const statusItem = document.createElement('div');
        statusItem.className = `status-item ${currentStatus.id === index ? 'active' : ''}`;
        statusItem.dataset.statusColor = status.color;
        statusItem.textContent = status.name;
        statusItem.dataset.index = index;
        statusItem.addEventListener('click', function () {
            setStatus(parseInt(this.dataset.index));
        });
        container.appendChild(statusItem);
    };
}

// 更新当前状态显示
function updateCurrentStatus() {
    const statusName = document.getElementById('current-status-name');
    if (statusList[currentStatus.id]) {
        statusName.textContent = statusList[currentStatus.id].name;
        statusName.dataset.statusColor = statusList[currentStatus.id].color;
    } else {
        statusName.textContent = '未知状态';
        statusName.dataset.statusColor = 'error';
    }

    // 更新状态选择器中的活动状态
    document.querySelectorAll('.status-item').forEach((item, index) => {
        item.classList.toggle('active', index === currentStatus.id);
    });
}

// 设置状态
async function setStatus(statusIndex) {
    try {
        const response = await postJSON('/api/status/set', { status: statusIndex });
        const data = await response.json();

        if (data.success) {
            currentStatus.id = statusIndex;
            updateCurrentStatus();
        } else {
            alert('设置状态失败: ' + (data.message || '未知错误'));
        }
    } catch (error) {
        console.error('设置状态失败:', error);
        alert('设置状态失败，请检查网络连接');
    }
}

// 渲染设备列表
function renderDeviceList() {
    const tbody = document.getElementById('device-list-body');
    tbody.innerHTML = '';

    if (Object.keys(deviceData).length === 0) {
        const tr = document.createElement('tr');
        const emptyCell = document.createElement('td');
        emptyCell.colSpan = 6;
        emptyCell.style.textAlign = 'center';
        emptyCell.textContent = '暂无设备数据';
        tr.appendChild(emptyCell);
        tbody.appendChild(tr);
        return;
    }

    const orderedIds = deviceOrder.filter((deviceId) => deviceData[deviceId]);
    Object.keys(deviceData).forEach((deviceId) => {
        if (!orderedIds.includes(deviceId)) orderedIds.push(deviceId);
    });
    for (const deviceId of orderedIds) {
        const device = deviceData[deviceId];
        const tr = document.createElement('tr');

        const profile = device.profile || {};
        const deleteButton = document.createElement('button');
        deleteButton.className = 'btn btn-danger';
        deleteButton.textContent = '删除';
        deleteButton.dataset.deviceId = deviceId;
        deleteButton.addEventListener('click', function () {
            removeDevice(this.dataset.deviceId);
        });

        const tdDevice = document.createElement('td');
        tdDevice.textContent = deviceId;

        const tdName = document.createElement('td');
        const nameInput = document.createElement('input');
        nameInput.className = 'panel-input device-name-input';
        nameInput.value = profile.display_name || device.show_name || '';
        nameInput.maxLength = 1024;
        tdName.appendChild(nameInput);

        const tdIcon = document.createElement('td');
        const iconSelect = document.createElement('select');
        iconSelect.className = 'panel-input';
        const iconOptions = {
            desktop: '🖥️ 台式机',
            laptop: '💻 笔记本',
            phone: '📱 手机',
            tablet: '▯ 平板',
            watch: '⌚ 手表',
            server: '▤ 服务器',
            game: '🎮 游戏设备',
            other: '◇ 其他',
            bilibili: '哔哩哔哩'
        };
        for (const [value, label] of Object.entries(iconOptions)) {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = label;
            option.selected = value === (profile.icon_key || 'desktop');
            iconSelect.appendChild(option);
        }
        tdIcon.appendChild(iconSelect);

        const tdPublic = document.createElement('td');
        const publicInput = document.createElement('input');
        publicInput.type = 'checkbox';
        publicInput.checked = profile.public !== false;
        publicInput.setAttribute('aria-label', `公开 ${device.show_name}`);
        tdPublic.appendChild(publicInput);

        const tdStatus = document.createElement('td');
        tdStatus.className = 'device-live-state';
        tdStatus.textContent = `${device.using ? '使用中' : '未使用'} · ${device.status || '无状态'}`;

        const tdAction = document.createElement('td');
        const actionGroup = document.createElement('div');
        actionGroup.className = 'device-action-group';
        const position = orderedIds.indexOf(deviceId);
        [['up', '↑', '向上移动', position === 0], ['down', '↓', '向下移动', position === orderedIds.length - 1]].forEach(([direction, symbol, label, disabled]) => {
            const moveButton = document.createElement('button');
            moveButton.className = 'icon-btn';
            moveButton.type = 'button';
            moveButton.textContent = symbol;
            moveButton.title = label;
            moveButton.setAttribute('aria-label', label);
            moveButton.disabled = disabled;
            moveButton.addEventListener('click', () => reorderDevice(deviceId, direction));
            actionGroup.appendChild(moveButton);
        });
        const saveButton = document.createElement('button');
        saveButton.className = 'btn btn-primary';
        saveButton.textContent = '保存';
        saveButton.addEventListener('click', () => {
            saveDeviceProfile(deviceId, {
                display_name: nameInput.value,
                icon_key: iconSelect.value,
                public: publicInput.checked
            });
        });
        actionGroup.appendChild(saveButton);
        actionGroup.appendChild(deleteButton);
        tdAction.appendChild(actionGroup);

        tr.appendChild(tdDevice);
        tr.appendChild(tdName);
        tr.appendChild(tdIcon);
        tr.appendChild(tdPublic);
        tr.appendChild(tdStatus);
        tr.appendChild(tdAction);

        tbody.appendChild(tr);
    }
}

async function reorderDevice(deviceId, direction) {
    try {
        const response = await postJSON('/api/admin/device/reorder', { id: deviceId, direction });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.message || '排序失败');
        deviceData = data.devices || {};
        deviceOrder = Array.isArray(data.device_order) ? data.device_order : Object.keys(deviceData);
        renderDeviceList();
    } catch (error) {
        alert(`设备排序失败：${error.message || error}`);
    }
}

async function saveDeviceProfile(deviceId, profile) {
    try {
        const response = await postJSON('/api/admin/device/profile', {
            id: deviceId,
            ...profile
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.message || data.details || '保存失败');
        }
        deviceData[deviceId] = data.device;
        renderDeviceList();
    } catch (error) {
        console.error('保存设备资料失败:', error);
        alert(`保存设备资料失败：${error.message || error}`);
    }
}

function renderComments() {
    const container = document.getElementById('comments-list');
    if (!container) return;
    container.replaceChildren();
    if (!commentsData.length) {
        const empty = document.createElement('p');
        empty.className = 'comments-empty';
        empty.textContent = '暂无保留评论。';
        container.appendChild(empty);
        return;
    }
    commentsData.forEach((comment) => {
        const row = document.createElement('article');
        row.className = 'comment-row';
        const copy = document.createElement('div');
        copy.className = 'comment-row__copy';
        const meta = document.createElement('div');
        meta.className = 'comment-row__meta';
        const nickname = document.createElement('strong');
        nickname.textContent = comment.nickname;
        const date = document.createElement('time');
        date.textContent = new Date(Number(comment.created_at) * 1000).toLocaleString('zh-CN');
        meta.append(nickname, date);
        const state = document.createElement('span');
        state.className = 'comment-row__state';
        state.textContent = [comment.pinned ? '已置顶' : '', comment.favorite ? '已收藏' : ''].filter(Boolean).join(' · ') || '普通';
        meta.appendChild(state);
        const content = document.createElement('p');
        content.textContent = comment.content;
        copy.append(meta, content);
        const actions = document.createElement('div');
        actions.className = 'comment-row__actions';
        [['favorite', comment.favorite ? '取消收藏' : '收藏', comment.favorite ? '♥' : '♡'],
            ['pinned', comment.pinned ? '取消置顶' : '置顶', '⤒']].forEach(([key, label, symbol]) => {
            const button = document.createElement('button');
            button.className = `comment-action comment-action--${key}`;
            button.type = 'button';
            button.title = label;
            button.setAttribute('aria-label', label);
            button.setAttribute('aria-pressed', String(Boolean(comment[key])));
            const icon = document.createElement('span');
            icon.className = 'comment-action__icon';
            icon.setAttribute('aria-hidden', 'true');
            icon.textContent = symbol;
            const text = document.createElement('span');
            text.textContent = label;
            button.append(icon, text);
            button.addEventListener('click', () => updateComment(comment, key));
            actions.appendChild(button);
        });
        const remove = document.createElement('button');
        remove.className = 'comment-action comment-action--danger';
        remove.type = 'button';
        remove.title = '删除评论';
        remove.setAttribute('aria-label', '删除评论');
        const removeIcon = document.createElement('span');
        removeIcon.className = 'comment-action__icon';
        removeIcon.setAttribute('aria-hidden', 'true');
        removeIcon.textContent = '×';
        const removeText = document.createElement('span');
        removeText.textContent = '删除';
        remove.append(removeIcon, removeText);
        remove.addEventListener('click', () => removeComment(comment.id));
        actions.appendChild(remove);
        row.append(copy, actions);
        container.appendChild(row);
    });
}

async function updateComment(comment, changedKey) {
    const next = { favorite: Boolean(comment.favorite), pinned: Boolean(comment.pinned) };
    next[changedKey] = !next[changedKey];
    const response = await postJSON('/api/admin/comments/update', { id: comment.id, ...next });
    const data = await response.json();
    if (!response.ok || !data.success) return alert(data.message || '评论更新失败');
    commentsData = commentsData.map((item) => item.id === comment.id ? data.comment : item);
    renderComments();
}

async function removeComment(commentId) {
    const response = await postJSON('/api/admin/comments/remove', { id: commentId });
    const data = await response.json();
    if (!response.ok || !data.success) return alert(data.message || '删除评论失败');
    commentsData = commentsData.filter((comment) => comment.id !== commentId);
    renderComments();
}

async function clearComments() {
    if (!confirm('确定清空所有评论吗？此操作不可撤销。')) return;
    const response = await postJSON('/api/admin/comments/clear');
    const data = await response.json();
    if (!response.ok || !data.success) return alert(data.message || '清空评论失败');
    commentsData = [];
    renderComments();
}

async function saveDisplaySettings() {
    const select = document.getElementById('visit-display-mode');
    if (!select) return;
    try {
        const response = await postJSON('/api/admin/settings', {
            visit_display_mode: select.value,
            page_name: document.getElementById('page-name').value.trim(),
            page_title: document.getElementById('page-title').value.trim(),
            music_library: document.getElementById('music-library').value.trim()
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.message || data.details || '保存失败');
        }
        displaySettings = data.settings;
        alert('主页展示与音乐目录已保存。');
    } catch (error) {
        console.error('保存展示设置失败:', error);
        alert(`保存展示设置失败：${error.message || error}`);
    }
}

async function saveCommentDisplaySettings() {
    const values = {
        danmaku_enabled: document.getElementById('danmaku-enabled')?.checked,
        comment_display_limit: Number(document.getElementById('comment-display-limit')?.value),
        danmaku_replay_count: Number(document.getElementById('danmaku-replay-count')?.value),
        danmaku_replay_interval: Number(document.getElementById('danmaku-replay-interval')?.value),
    };
    if (!Number.isInteger(values.comment_display_limit) || values.comment_display_limit < 1 || values.comment_display_limit > 50
        || !Number.isInteger(values.danmaku_replay_count) || values.danmaku_replay_count < 1 || values.danmaku_replay_count > 10
        || !Number.isInteger(values.danmaku_replay_interval) || values.danmaku_replay_interval < 3 || values.danmaku_replay_interval > 300) {
        alert('请填写有效范围：主页评论 1–50 条、每轮弹幕 1–10 条、播放间隔 3–300 秒。');
        return;
    }
    try {
        const response = await postJSON('/api/admin/settings', values);
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.message || data.details || '保存失败');
        displaySettings = data.settings;
        alert('评论和弹幕展示设置已保存。');
    } catch (error) {
        alert(`保存评论展示设置失败：${error.message || error}`);
    }
}

async function saveSocialLinks() {
    const entries = [];
    for (const checkbox of document.querySelectorAll('#social-links-editor input[type="checkbox"]')) {
        if (!checkbox.checked) continue;
        const platform = checkbox.dataset.platform;
        const input = document.querySelector(`#social-links-editor input[data-social-url="${CSS.escape(platform)}"]`);
        const url = input?.value.trim() || '';
        if (!url) {
            alert(`请填写 ${checkbox.parentElement?.textContent?.trim() || platform} 的链接。`);
            input?.focus();
            return;
        }
        entries.push({ platform, url });
    }
    try {
        const response = await postJSON('/api/admin/settings', { social_links: entries });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.message || data.details || '保存失败');
        displaySettings = data.settings;
        renderSocialLinksEditor(displaySettings.social_links || []);
        alert('个人链接已保存。');
    } catch (error) {
        alert(`保存个人链接失败：${error.message || error}`);
    }
}

async function saveStatusDescriptions() {
    const online = document.getElementById('online-status-desc');
    const offline = document.getElementById('offline-status-desc');
    if (!online?.value.trim() || !offline?.value.trim()) {
        alert('两条状态文案都不能为空。');
        return;
    }
    try {
        const response = await postJSON('/api/admin/settings', {
            online_status_desc: online.value.trim(),
            offline_status_desc: offline.value.trim()
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.message || data.details || '保存失败');
        displaySettings = data.settings;
        statusList[0].desc = data.settings.online_status_desc;
        statusList[1].desc = data.settings.offline_status_desc;
        alert('状态文案已保存。');
    } catch (error) {
        alert(`保存状态文案失败：${error.message || error}`);
    }
}

async function uploadProfileAvatar() {
    const input = document.getElementById('profile-avatar-file');
    const status = document.getElementById('profile-avatar-upload-status');
    const preview = document.getElementById('profile-avatar-preview');
    const file = input?.files?.[0];
    if (!file) {
        status.textContent = '请选择 PNG、JPEG 或 WebP 图片。';
        return;
    }
    if (file.size > 5 * 1024 * 1024) {
        status.textContent = '图片不能超过 5 MiB。';
        return;
    }
    status.textContent = '上传中...';
    try {
        const response = await fetch('/api/admin/profile/avatar', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': file.type },
            body: file
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.message || '上传失败');
        preview.src = data.profile_avatar;
        status.textContent = '主页头像和网站图标已更新。';
        input.value = '';
        document.getElementById('profile-avatar-file-name').textContent = '';
    } catch (error) {
        status.textContent = `上传失败：${error.message || error}`;
    }
}

async function saveSecret() {
    const first = document.getElementById('new-secret');
    const second = document.getElementById('confirm-secret');
    if (!first || !second) return;
    if (first.value.length < 6) {
        alert('新密钥至少需要 6 个字符。');
        first.focus();
        return;
    }
    if (first.value !== second.value) {
        alert('两次输入的密钥不一致。');
        second.focus();
        return;
    }
    if (!confirm('轮换后旧客户端会立即无法上报，确定继续吗？')) return;
    try {
        const response = await postJSON('/api/admin/secret', { new_secret: first.value });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.message || data.details || '密钥轮换失败');
        }
        first.value = '';
        second.value = '';
        alert('密钥已更新。请立即同步更新所有客户端。');
    } catch (error) {
        alert(`密钥轮换失败：${error.message || error}`);
    }
}

// 删除设备
async function removeDevice(deviceId) {
    if (!confirm(`确定要删除设备 "${deviceId}" 吗？`)) {
        return;
    }

    try {
        const response = await postJSON('/api/device/remove', { id: deviceId });
        const data = await response.json();

        if (data.success) {
            delete deviceData[deviceId];
            renderDeviceList();
        } else {
            alert('删除设备失败: ' + (data.message || '未知错误'));
        }
    } catch (error) {
        console.error('删除设备失败:', error);
        alert('删除设备失败，请检查网络连接');
    }
}

// 清除所有设备
async function clearAllDevices() {
    if (!confirm('确定要清除所有设备吗？此操作不可撤销！')) {
        return;
    }

    try {
        const response = await postJSON('/api/device/clear');
        const data = await response.json();

        if (data.success) {
            deviceData = {};
            renderDeviceList();
        } else {
            alert('清除设备失败: ' + (data.message || '未知错误'));
        }
    } catch (error) {
        console.error('清除设备失败:', error);
        alert('清除设备失败，请检查网络连接');
    }
}

// 切换隐私模式
async function togglePrivateMode(isPrivate) {
    try {
        const response = await postJSON('/api/device/private', { private: isPrivate });
        const data = await response.json();

        if (data.success) {
            privateMode = isPrivate;
        } else {
            alert('切换隐私模式失败: ' + (data.message || '未知错误'));
            document.getElementById('private-mode-toggle').checked = privateMode;
        }
    } catch (error) {
        console.error('切换隐私模式失败:', error);
        alert('切换隐私模式失败，请检查网络连接');
        document.getElementById('private-mode-toggle').checked = privateMode;
    }
}

async function toggleHealthSection(enabled) {
    const toggle = document.getElementById('health-section-toggle');
    try {
        const response = await postJSON('/api/admin/settings', { health_section_enabled: enabled });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.message || data.details || '保存失败');
        displaySettings = data.settings;
    } catch (error) {
        console.error('切换身体数据区域失败:', error);
        if (toggle) toggle.checked = displaySettings.health_section_enabled !== false;
        alert(`切换身体数据区域失败：${error.message || error}`);
    }
}

// 获取统计数据
async function fetchMetrics() {
    try {
        const response = await fetch('/api/metrics');
        const data = await response.json();

        const container = document.getElementById('metrics-container');
        container.innerHTML = '';

        // 今日访问
        if (data.daily) {
            if (data.daily['/']) {
                addMetricCard(container, '今日首页访问量', data.daily['/'] || 0);
            }
            let apiCalls = 0;
            for (const [path, count] of Object.entries(data.daily)) {
                if (path.startsWith('/') && path !== '/') {
                    apiCalls += count;
                }
            }
            addMetricCard(container, '今日 API 调用次数', apiCalls);
        }

        // 本周访问
        if (data.weekly) {
            if (data.weekly['/']) {
                addMetricCard(container, '本周首页访问量', data.weekly['/'] || 0);
            }
            let apiCalls = 0;
            for (const [path, count] of Object.entries(data.weekly)) {
                if (path.startsWith('/') && path !== '/') {
                    apiCalls += count;
                }
            }
            addMetricCard(container, '本周 API 调用次数', apiCalls);
        }

        // 本月访问
        if (data.monthly) {
            if (data.monthly['/']) {
                addMetricCard(container, '本月首页访问量', data.monthly['/'] || 0);
            }
            let apiCalls = 0;
            for (const [path, count] of Object.entries(data.monthly)) {
                if (path.startsWith('/') && path !== '/') {
                    apiCalls += count;
                }
            }
            addMetricCard(container, '本月 API 调用次数', apiCalls);
        }

        // 本年访问
        if (data.yearly) {
            if (data.yearly['/']) {
                addMetricCard(container, '本年首页访问量', data.yearly['/'] || 0);
            }
            let apiCalls = 0;
            for (const [path, count] of Object.entries(data.yearly)) {
                if (path.startsWith('/') && path !== '/') {
                    apiCalls += count;
                }
            }
            addMetricCard(container, '本年 API 调用次数', apiCalls);
        }

        // 总访问
        if (data.total) {
            if (data.total['/']) {
                addMetricCard(container, '首页总访问量', data.total['/'] || 0);
            }
            let apiCalls = 0;
            for (const [path, count] of Object.entries(data.total)) {
                if (path.startsWith('/') && path !== '/') {
                    apiCalls += count;
                }
            }
            addMetricCard(container, 'API 总调用次数', apiCalls);
        }

    } catch (error) {
        console.error('获取统计数据失败:', error);
        const container = document.getElementById('metrics-container');
        container.innerHTML = '<p>获取统计数据失败，请刷新页面重试</p>';
    }
}

// 添加统计卡片
function addMetricCard(container, label, value) {
    const card = document.createElement('div');
    card.className = 'metric-card';
    card.innerHTML = `
        <div class="metric-value">${value}</div>
        <div class="metric-label">${label}</div>
    `;
    container.appendChild(card);
}

// 退出登录
async function logout() {
    try {
        await postJSON('/panel/logout');
    } finally {
        window.location.href = '/panel/login';
    }
}

// 初始化事件监听器
document.addEventListener('DOMContentLoaded', function () {
    // 添加事件监听器
    const clearDevicesBtn = document.getElementById('clear-devices-btn');
    if (clearDevicesBtn) {
        clearDevicesBtn.addEventListener('click', clearAllDevices);
    }

    // 刷新数据按钮
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', initPage)
    }

    // 退出登录按钮
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', logout);
    }

    // 切换隐私模式按钮
    const privateModeToggle = document.getElementById('private-mode-toggle');
    if (privateModeToggle) {
        privateModeToggle.addEventListener('change', function () {
            togglePrivateMode(this.checked);
        });
    }
    const healthSectionToggle = document.getElementById('health-section-toggle');
    if (healthSectionToggle) {
        healthSectionToggle.addEventListener('change', function () {
            toggleHealthSection(this.checked);
        });
    }

    const saveDisplaySettingsBtn = document.getElementById('save-display-settings-btn');
    if (saveDisplaySettingsBtn) {
        saveDisplaySettingsBtn.addEventListener('click', saveDisplaySettings);
    }
    const saveStatusDescriptionsBtn = document.getElementById('save-status-descriptions-btn');
    if (saveStatusDescriptionsBtn) {
        saveStatusDescriptionsBtn.addEventListener('click', saveStatusDescriptions);
    }
    const saveCommentDisplaySettingsBtn = document.getElementById('save-comment-display-settings-btn');
    if (saveCommentDisplaySettingsBtn) {
        saveCommentDisplaySettingsBtn.addEventListener('click', saveCommentDisplaySettings);
    }
    const saveSecretBtn = document.getElementById('save-secret-btn');
    if (saveSecretBtn) {
        saveSecretBtn.addEventListener('click', saveSecret);
    }
    const profileAvatarFile = document.getElementById('profile-avatar-file');
    if (profileAvatarFile) {
        profileAvatarFile.addEventListener('change', () => {
            const file = profileAvatarFile.files?.[0];
            document.getElementById('profile-avatar-file-name').textContent = file ? file.name : '';
            if (!file) return;
            const preview = document.getElementById('profile-avatar-preview');
            const objectUrl = URL.createObjectURL(file);
            preview.onload = () => URL.revokeObjectURL(objectUrl);
            preview.src = objectUrl;
        });
    }
    const chooseProfileAvatarBtn = document.getElementById('choose-profile-avatar-btn');
    if (chooseProfileAvatarBtn) chooseProfileAvatarBtn.addEventListener('click', () => profileAvatarFile?.click());
    const uploadProfileAvatarBtn = document.getElementById('upload-profile-avatar-btn');
    if (uploadProfileAvatarBtn) uploadProfileAvatarBtn.addEventListener('click', uploadProfileAvatar);
    const saveSocialLinksBtn = document.getElementById('save-social-links-btn');
    if (saveSocialLinksBtn) saveSocialLinksBtn.addEventListener('click', saveSocialLinks);
    const clearCommentsBtn = document.getElementById('clear-comments-btn');
    if (clearCommentsBtn) clearCommentsBtn.addEventListener('click', clearComments);

    // 设备删除按钮
    document.addEventListener('click', function (event) {
        const target = event.target;
        if (target.matches('button[onclick^="removeDevice"]')) {
            event.preventDefault();
            const deviceId = target.getAttribute('onclick').match(/'([^']+)'/)[1];
            removeDevice(deviceId);
            target.removeAttribute('onclick');
        }
    });

    // 不等待背景图、头像等非关键资源，先请求后台数据。
    void initPage();
});
