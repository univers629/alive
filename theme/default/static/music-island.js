(() => {
    const root = document.getElementById('music-island');
    if (!root) return;

    const elements = {
        summary: root.querySelector('.music-island__summary'),
        cover: root.querySelector('.music-island__cover'),
        title: root.querySelector('.music-island__title'),
        artist: root.querySelector('.music-island__artist'),
        speaker: root.querySelector('.music-island__speaker'),
        app: root.querySelector('.music-island__app'),
        appGlyph: root.querySelector('.music-island__app-glyph'),
        appIcon: root.querySelector('.music-island__app-icon'),
        progress: root.querySelector('.music-island__progress'),
        progressFill: root.querySelector('.music-island__progress-fill'),
        elapsed: root.querySelector('.music-island__elapsed'),
        duration: root.querySelector('.music-island__duration'),
        currentLyric: root.querySelector('.music-island__current-lyric'),
        ownerState: root.querySelector('.music-island__owner-state'),
        join: root.querySelector('.music-island__join'),
        audio: root.querySelector('.music-island__audio')
    };

    const PLAYER_ICONS = {
        'media-player': { glyph: '▶', label: 'Windows 媒体播放器' },
        'windows-media-player': { glyph: 'W', label: 'Windows Media Player' },
        groove: { glyph: '♫', label: 'Groove 音乐' },
        cloudmusic: { glyph: '♬', label: '网易云音乐' },
        saltplayer: { glyph: 'S', label: 'Salt Player for Windows' },
        spotify: { glyph: '●', label: 'Spotify' },
        foobar2000: { glyph: 'ƒ', label: 'foobar2000' }
    };

    let state = null;
    let joined = false;
    let lyricIndex = -1;
    let loadedAudioUrl = '';
    let playbackUnlocked = false;
    let playBlocked = false;
    let latestStateUpdatedAt = 0;

    function setExpanded(expanded) {
        root.classList.toggle('is-expanded', expanded);
        document.body.classList.toggle('music-island-expanded', expanded);
        elements.summary.setAttribute('aria-expanded', String(expanded));
        elements.summary.title = expanded ? '收起当前音乐' : '展开当前音乐';
    }

    elements.summary.addEventListener('click', () => {
        setExpanded(!root.classList.contains('is-expanded'));
    });

    elements.summary.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            setExpanded(!root.classList.contains('is-expanded'));
        } else if (event.key === 'Escape') {
            setExpanded(false);
        }
    });

    function formatTime(value) {
        const seconds = Math.max(0, Math.floor(Number(value) || 0));
        return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    }

    function normalizedLyrics() {
        if (!state || !Array.isArray(state.lyrics)) return [];
        return state.lyrics
            .filter((line) => line && Number.isFinite(Number(line.time)))
            .map((line) => ({
                time: Number(line.time),
                text: String(line.text || '').trim(),
                translation: String(line.translation || '').trim()
            }))
            .sort((left, right) => left.time - right.time);
    }

    function lyricsSignature(lyrics) {
        if (!Array.isArray(lyrics)) return '';
        return lyrics.map((line) => [
            Number(line?.time || 0),
            String(line?.text || ''),
            String(line?.translation || '')
        ].join('\u0000')).join('\u0001');
    }

    function updateLyric(position) {
        const lyrics = normalizedLyrics();
        let nextIndex = -1;
        for (let index = 0; index < lyrics.length; index += 1) {
            if (lyrics[index].time <= position + 0.08) nextIndex = index;
            else break;
        }
        if (nextIndex === lyricIndex) return;
        lyricIndex = nextIndex;
        const lyric = lyrics[nextIndex];
        const text = lyric?.text || (state?.playing ? '暂无同步歌词' : '播放已暂停');
        elements.currentLyric.textContent = lyric?.translation
            ? `${text}  ·  ${lyric.translation}`
            : text;
        elements.currentLyric.classList.remove('is-changing');
        void elements.currentLyric.offsetWidth;
        elements.currentLyric.classList.add('is-changing');
    }

    function updateProgress() {
        if (!state || root.hidden) return;
        if (Number(state.expires_at || 0) > 0 && Date.now() / 1000 > Number(state.expires_at)) {
            setState(null, true);
            return;
        }
        // Playback state is kept alive by the reporter heartbeat. We deliberately
        // do not infer or synchronize the owner's precise position for visitors.
        const position = joined ? Number(elements.audio.currentTime || 0) : Number(state.position || 0);
        const duration = Number(elements.audio.duration || state.duration || 0);
        const fraction = duration > 0 ? Math.min(position / duration, 1) : 0;
        const percent = Math.round(fraction * 100);
        elements.progressFill.style.width = `${fraction * 100}%`;
        elements.progress.setAttribute('aria-valuenow', String(percent));
        elements.elapsed.textContent = formatTime(position);
        elements.duration.textContent = formatTime(duration);
        updateLyric(position);
    }

    function setCover(url) {
        const coverUrl = String(url || '');
        root.classList.toggle('has-cover', Boolean(coverUrl));
        if (coverUrl) elements.cover.src = coverUrl;
        else elements.cover.removeAttribute('src');
        elements.cover.alt = coverUrl && state ? `${state.title} 的封面` : '';
    }

    function setPlayerIcon(iconKey, reportedName, iconUrl, sourceMode) {
        const safeKey = Object.hasOwn(PLAYER_ICONS, iconKey) ? iconKey : 'media-player';
        const icon = PLAYER_ICONS[safeKey];
        const label = String(reportedName || icon.label);
        root.dataset.player = safeKey;
        const uploadedUrl = String(iconUrl || '');
        // The bundled NetEase icon is only used on the netease-api chain (a
        // song ID was resolved). Local-upload and metadata-only chains keep
        // the default glyph even when the reporting player is NetEase.
        const bundledUrl = safeKey === 'saltplayer'
            ? root.dataset.saltplayerIcon || ''
            : (safeKey === 'cloudmusic' && sourceMode === 'netease-api'
                ? root.dataset.neteaseIcon || '' : '');
        const shownUrl = uploadedUrl || bundledUrl;
        root.classList.toggle('has-player-icon', Boolean(shownUrl));
        elements.appGlyph.textContent = icon.glyph;
        if (shownUrl) elements.appIcon.src = shownUrl;
        else elements.appIcon.removeAttribute('src');
        elements.appIcon.hidden = !shownUrl;
        elements.appIcon.alt = label;
        elements.app.title = label;
        elements.app.setAttribute('aria-label', `音乐应用：${label}`);
    }

    function updateJoinButton(message = '') {
        elements.join.disabled = !state?.audio_url && !joined;
        elements.join.textContent = joined ? '退出同听' : '一起听';
        const speakerLabel = joined ? '网页已开启一起听' : '网页未开启一起听';
        elements.speaker.setAttribute('aria-label', speakerLabel);
        elements.speaker.title = speakerLabel;
        if (message) {
            elements.ownerState.textContent = message;
        } else if (joined && !state?.audio_url) {
            elements.ownerState.textContent = '已开启一起听，等待下一首可用音源';
        } else if (!state?.audio_url) {
            elements.ownerState.textContent = '只展示状态，未匹配到本地音源';
        } else if (joined) {
            elements.ownerState.textContent = state.playing ? '正在与机主同步收听' : '已同步，等待机主继续播放';
        } else {
            elements.ownerState.textContent = state.playing ? '机主正在播放' : '机主已暂停';
        }
    }

    function loadAudio(url) {
        const nextUrl = String(url || '');
        if (nextUrl === loadedAudioUrl) return;
        elements.audio.pause();
        loadedAudioUrl = nextUrl;
        if (nextUrl) {
            elements.audio.src = nextUrl;
            elements.audio.loop = true;
            elements.audio.load();
        } else {
            elements.audio.removeAttribute('src');
            elements.audio.load();
        }
    }

    function leaveTogether() {
        joined = false;
        elements.audio.pause();
        elements.audio.playbackRate = 1;
        root.classList.remove('is-listening');
        updateJoinButton();
    }

    function setState(nextState, allowInactive = false) {
        const updatedAt = Number(nextState?.updated_at || 0);
        if (updatedAt > 0 && updatedAt < latestStateUpdatedAt) return;
        if (!nextState || !nextState.active || !nextState.title) {
            // A delayed poll must not blank a still-valid SSE state during a
            // song switch.  Expiry is handled locally below when it is real.
            if (!allowInactive && state && Number(state.expires_at || 0) > Date.now() / 1000) return;
            state = null;
            document.body.classList.remove('music-island-visible');
            setExpanded(false);
            elements.audio.pause();
            elements.audio.playbackRate = 1;
            loadAudio('');
            root.hidden = true;
            return;
        }

        const previousSong = state
            ? `${state.source_id || ''}|${state.title || ''}|${state.artist || ''}`
            : '';
        const previousLyrics = lyricsSignature(state?.lyrics);
        state = nextState;
        latestStateUpdatedAt = Math.max(latestStateUpdatedAt, updatedAt);
        const nextSong = `${state.source_id || ''}|${state.title || ''}|${state.artist || ''}`;
        const lyricsChanged = lyricsSignature(state.lyrics) !== previousLyrics;
        document.body.classList.add('music-island-visible');
        root.hidden = false;
        root.classList.toggle('is-playing', Boolean(state.playing));
        elements.title.textContent = state.title || '未知歌曲';
        elements.artist.textContent = state.artist || '未知艺术家';
        setCover(state.cover_url);
        setPlayerIcon(state.player_icon, state.player_name, state.player_icon_url, state.source_mode);

        if (nextSong !== previousSong || String(state.audio_url || '') !== loadedAudioUrl) {
            loadAudio(state.audio_url);
            if (joined && playbackUnlocked && state.audio_url) {
                elements.audio.play().catch(() => {
                    playBlocked = true;
                    updateJoinButton('浏览器阻止自动播放新歌，请重新点击“一起听”');
                });
            }
        }

        if (nextSong !== previousSong || lyricsChanged) lyricIndex = -1;
        updateJoinButton();
        updateProgress();
    }

    elements.cover.addEventListener('error', () => {
        root.classList.remove('has-cover');
        elements.cover.removeAttribute('src');
    });

    elements.appIcon.addEventListener('error', () => {
        root.classList.remove('has-player-icon');
        elements.appIcon.hidden = true;
        elements.appIcon.removeAttribute('src');
    });

    elements.join.addEventListener('click', (event) => {
        event.stopPropagation();
        if (joined) {
            leaveTogether();
            return;
        }
        if (!state?.audio_url) return;

        joined = true;
        playBlocked = false;
        elements.audio.preload = 'auto';
        elements.audio.preservesPitch = true;
        root.classList.add('is-listening');
        updateJoinButton();
        // Keep play() in the direct click call stack so browser autoplay policy
        // recognizes this as an explicit visitor action.
        const playAttempt = elements.audio.play();
        playAttempt.then(() => {
            playbackUnlocked = true;
            playBlocked = false;
            updateJoinButton();
        }).catch((error) => {
            console.warn('[MusicIsland] 浏览器暂未允许播放音频', error);
            joined = false;
            playBlocked = true;
            root.classList.remove('is-listening');
            elements.audio.pause();
            updateJoinButton('浏览器阻止播放，请再次点击“一起听”');
        });
    });

    elements.audio.addEventListener('error', () => {
        elements.audio.pause();
        elements.audio.playbackRate = 1;
        updateJoinButton('当前音源不可用，将在切歌后自动重试');
    });

    elements.audio.addEventListener('waiting', () => {
        if (joined) updateJoinButton('网络缓冲中');
    });

    elements.audio.addEventListener('playing', () => {
        if (joined) updateJoinButton();
    });

    window.addEventListener('alive:update', (event) => {
        if (event.detail?.music) setState(event.detail.music);
    });

    function refreshMusicState() {
        return fetch('/api/music/query', { cache: 'no-store' })
            .then((response) => response.json())
            .then((data) => setState(data.music))
            .catch((error) => console.warn('[MusicIsland] 音乐状态加载失败', error));
    }

    refreshMusicState();
    // SSE handles normal changes; this is only a fallback for buffered proxies.
    window.setInterval(refreshMusicState, 1000);

    window.setInterval(updateProgress, 250);
})();
