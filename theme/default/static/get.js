import {
    sleep,
    sliceText,
    escapeHtml,
    escapeJs,
    getFormattedTime,
    checkVercelDeploy
} from './utils.js';

function updateHealthStatus(health) {
    const badge = document.getElementById('health-data-state');
    if (!badge) return;

    const values = health && health.active ? health : null;
    const heartRate = values?.heart_rate;
    const resting = values?.resting_heart_rate;
    const minimum = values?.heart_rate_min;
    const maximum = values?.heart_rate_max;
    const steps = values?.steps;
    const goal = values?.step_goal || 8000;
    const source = String(values?.source || '身体状态');
    const stale = Boolean(values?.stale);
    const updated = values?.updated_at
        ? getFormattedTime(new Date(Number(values.updated_at) * 1000))
        : '等待上报';

    const setText = (id, text) => {
        const element = document.getElementById(id);
        if (element) element.textContent = text;
    };

    if (!values) {
        badge.textContent = '等待真机上报';
        setText('health-heart-rate', '—');
        setText('health-resting-rate', '暂无静息心率');
        setText('health-heart-range', '暂无今日范围');
        setText('health-steps', '—');
        setText('health-step-goal', '目标 8,000');
        setText('health-step-remaining', '等待步数数据');
        setText('health-steps-percent', '0%');
        setText('health-heart-source', '等待 Android 真机');
        setText('health-steps-source', '等待 Android 真机');
        setText('health-heart-state', '未连接');
        setText('health-steps-state', '未连接');
        setText('health-heart-updated', '尚无真实数据');
        setText('health-steps-updated', '尚无真实数据');
        const ring = document.getElementById('health-steps-ring');
        if (ring) {
            ring.style.setProperty('--step-progress', '0%');
            ring.setAttribute('aria-label', '等待真实步数数据');
        }
        return;
    }

    badge.textContent = stale ? '已保存 · 等待新数据' : '实时身体数据';
    setText('health-heart-rate', Number.isFinite(Number(heartRate)) ? String(heartRate) : '—');
    setText('health-resting-rate', resting != null && Number.isFinite(Number(resting)) ? `静息 ${resting}` : '暂无静息心率');
    setText(
        'health-heart-range',
        minimum != null && maximum != null && Number.isFinite(Number(minimum)) && Number.isFinite(Number(maximum))
            ? `今日 ${minimum}–${maximum}`
            : '暂无今日范围'
    );
    setText('health-steps', Number.isFinite(Number(steps)) ? Number(steps).toLocaleString('zh-CN') : '—');
    setText('health-step-goal', `目标 ${Number(goal).toLocaleString('zh-CN')}`);
    setText(
        'health-step-remaining',
        Number.isFinite(Number(steps))
            ? (Number(steps) >= Number(goal)
                ? `超出目标 ${(Number(steps) - Number(goal)).toLocaleString('zh-CN')}`
                : `还差 ${(Number(goal) - Number(steps)).toLocaleString('zh-CN')}`)
            : '等待步数数据'
    );
    setText('health-heart-source', source);
    setText('health-steps-source', source);
    setText('health-heart-state', stale ? '非实时' : '监测中');
    setText('health-steps-state', stale ? '非实时' : '今日');
    setText('health-heart-updated', `更新于 ${updated}`);
    setText('health-steps-updated', `更新于 ${updated}`);

    const progress = Number.isFinite(Number(steps))
        ? Math.max(0, Math.min(100, Math.round(Number(steps) / Number(goal) * 100)))
        : 0;
    setText('health-steps-percent', `${progress}%`);
    const ring = document.getElementById('health-steps-ring');
    if (ring) {
        ring.style.setProperty('--step-progress', `${progress}%`);
        ring.setAttribute('aria-label', `今日步数目标完成 ${progress}%`);
    }
}

function setTextIfChanged(element, value) {
    const text = String(value);
    if (element && element.textContent !== text) element.textContent = text;
}

function createDeviceCard(device, index, timeout, now, deviceIcons) {
    const card = document.createElement('article');
    card.className = 'device-card';
    card.dataset.deviceId = String(device.id);
    card.innerHTML = `
        <div class="device-card__top">
            <div class="device-card__identity">
                <span class="device-card__icon" aria-hidden="true"></span>
                <div class="device-card__name"><strong></strong><span></span></div>
            </div>
            <span class="device-card__state"><i class="device-card__dot" aria-hidden="true"></i><span></span></span>
        </div>
        <div class="device-card__app">
            <span class="device-card__app-icon" aria-hidden="true"></span>
            <div class="device-card__app-copy"><small>CURRENT APP</small><span></span></div>
        </div>
        <div class="device-card__bottom">
            <div class="device-card__meta"></div>
            <span class="device-card__footer"></span>
        </div>`;
    updateDeviceCard(card, device, index, timeout, now, deviceIcons);
    return card;
}

function updateDeviceCard(card, device, index, timeout, now, deviceIcons) {
    const fields = device.fields || {};
    const fresh = timeout <= 0 || now - Number(device.last_updated || 0) <= timeout;
    const state = fresh ? (device.using ? 'active' : 'idle') : 'offline';
    const stateLabel = state === 'active' ? '使用中' : state === 'idle' ? '在线空闲' : '离线';
    const appName = sliceText(String(device.status || '暂无活动'), metadata.status.device_slice || 80);
    const appInitial = Array.from(appName.trim())[0] || 'A';
    const updated = getFormattedTime(new Date(device.last_updated * 1000));

    const stateClass = `device-card--${state}`;
    if (!card.classList.contains(stateClass)) {
        card.classList.remove('device-card--active', 'device-card--idle', 'device-card--offline');
        card.classList.add(stateClass);
    }
    if (card.style.getPropertyValue('--device-index') !== String(index)) {
        card.style.setProperty('--device-index', String(index));
    }
    if (card.title !== updated) card.title = updated;

    const icon = card.querySelector('.device-card__icon');
    const iconKey = device.profile?.icon_key;
    if (iconKey === 'bilibili') {
        if (!icon.querySelector('.bilibili-tv-icon')) {
            icon.replaceChildren(Object.assign(document.createElement('span'), { className: 'bilibili-tv-icon' }));
        }
    } else if (iconKey === 'tablet') {
        if (!icon.querySelector('.tablet-device-icon')) {
            icon.replaceChildren(Object.assign(document.createElement('span'), { className: 'tablet-device-icon' }));
        }
    } else {
        setTextIfChanged(icon, deviceIcons[iconKey] || deviceIcons.other);
    }

    setTextIfChanged(card.querySelector('.device-card__name strong'), device.show_name || device.id);
    setTextIfChanged(card.querySelector('.device-card__name span'), device.id);
    setTextIfChanged(card.querySelector('.device-card__state > span'), stateLabel);

    const appIcon = card.querySelector('.device-card__app-icon');
    const appIconUrl = String(fields.app_icon_url || '');
    const existingImage = appIcon.querySelector('img');
    if (appIconUrl) {
        if (!existingImage || existingImage.getAttribute('src') !== appIconUrl) {
            const image = document.createElement('img');
            image.src = appIconUrl;
            image.alt = '';
            image.width = 28;
            image.height = 28;
            image.loading = 'lazy';
            appIcon.replaceChildren(image);
        }
    } else {
        setTextIfChanged(appIcon, appInitial.toUpperCase());
    }
    const appText = card.querySelector('.device-card__app-copy > span');
    setTextIfChanged(appText, appName);
    if (appText.title !== String(device.status || '')) appText.title = String(device.status || '');

    const batteryRaw = fields.battery ?? fields.battery_percent ?? fields.power;
    const battery = Number(batteryRaw);
    const network = fields.network_type || fields.network || fields.connection_type || '';
    const platform = fields.platform || fields.os || '';
    const chips = [];
    if (Number.isFinite(battery)) {
        chips.push(`🔋 ${Math.max(0, Math.min(100, Math.round(battery)))}%${fields.charging ? ' · 充电中' : ''}`);
    }
    if (network) chips.push(`◉ ${String(network)}`);
    if (platform) chips.push(String(platform));
    if (!chips.length) chips.push(state === 'offline' ? '等待设备重新上线' : '状态实时同步中');

    const meta = card.querySelector('.device-card__meta');
    chips.forEach((chip, chipIndex) => {
        let element = meta.children[chipIndex];
        if (!element) {
            element = document.createElement('span');
            element.className = 'device-card__chip';
            meta.append(element);
        }
        setTextIfChanged(element, chip);
    });
    while (meta.children.length > chips.length) meta.lastElementChild.remove();
    setTextIfChanged(card.querySelector('.device-card__footer'), `更新于 ${updated}`);
}

function updateDeviceStatus(data) {
    /*
    正常更新状态使用
    data: api / events 返回数据
    */
    const statusElement = document.getElementById('status');
    const lastUpdatedElement = document.getElementById('last-updated');
    const visitMetric = data.visit_metric;
    const onlineViewerCount = document.getElementById('online-viewer-count');
    const healthOverview = document.getElementById('health-overview');

    if (healthOverview && typeof data.health_section_enabled === 'boolean') {
        healthOverview.hidden = !data.health_section_enabled;
    }

    if (onlineViewerCount && Number.isFinite(Number(data.online_viewers))) {
        onlineViewerCount.textContent = String(Math.max(0, Number(data.online_viewers)));
    }

    // 更新状态
    if (statusElement) {
        statusElement.textContent = data.status.name;
        document.getElementById('additional-info').innerHTML = data.status.desc;
        let last_status = statusElement.classList.item(0);
        statusElement.classList.remove(last_status);
        statusElement.classList.add(data.status.color);
    }

    updateHealthStatus(data.health);

    // 更新设备状态
    const deviceMap = data.device || {};
    const orderedIds = Array.isArray(data.device_order) ? data.device_order : Object.keys(deviceMap);
    const knownIds = new Set();
    const devices = orderedIds
        .map((id) => {
            const device = deviceMap[id];
            if (device) knownIds.add(String(id));
            return device;
        })
        .filter(Boolean);
    // Keep the page resilient to a partial response while respecting explicit order.
    Object.entries(deviceMap).forEach(([id, device]) => {
        if (!knownIds.has(String(id))) devices.push(device);
    });
    const deviceStatusElement = document.getElementById('device-status');
    const deviceIcons = {
        desktop: '🖥️',
        laptop: '💻',
        phone: '📱',
        tablet: '',
        watch: '⌚',
        server: '▤',
        game: '🎮',
        other: '◇',
        bilibili: ''
    };

    if (deviceStatusElement?.classList.contains('device-grid')) {
        const timeout = Number(metadata?.status?.device_timeout || 150);
        const now = Date.now() / 1000;
        const existingCards = new Map(
            [...deviceStatusElement.querySelectorAll(':scope > .device-card[data-device-id]')]
                .map((card) => [card.dataset.deviceId, card])
        );
        const activeIds = new Set(devices.map((device) => String(device.id)));
        existingCards.forEach((card, deviceId) => {
            if (!activeIds.has(deviceId)) card.remove();
        });
        deviceStatusElement.querySelector('.device-grid__empty')?.remove();

        devices.forEach((device, index) => {
            const deviceId = String(device.id);
            let card = existingCards.get(deviceId);
            if (card) {
                updateDeviceCard(card, device, index, timeout, now, deviceIcons);
            } else {
                card = createDeviceCard(device, index, timeout, now, deviceIcons);
            }
            const currentAtIndex = deviceStatusElement.children[index];
            if (currentAtIndex !== card) deviceStatusElement.insertBefore(card, currentAtIndex || null);
        });

        if (!devices.length) {
            const empty = document.createElement('div');
            empty.className = 'device-grid__empty';
            empty.textContent = '还没有公开设备。启动客户端后，设备卡片会自动出现在这里。';
            deviceStatusElement.append(empty);
        }
        const deviceCount = document.getElementById('device-count');
        setTextIfChanged(deviceCount, `${devices.length} 台设备`);
    } else if (deviceStatusElement) {
        var deviceStatus = '<hr/><b><p class="device-status-title"><i>Device</i> Status</p></b>';
        for (let device of devices) {
            let device_status;
            const escapedAppName = escapeHtml(device.status || '...');
            if (device.using) {
                const jsShowName = escapeJs(device.show_name);
                const jsAppName = escapeJs(device.status || '...');
                const jsCode = `alert('${jsShowName}: \\n${jsAppName}\\n${getFormattedTime(new Date(device.last_updated * 1000))}')`;
                const escapedJsCode = escapeHtml(jsCode);

                device_status = `
<a
    class="awake"
    title="${escapedAppName}"
    href="javascript:${escapedJsCode}">
${sliceText(escapedAppName, metadata.status.device_slice).replaceAll('\n', ' <br/>\n')}
</a>`;
            } else {
                device_status = `
<a
    class="sleeping"
    title="${escapedAppName}">
${sliceText(escapedAppName, metadata.status.device_slice).replaceAll('\n', ' <br/>\n')}
</a>`
            }
            const iconKey = device.profile?.icon_key;
            const icon = deviceIcons[iconKey] || deviceIcons.other;
            const iconMarkup = iconKey === 'bilibili'
                ? '<span class="bilibili-tv-icon" aria-hidden="true"></span>'
                : icon;
            deviceStatus += `${iconMarkup} ${escapeHtml(device.show_name)}: ${device_status} <br/>`;
        }
        if (devices.length === 0) deviceStatus = '';
        deviceStatusElement.innerHTML = deviceStatus;
    }

    // 更新最后更新时间
    const timenow = getFormattedTime(new Date());
    const last_updated = getFormattedTime(new Date(data.last_updated * 1000));
    if (lastUpdatedElement) {
        lastUpdatedElement.innerHTML = `
最后更新:
<a class="awake"
href="javascript:alert('浏览器最后更新时间: ${timenow}\\n数据最后更新时间: ${last_updated}')">
${last_updated}
</a>`;
    }

    if (visitMetric?.enabled) {
        const metricContainer = document.getElementById('visit-metric');
        const metricLabel = document.getElementById('visit-metric-label');
        const metricValue = document.getElementById('visit-metric-value');
        if (metricContainer) metricContainer.dataset.mode = visitMetric.mode;
        if (metricLabel) metricLabel.textContent = visitMetric.label;
        if (metricValue) metricValue.textContent = String(visitMetric.value);
    }
}

// 全局变量 - 重要：保证所有函数可访问
let evtSource = null;
let reconnectInProgress = false;
let countdownInterval = null;
let delayInterval = null;
let connectionCheckTimer = null;
let lastEventTime = Date.now();
let connectionAttempts = 0;
let firstError = true; // 是否为 SSR 第一次出错 (如是则激活 Vercel 部署检测)
const maxReconnectDelay = 30000; // 最大重连延迟时间为 30 秒

// 重连函数
function reconnectWithDelay(delay) {
    if (reconnectInProgress) {
        console.log('[SSE] 已经在重连过程中，忽略此次请求');
        return;
    }

    reconnectInProgress = true;
    console.log(`[SSE] 安排在 ${delay / 1000} 秒后重连`);

    // 清除可能存在的倒计时
    if (countdownInterval) {
        clearInterval(countdownInterval);
    }

    // 更新UI状态
    const statusElement = document.getElementById('status');
    if (statusElement) {
        statusElement.textContent = '[!错误!]';
        document.getElementById('additional-info').textContent = '与服务器的连接已断开，正在尝试重新连接...';
        let last_status = statusElement.classList.item(0);
        statusElement.classList.remove(last_status);
        statusElement.classList.add('error');
    }

    // 添加倒计时更新
    let remainingSeconds = Math.floor(delay / 1000);
    const lastUpdatedElement = document.getElementById('last-updated');
    if (lastUpdatedElement) {
        lastUpdatedElement.innerHTML = `连接服务器失败，${remainingSeconds} 秒后重新连接... <a href="javascript:reconnectNow();" target="_self" style="color: rgb(0, 255, 0);">立即重连</a>`;
    }

    countdownInterval = setInterval(() => {
        remainingSeconds--;
        if (remainingSeconds > 0 && lastUpdatedElement) {
            lastUpdatedElement.innerHTML = `连接服务器失败，${remainingSeconds} 秒后重新连接... <a href="javascript:reconnectNow();" target="_self" style="color: rgb(0, 255, 0);">立即重连</a>`;
        } else if (remainingSeconds <= 0) {
            clearInterval(countdownInterval);
        }
    }, 1000);

    delayInterval = setTimeout(() => {
        if (reconnectInProgress) {
            console.log('[SSE] 开始重连...');
            clearInterval(countdownInterval); // 清除倒计时
            setupEventSource();
            reconnectInProgress = false;
        }
    }, delay);
}

// 立即重连函数
window.reconnectNow = function () {
    console.log('[SSE] 用户选择立即重连');
    clearInterval(delayInterval); // 清除当前倒计时
    clearInterval(countdownInterval);
    connectionAttempts = 0; // 重置重连计数
    setupEventSource(); // 立即尝试重新连接
    reconnectInProgress = false;
}


// 建立SSE连接
function setupEventSource() {
    // 重置重连状态
    reconnectInProgress = false;

    // 清除可能存在的倒计时
    if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
    }

    // 清除旧的定时器
    if (connectionCheckTimer) {
        clearTimeout(connectionCheckTimer);
        connectionCheckTimer = null;
    }

    // 更新UI状态
    const statusElement = document.getElementById('status');
    const lastUpdatedElement = document.getElementById('last-updated');
    if (lastUpdatedElement) {
        lastUpdatedElement.innerHTML = `正在连接服务器... <a href="javascript:location.reload();" target="_self" style="color: rgb(0, 255, 0);">刷新页面</a>`;
    }

    // 关闭旧连接
    if (evtSource) {
        evtSource.close();
    }

    // 创建新连接
    evtSource = new EventSource('/api/status/events');

    // 监听连接打开事件
    evtSource.onopen = function () {
        console.log('[SSE] 连接已建立');
        connectionAttempts = 0; // 重置重连计数
        lastEventTime = Date.now(); // 初始化最后事件时间
    };

    // 监听更新事件
    evtSource.addEventListener('update', function (event) {
        lastEventTime = Date.now(); // 更新最后收到消息的时间

        const data = JSON.parse(event.data);
        console.log(`[SSE] [#${event.lastEventId}] 收到数据更新:`, data);

        if (!metadata) {
            getMetadata();
        }

        // 处理更新数据
        if (data.success) {
            updateDeviceStatus(data);
            window.dispatchEvent(new CustomEvent('alive:update', { detail: data }));
        } else {
            if (statusElement) {
                statusElement.textContent = '[!错误!]';
                document.getElementById('additional-info').textContent = data.details || '未知错误';
                let last_status = statusElement.classList.item(0);
                statusElement.classList.remove(last_status);
                statusElement.classList.add('error');
            }
        }
    });

    // 监听心跳事件
    evtSource.addEventListener('heartbeat', function (event) {
        console.log(`[SSE] [#${event.lastEventId}] 收到心跳包`);
        lastEventTime = Date.now(); // 更新最后收到消息的时间
    });

    // 错误处理 (定时重连 / 回退)
    evtSource.onerror = async function (e) {
        console.error(`[SSE] 连接错误: ${e}`);
        evtSource.close();

        // 如是第一次错误, 检查是否为 Vercel 部署
        if (firstError) {
            const isVercel = await checkVercelDeploy();
            if (isVercel === 1) {
                // 如是，清除所有定时器, 并回退到原始轮询函数
                if (countdownInterval) {
                    clearInterval(countdownInterval);
                    countdownInterval = null;
                }
                if (connectionCheckTimer) {
                    clearTimeout(connectionCheckTimer);
                    connectionCheckTimer = null;
                }
                update();
                return;
            } else if (isVercel === 0) {
                // 如不是 (非错误), 以后错误跳过检查
                firstError = false;
            }
            // 如请求错误, 下次继续检查
        }


        // 计算重连延迟时间 (指数退避)
        const reconnectDelay = Math.min(1000 * Math.pow(2, connectionAttempts), maxReconnectDelay);
        connectionAttempts++;

        // 使用统一重连函数
        reconnectWithDelay(reconnectDelay);
    };

    // 设置长时间未收到消息的检测
    function checkConnectionStatus() {
        const currentTime = Date.now();
        const elapsedTime = currentTime - lastEventTime;

        // 只有在连接正常但长时间未收到消息时才触发重连
        if (elapsedTime > 120 * 1000 && !reconnectInProgress) {
            console.warn('[SSE] 长时间未收到服务器消息，正在重新连接...');
            evtSource.close();

            // 使用与onerror相同的重连逻辑
            const reconnectDelay = Math.min(1000 * Math.pow(2, connectionAttempts), maxReconnectDelay);
            connectionAttempts++;
            reconnectWithDelay(reconnectDelay);
        }

        // 仅当没有正在进行的重连时才设置下一次检查
        if (!reconnectInProgress) {
            connectionCheckTimer = setTimeout(checkConnectionStatus, 10000);
        }
    }

    // 启动连接状态检查
    connectionCheckTimer = setTimeout(checkConnectionStatus, 10000);

    // 在页面卸载时关闭连接
    window.addEventListener('beforeunload', function () {
        if (evtSource) {
            evtSource.close();
        }
    });
}

// 初始化SSE连接或回退到轮询
document.addEventListener('DOMContentLoaded', function () {
    try {
        // 获取元数据
        fetch('/api/meta', { timeout: 10000 })
            .then((response) => response.json())
            .then((data) => {
                window.metadata = data;
                lastEventTime = Date.now();
                connectionAttempts = 0;

                // 检查浏览器是否支持SSE
                if (typeof (EventSource) !== "undefined") {
                    console.log('[SSE] 浏览器支持SSE，开始建立连接...');
                    // 初始建立连接
                    setupEventSource();
                } else {
                    // 浏览器不支持SSE，回退到轮询方案
                    console.log('[SSE] 浏览器不支持SSE，回退到轮询方案');
                    update();
                }
            })
    } catch (e) {
        alert(`请求元数据错误: ${e}, 请刷新页面`);
    }

});

// 原始轮询函数 (仅作为后备方案)
async function update() {
    let refresh_time = metadata.status.refresh_interval || 5000;
    while (true) {
        if (document.visibilityState == 'visible') {
            console.log('[Update] 页面可见，更新中...');
            let success_flag = true;
            let errorinfo = '';
            const statusElement = document.getElementById('status');
            // --- show updating
            document.getElementById('last-updated').innerHTML = `正在更新状态, 请稍候... <a href="javascript:location.reload();" target="_self" style="color: rgb(0, 255, 0);">刷新页面</a>`;
            // fetch data
            fetch('/api/status/query', { timeout: 10000 })
                .then(response => response.json())
                .then(async (data) => {
                    console.log(`[Update] 返回: ${data}`);
                    if (data.success) {
                        updateDeviceStatus(data);
                        window.dispatchEvent(new CustomEvent('alive:update', { detail: data }));
                    } else {
                        errorinfo = data.details || '未知错误';
                        success_flag = false;
                    }
                })
                .catch(error => {
                    errorinfo = error;
                    success_flag = false;
                });
            // 出错时显示
            if (!success_flag) {
                statusElement.textContent = '[!错误!]';
                document.getElementById('additional-info').textContent = errorinfo;
                last_status = statusElement.classList.item(0);
                statusElement.classList.remove(last_status);
                statusElement.classList.add('error');
            }
        } else {
            console.log('[Update] 页面不可见，跳过更新');
        }

        await sleep(refresh_time);
    }
}
