(() => {
    const root = document.getElementById('drawingContent');
    const progress = document.getElementById('drawingProgress');
    const isHost = document.body.dataset.host === 'true';
    let lastKey = '', state = null;
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
    function renderCanvas(container) {
        const tools = el('div', undefined, 'drawing-tools');
        const colorLabel = el('label', 'Колір '); const color = document.createElement('input'); color.type = 'color'; color.value = '#171714'; colorLabel.append(color);
        const sizeLabel = el('label', 'Товщина '); const size = document.createElement('input'); size.type = 'range'; size.min = 2; size.max = 50; size.value = 5; sizeLabel.append(size);
        let erase = false, active = false;
        const canvas = el('canvas', undefined, 'drawing-canvas'); canvas.width = 800; canvas.height = 600;
        const ctx = canvas.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        const point = e => { const r = canvas.getBoundingClientRect(); return [(e.clientX-r.left)*canvas.width/r.width, (e.clientY-r.top)*canvas.height/r.height]; };
        canvas.addEventListener('pointerdown', e => { e.preventDefault(); active = true; canvas.setPointerCapture(e.pointerId); const [x,y] = point(e); ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(x+.01,y+.01); ctx.strokeStyle = erase ? '#fff' : color.value; ctx.lineWidth = Number(size.value); ctx.stroke(); });
        canvas.addEventListener('pointermove', e => { if (!active) return; e.preventDefault(); const [x,y] = point(e); ctx.lineTo(x,y); ctx.strokeStyle = erase ? '#fff' : color.value; ctx.lineWidth = Number(size.value); ctx.stroke(); });
        canvas.addEventListener('pointerup', () => { active = false; }); canvas.addEventListener('pointercancel', () => { active = false; });
        const pen = button('Олівець', () => { erase = false; }, 'drawing-tool');
        const eraser = button('Гумка', () => { erase = true; }, 'drawing-tool');
        const clear = button('Очистити', () => { ctx.fillStyle = '#fff'; ctx.fillRect(0,0,canvas.width,canvas.height); }, 'drawing-tool');
        tools.append(colorLabel, sizeLabel, pen, eraser, clear);
        container.append(tools, canvas, button('Надіслати малюнок', () => update('/api/drawing/submit', {round:state.round, image:canvas.toDataURL('image/png')})));
    }
    function render() {
        progress.textContent = `РАУНД ${state.round} / ${state.rounds}`;
        root.replaceChildren();
        root.append(el('div', state.phase === 'results' ? 'ФІНАЛ' : `РАУНД ${state.round}`, 'drawing-eyebrow'));
        root.append(el('h1', state.phase === 'results' ? 'Ось наші переможці!' : state.prompt));
        if (state.phase === 'drawing') {
            if (isHost) root.append(el('p', 'Учасники малюють. Коли всі будуть готові, відкрийте голосування.'));
            else if (state.submitted) root.append(el('p', 'Ваш малюнок надіслано! Очікуємо голосування.'));
            else renderCanvas(root);
        } else if (state.phase === 'voting') {
            root.append(el('p', 'Роботи анонімні до кінця гри. Можна віддати один голос за чужий малюнок.'));
            if (!isHost && !state.voting_joined) root.append(button('Приєднатися до голосування', () => update('/api/voting/join')));
            if (state.voted) root.append(el('p', 'Ваш голос зараховано ✓'));
            const grid = el('div', undefined, 'drawing-gallery');
            state.drawings.forEach((work, i) => {
                const card = el('article', undefined, 'drawing-card'); const img = document.createElement('img'); img.src = work.url; img.alt = `Робота ${i+1}`;
                card.append(img, el('strong', `Робота ${i+1}`));
                if (work.own) card.append(el('span', 'Ваша робота'));
                else if (!isHost && state.voting_joined && !state.voted) card.append(button('Обрати цю роботу', () => update('/api/drawing/vote', {round:state.round, drawing_id:work.id})));
                grid.append(card);
            });
            if (!state.drawings.length) grid.append(el('p', 'У цьому раунді немає надісланих робіт.'));
            root.append(grid);
        } else {
            const winners = el('section', undefined, 'drawing-winners');
            state.winners.forEach(w => winners.append(el('p', `${w.round}. ${w.prompt} — ${w.names.length ? w.names.join(', ') : 'немає переможця'}`)));
            root.append(winners, el('h2', 'Усі роботи'), el('p', 'Роботи доступні за посиланням протягом 7 днів після надсилання.'));
            const grid = el('div', undefined, 'drawing-gallery');
            state.drawings.forEach(work => {
                const card = el('article', undefined, 'drawing-card'); const img = document.createElement('img'); img.src = work.url; img.alt = `Малюнок: ${work.prompt}`;
                const download = el('a', 'Завантажити', 'drawing-tool'); download.href = work.url; download.download = 'malyunok.png';
                const share = button('Скопіювати посилання', async () => { await navigator.clipboard.writeText(new URL(work.url, location.href).href); showToast('Посилання скопійовано.', {type:'success'}); }, 'drawing-tool');
                card.append(img, el('strong', work.author), el('span', `Раунд ${work.round} · ${work.prompt}`), download, share); grid.append(card);
            });
            root.append(grid);
        }
        if (isHost) {
            const text = state.phase === 'drawing' ? 'Відкрити голосування' : state.phase === 'voting' ? (state.round === state.rounds ? 'Показати результати' : 'Наступний раунд') : 'Повернутися в лобі';
            root.append(button(text, () => update('/api/drawing/advance', {round:state.round, phase:state.phase}), 'drawing-button drawing-host-action'));
        }
    }
    connectRoomSocket({drawing:refresh, state(s) { if (s.activity_type !== 'drawing') window.location.href = '/lobby'; }});
    refresh(); setInterval(refresh, 5000);
})();
