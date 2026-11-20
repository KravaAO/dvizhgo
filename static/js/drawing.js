(() => {
    const root = document.getElementById('drawingContent');
    const progress = document.getElementById('drawingProgress');
    const timer = document.getElementById('drawingTimer');
    const sound = createCountdownSound(document.getElementById('drawingSound'));
    const isHost = document.body.dataset.host === 'true';
    // Values that change on every poll; they update in place instead of
    // rebuilding the screen.
    const LIVE_FIELDS = ['time_left_ms', 'submitted_count', 'expected_count', 'votes_count', 'voters_count'];
    let lastKey = '', state = null;
    // The board survives re-renders of the same round, so polling or socket
    // updates never wipe a picture that is still being drawn.
    let board = null, boardRound = null;
    // Deadline on the monotonic clock; the server only sends "ms left".
    let deadlineAt = null, timeUpRound = null, lateRefreshRound = null;
    // Seconds whose countdown cue already sounded, reset every round.
    let cueRound = null, cuedSeconds = new Set();
    // The open full-screen picture viewer, if any.
    let viewer = null;
    // Autosave: the board revision last stored on the server (null = none
    // yet this round), whether the restore check has finished, and a save in
    // flight. A changed picture is saved every few seconds.
    const AUTOSAVE_MS = 3000;
    // Browsers cap keepalive requests (sent while the tab hides) at 64 KB.
    const KEEPALIVE_LIMIT = 60000;
    let savedRevision = null, draftReady = false, draftSaving = false, saveStatus = '';

    const el = (tag, text, cls) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; };
    async function send(url, body = {}, {keepalive = false} = {}) {
        const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body), keepalive});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Не вдалося виконати дію.');
        return data;
    }
    function button(text, fn, cls = 'drawing-button') {
        const b = el('button', text, cls); b.type = 'button';
        b.onclick = async () => { b.disabled = true; try { await fn(); } catch (error) { showToast(error.message, {type:'error'}); } finally { b.disabled = false; } };
        return b;
    }
    const svgIcon = paths => `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="square" stroke-linejoin="miter" aria-hidden="true" focusable="false">${paths}</svg>`;
    const ICONS = {
        download: svgIcon('<path d="M12 3v12"/><path d="M6.5 9.5 12 15l5.5-5.5"/><path d="M4 15v5h16v-5"/>'),
        link: svgIcon('<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3.2-3.2a4.5 4.5 0 0 0-6.4-6.4L11.6 6"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3.2 3.2a4.5 4.5 0 0 0 6.4 6.4l1.6-1.6"/>'),
        copied: svgIcon('<path d="m4.5 12.5 5 5 10-11"/>'),
    };
    function iconControl(node, icon, label) {
        node.className = 'drawing-icon-button';
        node.innerHTML = icon;
        node.setAttribute('aria-label', label);
        node.title = label;
        return node;
    }
    async function copyText(text) {
        if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return; }
        // Plain-HTTP fallback (e.g. a phone on the LAN dev server).
        const area = el('textarea'); area.value = text; area.setAttribute('readonly', '');
        area.style.cssText = 'position:fixed;top:0;left:0;opacity:0;';
        document.body.append(area); area.select();
        const ok = document.execCommand('copy'); area.remove();
        if (!ok) throw new Error('Не вдалося скопіювати посилання.');
    }
    function renderKey(next) {
        const stable = {...next};
        LIVE_FIELDS.forEach(field => delete stable[field]);
        return JSON.stringify(stable);
    }
    async function refresh() {
        try {
            const response = await fetch('/api/drawing/current', {cache:'no-store'});
            if (response.status === 404) { window.location.href = '/lobby'; return; }
            if (!response.ok) return;
            const next = await response.json();
            // The round can close a moment before this screen's own clock
            // reaches zero (the last drawer auto-submitted); still buzz.
            const closedAtDeadline = state && state.phase === 'drawing' && next.phase !== 'drawing'
                && next.round === state.round && deadlineAt !== null && deadlineAt - performance.now() < 1500;
            if (closedAtDeadline) countdownCue(0);
            state = next;
            deadlineAt = typeof next.time_left_ms === 'number' ? performance.now() + next.time_left_ms : null;
            const key = renderKey(next);
            if (key !== lastKey) { lastKey = key; render(); }
            updateProgress();
            tick();
        } catch (error) { console.error(error); }
    }
    const update = async (url, data = {}) => { await send(url, data); await refresh(); };

    function dropBoard() {
        if (!board) return;
        board.destroy();
        board = null;
        boardRound = null;
    }

    // Live "done / total" counter: pictures while drawing, votes while voting.
    function progressCounts() {
        if (!state) return null;
        if (state.phase === 'drawing' && typeof state.expected_count === 'number') {
            return {done:state.submitted_count, total:Math.max(state.expected_count, state.submitted_count), label:'надіслали'};
        }
        if (state.phase === 'voting' && typeof state.voters_count === 'number') {
            return {done:state.votes_count, total:Math.max(state.voters_count, state.votes_count), label:'проголосували'};
        }
        return null;
    }

    function progressBlock(compact = false) {
        const block = el('div', undefined, compact ? 'drawing-progress drawing-progress--compact' : 'drawing-progress');
        const count = el('strong');
        count.dataset.live = 'done';
        const total = el('span');
        total.dataset.live = 'total';
        const bar = el('div', undefined, 'drawing-progress-bar');
        const fill = el('i');
        fill.dataset.live = 'bar';
        bar.append(fill);
        block.append(count, total, bar);
        return block;
    }

    function updateProgress() {
        const counts = progressCounts();
        if (!counts) return;
        const complete = counts.total > 0 && counts.done >= counts.total;
        root.querySelectorAll('[data-live="done"]').forEach(node => { node.textContent = counts.done; });
        root.querySelectorAll('[data-live="total"]').forEach(node => { node.textContent = `/ ${counts.total} ${counts.label}`; });
        root.querySelectorAll('[data-live="bar"]').forEach(node => { node.style.width = `${counts.total ? counts.done / counts.total * 100 : 0}%`; });
        // Everyone has voted: nudge the host towards the next step.
        root.querySelectorAll('[data-live="ready"]').forEach(node => { node.classList.toggle('is-ready', complete); });
    }

    function confirmDialog({title, text, confirmLabel, cancelLabel = 'Скасувати'}) {
        return new Promise(resolve => {
            const backdrop = el('div', undefined, 'leave-modal-backdrop open');
            const dialog = el('section', undefined, 'leave-modal');
            dialog.setAttribute('role', 'dialog');
            dialog.setAttribute('aria-modal', 'true');
            dialog.setAttribute('aria-labelledby', 'drawingConfirmTitle');
            const heading = el('h2', title);
            heading.id = 'drawingConfirmTitle';
            const actions = el('div');
            const cancel = el('button', cancelLabel, 'leave-cancel'); cancel.type = 'button';
            const accept = el('button', confirmLabel, 'leave-confirm'); accept.type = 'button';
            actions.append(cancel, accept);
            dialog.append(el('div', 'ПІДТВЕРДЖЕННЯ', 'dv-micro'), heading, el('p', text), actions);
            backdrop.append(dialog);
            document.body.append(backdrop);
            const close = result => { document.removeEventListener('keydown', onKey); backdrop.remove(); resolve(result); };
            const onKey = event => { if (event.key === 'Escape') close(false); };
            document.addEventListener('keydown', onKey);
            cancel.onclick = () => close(false);
            accept.onclick = () => close(true);
            backdrop.onclick = event => { if (event.target === backdrop) close(false); };
            cancel.focus();
        });
    }

    async function endDrawingEarly() {
        const missing = Math.max(0, state.expected_count - state.submitted_count);
        const confirmed = await confirmDialog({
            title: 'Завершити малювання?',
            text: missing
                ? `Ще малюють: ${missing}. У голосування потрапить те, що вони встигли намалювати.`
                : 'Голосування відкриється одразу.',
            confirmLabel: 'Відкрити голосування',
        });
        if (confirmed) await update('/api/drawing/advance', {round:state.round, phase:'drawing'});
    }

    async function finishVoting() {
        const last = state.round === state.rounds;
        const missing = Math.max(0, state.voters_count - state.votes_count);
        if (missing) {
            const confirmed = await confirmDialog({
                title: last ? 'Показати результати?' : 'Наступний раунд?',
                text: `Ще не проголосували: ${missing}. Їхні голоси в цьому раунді не врахуються.`,
                confirmLabel: last ? 'Показати результати' : 'Наступний раунд',
            });
            if (!confirmed) return;
        }
        await update('/api/drawing/advance', {round:state.round, phase:'voting'});
    }

    function formatTime(ms) {
        const seconds = Math.ceil(Math.max(0, ms) / 1000);
        return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    }

    // Chime at 10 s, tick through the last 5 s, buzz at zero. Only people
    // still drawing hear it, plus the host screen that the room watches.
    function countdownCue(remaining) {
        if (!isHost && (state.submitted || timeUpRound === state.round)) return;
        if (cueRound !== state.round) { cueRound = state.round; cuedSeconds = new Set(); }
        const second = Math.ceil(remaining / 1000);
        let cue = null;
        if (second === 10) cue = 'warning';
        else if (second >= 2 && second <= 5) cue = 'tick';
        else if (second === 1) cue = 'lastTick';
        // Only right at the deadline, never on a page opened after it.
        else if (second <= 0 && remaining > -1000) cue = 'end';
        const key = Math.max(0, second);
        if (!cue || cuedSeconds.has(key)) return;
        cuedSeconds.add(key);
        sound.play(cue);
    }

    function tick() {
        const remaining = deadlineAt === null ? null : deadlineAt - performance.now();
        const counting = state && state.phase === 'drawing' && remaining !== null;
        timer.hidden = !counting;
        document.body.classList.toggle('drawing-page--timed', Boolean(counting));
        if (!counting) return;
        timer.textContent = `⏱ ${formatTime(remaining)}`;
        timer.classList.toggle('urgent', remaining <= 10000);
        countdownCue(remaining);
        if (remaining <= 0 && !isHost && !state.submitted && board && timeUpRound !== state.round) handleTimeUp();
        // Once the grace window has passed, ask the server to close the round.
        if (remaining <= -(state.submit_grace_ms + 500) && lateRefreshRound !== state.round) {
            lateRefreshRound = state.round;
            refresh();
        }
    }

    // Whatever is on the canvas goes in at time-up, a blank one included.
    async function handleTimeUp() {
        const round = state.round;
        timeUpRound = round;
        board.setDisabled(true);
        const image = board.toPng();
        const blank = board.isBlank();
        try {
            await send('/api/drawing/submit', {round, image, blank});
            showToast(blank ? 'Час вийшов — надіслано порожнє полотно.' : 'Час вийшов — малюнок надіслано!', {type:'success'});
        } catch (error) {
            // The last autosave still becomes the entry on the server.
            showToast(error.message, {type:'error'});
        }
        await refresh();
    }

    async function submitDrawing() {
        const image = board.toPng();
        const blank = board.isBlank();
        if (blank && !await confirmDialog({
            title: 'Порожнє полотно?',
            text: 'Його побачать інші учасники під час голосування. Змінити роботу після надсилання не можна.',
            confirmLabel: 'Надіслати порожнє',
        })) return;
        await update('/api/drawing/submit', {round:state.round, image, blank});
    }

    // ---- Autosave -------------------------------------------------------
    const SAVE_LABELS = {saving:'· ЗБЕРІГАЄМО…', saved:'· ЗБЕРЕЖЕНО ✓', error:'· НЕ ЗБЕРЕЖЕНО'};
    function setSaveStatus(value) {
        saveStatus = value;
        root.querySelectorAll('.draw-autosave').forEach(node => {
            node.textContent = SAVE_LABELS[value] || '';
            node.dataset.state = value;
        });
    }

    // A new round's board: bring back the autosaved picture after a reload,
    // otherwise save the (blank) canvas at once, so having the page open is
    // enough to take part in the round.
    async function startDraft(round) {
        savedRevision = null;
        draftReady = false;
        setSaveStatus('');
        try {
            const response = await fetch('/api/drawing/draft', {cache:'no-store'});
            const data = response.ok ? await response.json() : null;
            // Restore only into an untouched board of the same round.
            if (data && data.image && data.round === round && boardRound === round && board.revision() === 0) {
                await board.load(data.image);
                savedRevision = 0;
                setSaveStatus('saved');
                showToast('Малюнок відновлено.', {type:'info'});
            }
        } catch (error) { console.error(error); }
        if (boardRound !== round) return;
        draftReady = true;
        saveDraft();
    }

    async function saveDraft({keepalive = false} = {}) {
        if (!board || !draftReady || draftSaving || !state || state.phase !== 'drawing' || boardRound !== state.round) return;
        const revision = board.revision();
        if (revision === savedRevision) return;
        const round = boardRound;
        const body = {round, image:board.draftPng(), blank:board.isBlank()};
        draftSaving = true;
        setSaveStatus('saving');
        try {
            const tooBig = JSON.stringify(body).length > KEEPALIVE_LIMIT;
            await send('/api/drawing/draft', body, {keepalive: keepalive && !tooBig});
            if (boardRound === round) { savedRevision = revision; setSaveStatus('saved'); }
        } catch (error) {
            if (boardRound === round) setSaveStatus('error');
        } finally {
            draftSaving = false;
        }
    }

    function renderWorkspace() {
        let fresh = false;
        if (!board || boardRound !== state.round) {
            dropBoard();
            board = createDrawingBoard();
            boardRound = state.round;
            fresh = true;
        }
        const workspace = el('section', undefined, 'draw-workspace');
        const top = el('div', undefined, 'draw-topbar');
        const prompt = el('div', undefined, 'draw-prompt');
        const eyebrow = el('span', `РАУНД ${state.round} / ${state.rounds} · ТЕМА `, 'drawing-eyebrow');
        const autosave = el('span', SAVE_LABELS[saveStatus] || '', 'draw-autosave');
        autosave.dataset.state = saveStatus;
        // Visual reassurance only; announcing it every few seconds would be noise.
        autosave.setAttribute('aria-hidden', 'true');
        eyebrow.append(autosave);
        prompt.append(eyebrow, el('h1', state.prompt));
        top.append(prompt, button('Надіслати ✓', submitDrawing, 'drawing-button draw-submit'));
        workspace.append(top, board.element);
        root.append(workspace);
        if (fresh) startDraft(state.round);
    }

    // A host button whose label shortens on phones; the full text stays
    // the accessible name.
    function hostButton(long, short, fn, cls) {
        const b = button('', fn, `${cls} drawing-host-action`);
        b.setAttribute('aria-label', long);
        b.append(el('span', long, 'label-long'), el('span', short, 'label-short'));
        return b;
    }

    function hostAction() {
        if (!isHost) return null;
        if (state.phase === 'drawing') return hostButton('Завершити малювання', 'Завершити', endDrawingEarly, 'drawing-tool');
        if (state.phase === 'voting') {
            const last = state.round === state.rounds;
            const next = hostButton(last ? 'Показати результати →' : 'Наступний раунд →', last ? 'Фінал →' : 'Далі →', finishVoting, 'drawing-button');
            next.dataset.live = 'ready';
            return next;
        }
        return hostButton('Повернутися в лобі', 'У лобі', () => update('/api/drawing/advance', {round:state.round, phase:state.phase}), 'drawing-button');
    }

    // Every screen except the canvas: round and topic on the left, the
    // host's next step always in the top-right corner.
    function stage(eyebrow, title) {
        const bar = el('div', undefined, 'draw-topbar drawing-stagebar');
        const prompt = el('div', undefined, 'draw-prompt');
        prompt.append(el('span', eyebrow, 'drawing-eyebrow'), el('h1', title));
        bar.append(prompt);
        const action = hostAction();
        if (action) bar.append(action);
        const body = el('div', undefined, 'drawing-content');
        root.append(bar, body);
        return body;
    }

    const workLabel = i => `Робота ${i + 1}`;
    const canVoteFor = work => state.can_vote && !work.own;

    async function castVote(work) {
        await send('/api/drawing/vote', {round:state.round, drawing_id:work.id});
        showToast('Голос зараховано!', {type:'success'});
        await refresh();
    }

    function pictureButton(url, label, onOpen) {
        const open = el('button', undefined, 'drawing-card-image');
        open.type = 'button';
        open.setAttribute('aria-label', `${label}: відкрити на весь екран`);
        const img = document.createElement('img');
        img.src = url; img.alt = label; img.loading = 'lazy'; img.decoding = 'async';
        open.append(img);
        open.onclick = onOpen;
        return open;
    }

    // Full-screen look at one picture, with arrows (or a swipe) to the rest.
    function openViewer(index) {
        closeViewer();
        const works = state.drawings;
        const results = state.phase === 'results';
        const backdrop = el('div', undefined, 'drawing-viewer');
        backdrop.setAttribute('role', 'dialog');
        backdrop.setAttribute('aria-modal', 'true');
        backdrop.setAttribute('aria-label', 'Перегляд роботи');
        const close = el('button', '✕', 'drawing-viewer-close');
        const prev = el('button', '←', 'drawing-viewer-nav drawing-viewer-prev');
        const next = el('button', '→', 'drawing-viewer-nav drawing-viewer-next');
        [close, prev, next].forEach(b => { b.type = 'button'; });
        close.setAttribute('aria-label', 'Закрити');
        prev.setAttribute('aria-label', 'Попередня робота');
        next.setAttribute('aria-label', 'Наступна робота');
        const figure = el('figure');
        const img = document.createElement('img');
        const caption = el('figcaption');
        figure.append(img, caption);
        const actions = el('div', undefined, 'drawing-viewer-actions');
        backdrop.append(close, prev, figure, next, actions);
        let current = index;
        function show(i) {
            current = (i + works.length) % works.length;
            const work = works[current];
            img.src = work.url;
            img.alt = results ? `Малюнок: ${work.prompt}` : workLabel(current);
            const notes = results ? [work.author, `Раунд ${work.round}`, work.prompt] : [`${workLabel(current)} з ${works.length}`];
            if (work.blank) notes.push('Порожнє полотно');
            if (!results && work.own) notes.push('Ваша робота');
            if (!results && state.voted_for === work.id) notes.push('★ Ваш голос');
            caption.textContent = notes.join(' · ');
            actions.replaceChildren();
            if (!results && canVoteFor(work)) actions.append(button('Голосувати за цю роботу', () => castVote(work), 'drawing-button drawing-vote-button'));
        }
        prev.hidden = next.hidden = works.length < 2;
        prev.onclick = () => show(current - 1);
        next.onclick = () => show(current + 1);
        close.onclick = () => closeViewer();
        backdrop.onclick = event => { if (event.target === backdrop) closeViewer(); };
        let swipeFrom = null;
        figure.addEventListener('pointerdown', event => { swipeFrom = event.clientX; });
        figure.addEventListener('pointerup', event => {
            if (swipeFrom === null || works.length < 2) return;
            const dx = event.clientX - swipeFrom;
            swipeFrom = null;
            if (Math.abs(dx) > 50) show(current + (dx < 0 ? 1 : -1));
        });
        const onKey = event => {
            if (event.key === 'Escape') closeViewer();
            else if (event.key === 'ArrowLeft' && works.length > 1) show(current - 1);
            else if (event.key === 'ArrowRight' && works.length > 1) show(current + 1);
        };
        const opener = document.activeElement;
        viewer = () => {
            document.removeEventListener('keydown', onKey);
            backdrop.remove();
            document.body.classList.remove('drawing-viewer-open');
            if (opener && opener.isConnected) opener.focus();
        };
        document.addEventListener('keydown', onKey);
        document.body.append(backdrop);
        document.body.classList.add('drawing-viewer-open');
        show(index);
        close.focus();
    }

    function closeViewer() {
        if (!viewer) return;
        const close = viewer;
        viewer = null;
        close();
    }

    function renderWaiting(body) {
        if (isHost) body.append(el('p', 'Голосування відкриється само, щойно всі надішлють малюнки або вийде час.'));
        else if (state.submitted) body.append(el('p', 'Ваш малюнок надіслано ✓ Голосування почнеться, коли всі закінчать.'));
        else body.append(el('p', 'Час вийшов. Голосування почнеться, коли всі закінчать.'));
        body.append(progressBlock());
    }

    function renderVoting(body) {
        const status = el('div', undefined, 'drawing-vote-status');
        let hint;
        if (isHost) hint = 'Роботи анонімні до кінця гри. Коли всі проголосують, переходьте далі.';
        else if (state.voted) hint = 'Ваш голос зараховано ✓ Чекаємо на інших.';
        else if (state.can_vote) hint = 'Оберіть найкращу чужу роботу. Голос один — змінити його не можна.';
        else hint = 'У цьому раунді немає чужих робіт, за які можна проголосувати.';
        status.append(progressBlock(true), el('p', hint, 'drawing-vote-hint'));
        body.append(status);
        if (!state.drawings.length) { body.append(el('p', 'У цьому раунді немає надісланих робіт.')); return; }
        const grid = el('div', undefined, 'drawing-gallery drawing-gallery--vote');
        state.drawings.forEach((work, i) => {
            const voted = state.voted_for === work.id;
            const card = el('article', undefined, 'drawing-card');
            card.classList.toggle('is-own', work.own);
            card.classList.toggle('is-blank', work.blank);
            card.classList.toggle('is-voted', voted);
            card.classList.toggle('is-dimmed', state.voted && !voted);
            const foot = el('div', undefined, 'drawing-card-foot');
            foot.append(el('strong', workLabel(i)));
            if (work.blank) foot.append(el('span', 'Порожнє полотно', 'drawing-badge drawing-badge--blank'));
            if (work.own) foot.append(el('span', 'Ваша робота', 'drawing-badge'));
            if (voted) foot.append(el('span', '★ Ваш голос', 'drawing-badge drawing-badge--vote'));
            card.append(pictureButton(work.url, workLabel(i), () => openViewer(i)), foot);
            if (canVoteFor(work)) card.append(button('Голосувати', () => castVote(work), 'drawing-button drawing-vote-button'));
            grid.append(card);
        });
        body.append(grid);
    }

    function renderResults(body) {
        const winners = el('section', undefined, 'drawing-winners');
        state.winners.forEach(w => winners.append(el('p', `${w.round}. ${w.prompt} — ${w.names.length ? w.names.join(', ') : 'немає переможця'}`)));
        body.append(winners, el('h2', 'Усі роботи'), el('p', 'Роботи доступні за посиланням протягом 7 днів після надсилання.'));
        const grid = el('div', undefined, 'drawing-gallery');
        state.drawings.forEach((work, i) => {
            const card = el('article', undefined, 'drawing-card');
            card.classList.toggle('is-blank', work.blank);
            const download = iconControl(el('a'), ICONS.download, 'Завантажити малюнок');
            download.href = work.url; download.download = `malyunok-${work.round}.png`;
            const share = iconControl(button('', async () => {
                await copyText(new URL(work.url, location.href).href);
                showToast('Посилання скопійовано.', {type:'success'});
                share.innerHTML = ICONS.copied; share.classList.add('is-done');
                setTimeout(() => { share.innerHTML = ICONS.link; share.classList.remove('is-done'); }, 1600);
            }, ''), ICONS.link, 'Скопіювати посилання');
            const links = el('div', undefined, 'drawing-card-links');
            links.append(download, share);
            const caption = `Раунд ${work.round} · ${work.prompt}${work.blank ? ' · порожнє полотно' : ''}`;
            const info = el('div', undefined, 'drawing-card-info');
            info.append(el('strong', work.author), el('span', caption));
            const row = el('div', undefined, 'drawing-card-row');
            row.append(info, links);
            card.append(pictureButton(work.url, `Малюнок: ${work.prompt}`, () => openViewer(i)), row);
            grid.append(card);
        });
        body.append(grid);
    }

    function render() {
        closeViewer();
        progress.textContent = `РАУНД ${state.round} / ${state.rounds}`;
        root.replaceChildren();
        const timedOut = timeUpRound === state.round;
        const drawingNow = state.phase === 'drawing' && !isHost && !state.submitted && !timedOut;
        document.body.classList.toggle('drawing-page--workspace', drawingNow);
        document.body.classList.toggle('drawing-page--stage', !drawingNow);
        if (drawingNow) { renderWorkspace(); return; }
        dropBoard();
        const round = `РАУНД ${state.round} / ${state.rounds}`;
        if (state.phase === 'drawing') renderWaiting(stage(`${round} · МАЛЮЄМО`, state.prompt));
        else if (state.phase === 'voting') renderVoting(stage(`${round} · ГОЛОСУВАННЯ`, state.prompt));
        else renderResults(stage('ФІНАЛ', 'Ось наші переможці!'));
        updateProgress();
    }
    connectRoomSocket({drawing:refresh, state(s) { if (s.activity_type !== 'drawing') window.location.href = '/lobby'; }});
    refresh(); setInterval(refresh, 5000); setInterval(tick, 250); setInterval(saveDraft, AUTOSAVE_MS);
    // Leaving or switching away: store the latest picture straight away.
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') saveDraft({keepalive:true}); });
    window.addEventListener('pagehide', () => saveDraft({keepalive:true}));
})();
