(() => {
    const root = document.getElementById('drawingContent');
    const progress = document.getElementById('drawingProgress');
    const isHost = document.body.dataset.host === 'true';
    let lastKey = '', state = null;
    // The board survives re-renders of the same round, so polling or socket
    // updates never wipe a picture that is still being drawn.
    let board = null, boardRound = null;

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
    async function refresh() {
        try {
            const response = await fetch('/api/drawing/current', {cache:'no-store'});
            if (response.status === 404) { window.location.href = '/lobby'; return; }
            if (!response.ok) return;
            const next = await response.json();
            const key = JSON.stringify(next);
            state = next;
            if (key !== lastKey) { lastKey = key; render(); }
        } catch (error) { console.error(error); }
    }
    const update = async (url, data = {}) => { await send(url, data); await refresh(); };

    function dropBoard() {
        if (!board) return;
        board.destroy();
        board = null;
        boardRound = null;
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
        const drawingNow = state.phase === 'drawing' && !isHost && !state.submitted;
        document.body.classList.toggle('drawing-page--workspace', drawingNow);
        if (drawingNow) { renderWorkspace(); return; }
        dropBoard();
        const content = el('div', undefined, 'drawing-content');
        root.append(content);
        content.append(el('div', state.phase === 'results' ? 'ФІНАЛ' : `РАУНД ${state.round}`, 'drawing-eyebrow'));
        content.append(el('h1', state.phase === 'results' ? 'Ось наші переможці!' : state.prompt));
        if (state.phase === 'drawing') {
            if (isHost) content.append(el('p', 'Учасники малюють. Коли всі будуть готові, відкрийте голосування.'));
            else content.append(el('p', 'Ваш малюнок надіслано! Очікуємо голосування.'));
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
        if (isHost) {
            const text = state.phase === 'drawing' ? 'Відкрити голосування' : state.phase === 'voting' ? (state.round === state.rounds ? 'Показати результати' : 'Наступний раунд') : 'Повернутися в лобі';
            content.append(button(text, () => update('/api/drawing/advance', {round:state.round, phase:state.phase}), 'drawing-button drawing-host-action'));
        }
    }
    connectRoomSocket({drawing:refresh, state(s) { if (s.activity_type !== 'drawing') window.location.href = '/lobby'; }});
    refresh(); setInterval(refresh, 5000);
})();
