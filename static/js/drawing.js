(() => {
    const root = document.getElementById('drawingContent');
    const progress = document.getElementById('drawingProgress');
    const timer = document.getElementById('drawingTimer');
    const sound = createCountdownSound(document.getElementById('drawingSound'));
    const isHost = document.body.dataset.host === 'true';
    // Values that change on every poll; they update in place instead of
    // rebuilding the screen.
    const LIVE_FIELDS = ['time_left_ms', 'submitted_count', 'expected_count'];
    let lastKey = '', state = null;
    // The board survives re-renders of the same round, so polling or socket
    // updates never wipe a picture that is still being drawn.
    let board = null, boardRound = null;
    // Deadline on the monotonic clock; the server only sends "ms left".
    let deadlineAt = null, timeUpRound = null, lateRefreshRound = null;
    // Seconds whose countdown cue already sounded, reset every round.
    let cueRound = null, cuedSeconds = new Set();

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

    function progressBlock() {
        const block = el('div', undefined, 'drawing-progress');
        const count = el('strong');
        count.dataset.live = 'submitted';
        const total = el('span');
        total.dataset.live = 'expected';
        const bar = el('div', undefined, 'drawing-progress-bar');
        const fill = el('i');
        fill.dataset.live = 'bar';
        bar.append(fill);
        block.append(count, total, bar);
        return block;
    }

    function updateProgress() {
        if (!state || state.phase !== 'drawing' || typeof state.expected_count !== 'number') return;
        const expected = Math.max(state.expected_count, state.submitted_count);
        root.querySelectorAll('[data-live="submitted"]').forEach(node => { node.textContent = state.submitted_count; });
        root.querySelectorAll('[data-live="expected"]').forEach(node => { node.textContent = `/ ${expected} надіслали`; });
        root.querySelectorAll('[data-live="bar"]').forEach(node => { node.style.width = `${expected ? state.submitted_count / expected * 100 : 0}%`; });
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

    function render() {
        progress.textContent = `РАУНД ${state.round} / ${state.rounds}`;
        root.replaceChildren();
        const timedOut = timeUpRound === state.round;
        const drawingNow = state.phase === 'drawing' && !isHost && !state.submitted && !timedOut;
        document.body.classList.toggle('drawing-page--workspace', drawingNow);
        if (drawingNow) { renderWorkspace(); return; }
        dropBoard();
        const content = el('div', undefined, 'drawing-content');
        root.append(content);
        content.append(el('div', state.phase === 'results' ? 'ФІНАЛ' : `РАУНД ${state.round}`, 'drawing-eyebrow'));
        content.append(el('h1', state.phase === 'results' ? 'Ось наші переможці!' : state.prompt));
        if (state.phase === 'drawing') {
            if (isHost) content.append(el('p', 'Голосування відкриється само, щойно всі надішлють малюнки або вийде час.'));
            else if (state.submitted) content.append(el('p', 'Ваш малюнок надіслано ✓ Голосування почнеться, коли всі закінчать.'));
            else content.append(el('p', 'Час вийшов. Голосування почнеться, коли всі закінчать.'));
            content.append(progressBlock());
        } else if (state.phase === 'voting') {
            content.append(el('p', 'Роботи анонімні до кінця гри. Можна віддати один голос за чужий малюнок.'));
            if (state.voted) content.append(el('p', 'Ваш голос зараховано ✓'));
            const grid = el('div', undefined, 'drawing-gallery');
            state.drawings.forEach((work, i) => {
                const card = el('article', undefined, 'drawing-card'); const img = document.createElement('img'); img.src = work.url; img.alt = `Робота ${i+1}`;
                card.append(img, el('strong', `Робота ${i+1}`));
                if (work.own) card.append(el('span', 'Ваша робота'));
                else if (state.can_vote) card.append(button('Голосувати за роботу', () => update('/api/drawing/vote', {round:state.round, drawing_id:work.id})));
                grid.append(card);
            });
            if (!state.drawings.length) grid.append(el('p', 'У цьому раунді немає надісланих робіт.'));
            content.append(grid);
        } else {
            const winners = el('section', undefined, 'drawing-winners');
            state.winners.forEach(w => winners.append(el('p', `${w.round}. ${w.prompt} — ${w.names.length ? w.names.join(', ') : 'немає переможця'}`)));
            content.append(winners, el('h2', 'Усі роботи'), el('p', 'Роботи доступні за посиланням протягом 7 днів після надсилання.'));
            const grid = el('div', undefined, 'drawing-gallery');
            state.drawings.forEach(work => {
                const card = el('article', undefined, 'drawing-card'); const img = document.createElement('img'); img.src = work.url; img.alt = `Малюнок: ${work.prompt}`;
                const download = el('a', 'Завантажити', 'drawing-tool'); download.href = work.url; download.download = 'malyunok.png';
                const share = button('Скопіювати посилання', async () => { await navigator.clipboard.writeText(new URL(work.url, location.href).href); showToast('Посилання скопійовано.', {type:'success'}); }, 'drawing-tool');
                card.append(img, el('strong', work.author), el('span', `Раунд ${work.round} · ${work.prompt}`), download, share); grid.append(card);
            });
            content.append(grid);
        }
        if (isHost && state.phase === 'drawing') {
            content.append(button('Завершити малювання зараз', endDrawingEarly, 'drawing-tool drawing-host-action'));
        } else if (isHost) {
            const text = state.phase === 'voting' ? (state.round === state.rounds ? 'Показати результати' : 'Наступний раунд') : 'Повернутися в лобі';
            content.append(button(text, () => update('/api/drawing/advance', {round:state.round, phase:state.phase}), 'drawing-button drawing-host-action'));
        }
        updateProgress();
    }
    connectRoomSocket({drawing:refresh, state(s) { if (s.activity_type !== 'drawing') window.location.href = '/lobby'; }});
    refresh(); setInterval(refresh, 5000); setInterval(tick, 250);
})();
