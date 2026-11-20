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

    const el = (tag, text, cls) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; };
    async function send(url, body = {}) {
        const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Не вдалося виконати дію.');
        return data;
    }
    function button(text, fn, cls = 'drawing-button') {
        const b = el('button', text, cls); b.type = 'button';
        b.onclick = async () => { b.disabled = true; try { await fn(); } catch (error) { showToast(error.message, {type:'error'}); } finally { b.disabled = false; } };
        return b;
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
                ? `Ще малюють: ${missing}. Їхні роботи не потраплять у голосування цього раунду.`
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

    async function handleTimeUp() {
        const round = state.round;
        timeUpRound = round;
        board.setDisabled(true);
        if (board.isBlank()) {
            showToast('Час вийшов. Порожнє полотно не надсилається.', {type:'info'});
            render();
            return;
        }
        try {
            await send('/api/drawing/submit', {round, image:board.toPng()});
            showToast('Час вийшов — малюнок надіслано!', {type:'success'});
        } catch (error) {
            showToast(error.message, {type:'error'});
        }
        await refresh();
    }

    async function submitDrawing() {
        if (board.isBlank()) throw new Error('Спочатку намалюйте щось на полотні.');
        await update('/api/drawing/submit', {round:state.round, image:board.toPng()});
    }

    function renderWorkspace() {
        if (!board || boardRound !== state.round) {
            dropBoard();
            board = createDrawingBoard();
            boardRound = state.round;
        }
        const workspace = el('section', undefined, 'draw-workspace');
        const top = el('div', undefined, 'draw-topbar');
        const prompt = el('div', undefined, 'draw-prompt');
        prompt.append(el('span', `РАУНД ${state.round} / ${state.rounds} · ТЕМА`, 'drawing-eyebrow'), el('h1', state.prompt));
        top.append(prompt, button('Надіслати ✓', submitDrawing, 'drawing-button draw-submit'));
        workspace.append(top, board.element);
        root.append(workspace);
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
            card.classList.toggle('is-voted', voted);
            card.classList.toggle('is-dimmed', state.voted && !voted);
            const foot = el('div', undefined, 'drawing-card-foot');
            foot.append(el('strong', workLabel(i)));
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
            const download = el('a', 'Завантажити', 'drawing-tool'); download.href = work.url; download.download = 'malyunok.png';
            const share = button('Скопіювати посилання', async () => { await navigator.clipboard.writeText(new URL(work.url, location.href).href); showToast('Посилання скопійовано.', {type:'success'}); }, 'drawing-tool');
            const links = el('div', undefined, 'drawing-card-links');
            links.append(download, share);
            card.append(pictureButton(work.url, `Малюнок: ${work.prompt}`, () => openViewer(i)), el('strong', work.author), el('span', `Раунд ${work.round} · ${work.prompt}`), links);
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
    refresh(); setInterval(refresh, 5000); setInterval(tick, 250);
})();
