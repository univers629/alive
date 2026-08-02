(() => {
  const root = document.getElementById('comment-wall');
  if (!root) return;

  const elements = {
    stage: document.getElementById('danmaku-stage'),
    toggle: document.getElementById('danmaku-toggle'),
    list: document.getElementById('comment-list'),
    count: document.getElementById('comment-count'),
    form: document.getElementById('comment-form'),
    nickname: document.getElementById('comment-nickname'),
    content: document.getElementById('comment-content'),
    color: document.getElementById('comment-color'),
    website: document.getElementById('comment-website'),
    status: document.getElementById('comment-status'),
    submit: document.querySelector('#comment-form button[type="submit"]'),
  };

  const colors = {
    violet: '#b6aaff',
    cyan: '#70ddff',
    rose: '#ff92ad',
    amber: '#ffd071',
    green: '#72e6ad',
  };
  const knownIds = new Set();
  let commentDisplayLimit = Number(root.dataset.displayLimit) || 8;
  let replayCount = Number(root.dataset.replayCount) || 1;
  let replayInterval = Number(root.dataset.replayInterval) || 30;
  let comments = [];
  let lane = 0;
  let replayTimer = null;
  let activeReplayInterval = null;
  let serverEnabled = root.dataset.serverEnabled === 'true';
  let danmakuEnabled = serverEnabled && localStorage.getItem('alive-danmaku') !== 'off';

  function setDanmakuEnabled(enabled) {
    danmakuEnabled = serverEnabled && enabled;
    localStorage.setItem('alive-danmaku', enabled ? 'on' : 'off');
    root.dataset.danmaku = danmakuEnabled ? 'on' : 'off';
    elements.stage.hidden = !danmakuEnabled;
    elements.toggle.disabled = !serverEnabled;
    elements.toggle.setAttribute('aria-pressed', String(danmakuEnabled));
    elements.toggle.lastChild.textContent = danmakuEnabled ? ' 弹幕开启' : ' 弹幕关闭';
    if (!danmakuEnabled) {
      elements.stage.querySelectorAll('.comment-wall__bullet').forEach((bullet) => bullet.remove());
    }
  }

  function commentTime(timestamp) {
    return new Intl.DateTimeFormat('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(new Date(Number(timestamp) * 1000));
  }

  function renderComments() {
    elements.list.replaceChildren();
    if (!comments.length) {
      const empty = document.createElement('li');
      empty.className = 'comment-wall__empty';
      empty.textContent = '还没有留言，来做第一个留下痕迹的人吧。';
      elements.list.append(empty);
    } else {
      comments.forEach((comment) => {
        const item = document.createElement('li');
        item.className = 'comment-wall__item';
        if (comment.pinned) item.classList.add('comment-wall__item--pinned');
        item.style.setProperty('--item-color', colors[comment.color] || colors.violet);

        const avatar = document.createElement('span');
        avatar.className = 'comment-wall__avatar';
        avatar.setAttribute('aria-hidden', 'true');
        avatar.textContent = Array.from(comment.nickname || '匿')[0] || '匿';

        const copy = document.createElement('div');
        copy.className = 'comment-wall__copy';
        const nickname = document.createElement('strong');
        nickname.textContent = comment.nickname || '匿名访客';
        if (comment.pinned) {
          const pinned = document.createElement('span');
          pinned.className = 'comment-wall__pinned';
          pinned.textContent = '置顶';
          nickname.append(' ', pinned);
        }
        const content = document.createElement('p');
        content.textContent = comment.content;
        copy.append(nickname, content);

        const time = document.createElement('time');
        time.className = 'comment-wall__time';
        time.dateTime = new Date(Number(comment.created_at) * 1000).toISOString();
        time.textContent = commentTime(comment.created_at);

        item.append(avatar, copy, time);
        elements.list.append(item);
      });
    }
    elements.count.textContent = `展示 ${comments.length} / ${commentDisplayLimit} 条`;
  }

  function launchDanmaku(comment) {
    if (!danmakuEnabled || !comment) return;
    const bullet = document.createElement('span');
    const stageHeight = Math.max(80, elements.stage.clientHeight);
    const laneSpace = Math.max(42, stageHeight - 46);
    bullet.className = 'comment-wall__bullet comment-wall__bullet--rtl';
    bullet.style.top = `${8 + ((lane * 53 + Math.floor(Math.random() * 23)) % laneSpace)}px`;
    bullet.style.setProperty('--bullet-color', colors[comment.color] || colors.violet);
    bullet.style.setProperty('--flight-duration', `${13 + (Number(comment.id) % 5)}s`);

    const nickname = document.createElement('strong');
    nickname.textContent = comment.nickname || '匿名访客';
    const content = document.createElement('span');
    content.textContent = `：${comment.content}`;
    bullet.append(nickname, content);
    elements.stage.append(bullet);
    lane += 1;
    bullet.addEventListener('animationend', () => {
      bullet.remove();
    }, { once: true });
  }

  function replayDanmakuBatch() {
    if (!danmakuEnabled || !comments.length || document.hidden) return;
    const queue = [...comments].sort(() => Math.random() - .5).slice(0, replayCount);
    queue.forEach((comment, index) => {
      window.setTimeout(() => {
        launchDanmaku(comment);
      }, index * 700);
    });
  }

  function resetDanmakuTimer() {
    if (replayTimer && activeReplayInterval === replayInterval) return;
    if (replayTimer) window.clearInterval(replayTimer);
    replayTimer = window.setInterval(replayDanmakuBatch, replayInterval * 1000);
    activeReplayInterval = replayInterval;
  }

  function launchNewDanmaku(commentsToLaunch) {
    commentsToLaunch
      .sort((left, right) => Number(left.created_at) - Number(right.created_at))
      .forEach((comment, index) => {
        window.setTimeout(() => launchDanmaku(comment), index * 700);
      });
  }

  async function refreshComments() {
    if (document.hidden) return;
    try {
      const response = await fetch('/api/comments/query', {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      });
      if (!response.ok) throw new Error('评论读取失败');
      const payload = await response.json();
      serverEnabled = payload.danmaku_enabled !== false;
      commentDisplayLimit = Number(payload.comment_display_limit) || commentDisplayLimit;
      replayCount = Number(payload.danmaku_replay_count) || replayCount;
      replayInterval = Number(payload.danmaku_replay_interval) || replayInterval;
      resetDanmakuTimer();
      setDanmakuEnabled(localStorage.getItem('alive-danmaku') !== 'off');
      const incoming = (Array.isArray(payload.comments) ? payload.comments : []).slice(0, commentDisplayLimit);
      const newComments = incoming.filter((comment) => !knownIds.has(comment.id));
      incoming.forEach((comment) => knownIds.add(comment.id));
      comments = incoming;
      renderComments();
      if (newComments.length) launchNewDanmaku(newComments);
    } catch (error) {
      if (!comments.length) {
        elements.list.innerHTML = '<li class="comment-wall__empty">暂时无法读取评论，请稍后重试。</li>';
        elements.count.textContent = '连接失败';
      }
    }
  }

  elements.toggle.addEventListener('click', () => {
    setDanmakuEnabled(!danmakuEnabled);
  });

  elements.form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const content = elements.content.value.trim();
    if (!content) {
      elements.status.textContent = '先写下一句话吧';
      elements.status.classList.add('is-error');
      elements.content.focus();
      return;
    }

    elements.submit.disabled = true;
    elements.status.textContent = '正在发送…';
    elements.status.classList.remove('is-error');
    try {
      const response = await fetch('/api/comments/create', {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          nickname: elements.nickname.value.trim(),
          content,
          color: elements.color.value,
          website: elements.website.value,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message || '发送失败');
      elements.content.value = '';
      elements.status.textContent = '发送成功';
      if (payload.comment) {
        knownIds.add(payload.comment.id);
        comments = [...comments, payload.comment]
          .sort((left, right) => Number(right.pinned) - Number(left.pinned)
            || Number(right.created_at) - Number(left.created_at))
          .slice(0, commentDisplayLimit);
        renderComments();
        launchDanmaku(payload.comment);
      }
    } catch (error) {
      elements.status.textContent = error.message || '发送失败，请稍后再试';
      elements.status.classList.add('is-error');
    } finally {
      elements.submit.disabled = false;
    }
  });

  setDanmakuEnabled(danmakuEnabled);
  refreshComments();
  window.setInterval(refreshComments, 6000);
})();
