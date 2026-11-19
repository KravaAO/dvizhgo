(() => {
    // Every drawing is stored at the same square resolution, whatever the
    // screen. The display size is clamped separately so the field never gets
    // unusably small on phones or oversized on a projector.
    const CANVAS_SIZE = 800;
    const DISPLAY_MIN = 260;
    const DISPLAY_MAX = 720;
    const FRAME_CHROME = 14;
    const MAX_DATA_URL_LENGTH = 1350000;
    const BACKGROUND = '#ffffff';
    const PALETTE = [
        ['#171714', 'Чорний'], ['#5b5852', 'Графіт'], ['#a39e93', 'Сірий'],
        ['#ffffff', 'Білий'], ['#e63946', 'Червоний'], ['#ff5a36', 'Кораловий'],
        ['#ff9f1c', 'Помаранчевий'], ['#ffd23f', 'Жовтий'], ['#8bd5aa', 'М’ятний'],
        ['#2a9d4b', 'Зелений'], ['#164d4b', 'Смарагдовий'], ['#82aeea', 'Блакитний'],
        ['#1d4ed8', 'Синій'], ['#6d28d9', 'Фіолетовий'], ['#c69ee7', 'Лавандовий'],
        ['#f4a6c0', 'Рожевий'], ['#8b5a2b', 'Коричневий'], ['#f2c9a0', 'Пісочний'],
    ];
    const SIZES = [
        {value: 3, dot: 4, label: 'Тонка'},
        {value: 8, dot: 8, label: 'Середня'},
        {value: 16, dot: 12, label: 'Товста'},
        {value: 28, dot: 17, label: 'Дуже товста'},
        {value: 44, dot: 23, label: 'Маркер'},
    ];
    const icon = paths => `<svg viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`;
    const ICONS = {
        pen: icon('<path d="M4 20l1-4L16 5l3 3L8 19z"/><path d="M14 7l3 3"/>'),
        eraser: icon('<path d="M4 15l8-8 6 6-6 6H8z"/><path d="M12 19h8"/><path d="M8 11l6 6"/>'),
    };
    const TOOLS = [
        {id: 'pen', label: 'Пензель', key: 'b'},
        {id: 'eraser', label: 'Гумка', key: 'e'},
    ];

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function iconButton(label, svg, className = 'draw-tool-btn') {
        const button = el('button', className);
        button.type = 'button';
        button.title = label;
        button.setAttribute('aria-label', label);
        button.innerHTML = svg;
        return button;
    }

    function createDrawingBoard() {
        const settings = {tool: 'pen', color: PALETTE[0][0], size: SIZES[1].value, opacity: 1};
        let disabled = false;
        let stroke = null;

        const element = el('div', 'draw-board');
        const toolbar = el('div', 'draw-toolbar');
        toolbar.setAttribute('role', 'toolbar');
        toolbar.setAttribute('aria-label', 'Інструменти малювання');
        const stage = el('div', 'draw-stage');
        const frame = el('div', 'draw-frame');
        const canvas = el('canvas', 'draw-canvas');
        const overlay = el('canvas', 'draw-overlay');
        const cursor = el('div', 'draw-cursor');
        canvas.width = canvas.height = overlay.width = overlay.height = CANVAS_SIZE;
        canvas.setAttribute('role', 'img');
        canvas.setAttribute('aria-label', 'Полотно для малювання');
        frame.append(canvas, overlay, cursor);
        stage.append(frame);
        const palette = el('aside', 'draw-palette');
        palette.setAttribute('aria-label', 'Колір і прозорість');
        element.append(toolbar, stage, palette);

        const ctx = canvas.getContext('2d', {willReadFrequently: true});
        const octx = overlay.getContext('2d');
        ctx.fillStyle = BACKGROUND;
        ctx.fillRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

        // ---- Toolbar -------------------------------------------------------
        const toolButtons = new Map();
        const toolGroup = el('div', 'draw-group');
        TOOLS.forEach(tool => {
            const button = iconButton(`${tool.label} (${tool.key.toUpperCase()})`, ICONS[tool.id]);
            button.addEventListener('click', () => selectTool(tool.id));
            toolButtons.set(tool.id, button);
            toolGroup.append(button);
        });

        const sizeButtons = new Map();
        const sizeGroup = el('div', 'draw-group draw-sizes');
        sizeGroup.setAttribute('role', 'group');
        sizeGroup.setAttribute('aria-label', 'Товщина лінії');
        SIZES.forEach(size => {
            const button = el('button', 'draw-tool-btn draw-size');
            button.type = 'button';
            button.title = `${size.label} · ${size.value}px`;
            button.setAttribute('aria-label', `${size.label} лінія, ${size.value} пікселів`);
            const dot = el('i');
            dot.style.setProperty('--dot', `${size.dot}px`);
            button.append(dot);
            button.addEventListener('click', () => selectSize(size.value));
            sizeButtons.set(size.value, button);
            sizeGroup.append(button);
        });
        toolbar.append(toolGroup, sizeGroup);

        // ---- Palette -------------------------------------------------------
        const current = el('div', 'draw-current');
        current.setAttribute('aria-hidden', 'true');
        const swatchGroup = el('div', 'draw-swatches');
        swatchGroup.setAttribute('role', 'group');
        swatchGroup.setAttribute('aria-label', 'Колір');
        const swatchButtons = new Map();
        PALETTE.forEach(([value, label]) => {
            const swatch = el('button', 'draw-swatch');
            swatch.type = 'button';
            swatch.title = label;
            swatch.setAttribute('aria-label', label);
            swatch.style.setProperty('--swatch', value);
            swatch.addEventListener('click', () => selectColor(value));
            swatchButtons.set(value, swatch);
            swatchGroup.append(swatch);
        });
        const customLabel = el('label', 'draw-custom');
        const customInput = el('input');
        customInput.type = 'color';
        customInput.value = '#3a86ff';
        customLabel.append(customInput, el('span', undefined, 'Свій колір'));
        customInput.addEventListener('input', () => selectColor(customInput.value, true));

        const opacityLabel = el('label', 'draw-opacity');
        const opacityText = el('span', 'draw-label');
        const opacityValue = el('output');
        opacityText.append('Прозорість ', opacityValue);
        const opacityInput = el('input');
        opacityInput.type = 'range';
        opacityInput.min = '10';
        opacityInput.max = '100';
        opacityInput.step = '5';
        opacityInput.value = '100';
        opacityInput.addEventListener('input', () => selectOpacity(Number(opacityInput.value) / 100));
        opacityLabel.append(opacityText, opacityInput);
        palette.append(el('span', 'draw-label', 'Колір'), current, swatchGroup, customLabel, opacityLabel);

        function selectTool(id) {
            settings.tool = id;
            toolButtons.forEach((button, key) => button.setAttribute('aria-pressed', String(key === id)));
            frame.dataset.tool = id;
            syncCursor();
        }

        function selectSize(value) {
            settings.size = value;
            sizeButtons.forEach((button, key) => button.setAttribute('aria-pressed', String(key === value)));
            syncCursor();
        }

        function selectColor(value, custom = false) {
            settings.color = value;
            swatchButtons.forEach((button, key) => button.setAttribute('aria-pressed', String(!custom && key === value)));
            customLabel.classList.toggle('active', custom);
            if (!custom) customInput.value = value;
            current.style.setProperty('--current', value);
            if (settings.tool === 'eraser') selectTool('pen');
        }

        function selectOpacity(value) {
            settings.opacity = value;
            opacityInput.value = String(Math.round(value * 100));
            opacityValue.textContent = `${Math.round(value * 100)}%`;
            current.style.setProperty('--current-opacity', value);
        }

        // ---- Square sizing -------------------------------------------------
        let displaySize = DISPLAY_MIN;
        function fit() {
            const style = getComputedStyle(stage);
            const width = stage.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
            const height = stage.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
            if (width <= 0 || height <= 0) return;
            // Reserve the frame border (2 × 3px) and its 7px hard shadow.
            const available = Math.min(width, height) - FRAME_CHROME;
            displaySize = Math.round(Math.max(DISPLAY_MIN, Math.min(DISPLAY_MAX, available)));
            frame.style.width = frame.style.height = `${displaySize}px`;
            syncCursor();
        }
        const resizeObserver = new ResizeObserver(fit);
        resizeObserver.observe(stage);

        // ---- Pointer input -------------------------------------------------
        let rect = null;
        function toCanvas(event) {
            return {
                x: (event.clientX - rect.left) * CANVAS_SIZE / rect.width,
                y: (event.clientY - rect.top) * CANVAS_SIZE / rect.height,
            };
        }

        function strokeColor() {
            return settings.tool === 'eraser' ? BACKGROUND : settings.color;
        }

        function strokeOpacity() {
            return settings.tool === 'eraser' ? 1 : settings.opacity;
        }

        function beginStroke(point) {
            // Strokes are drawn opaque on the overlay and composited once, so
            // a semi-transparent line never darkens where it overlaps itself.
            octx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);
            octx.strokeStyle = octx.fillStyle = strokeColor();
            octx.lineWidth = settings.size;
            octx.lineCap = 'round';
            octx.lineJoin = 'round';
            overlay.style.opacity = String(strokeOpacity());
            octx.beginPath();
            octx.arc(point.x, point.y, settings.size / 2, 0, Math.PI * 2);
            octx.fill();
            stroke.last = point;
            stroke.mid = point;
        }

        function extendStroke(point) {
            const mid = {x: (stroke.last.x + point.x) / 2, y: (stroke.last.y + point.y) / 2};
            octx.beginPath();
            octx.moveTo(stroke.mid.x, stroke.mid.y);
            octx.quadraticCurveTo(stroke.last.x, stroke.last.y, mid.x, mid.y);
            octx.stroke();
            stroke.last = point;
            stroke.mid = mid;
        }

        function commitOverlay() {
            ctx.save();
            ctx.globalAlpha = Number(overlay.style.opacity || 1);
            ctx.drawImage(overlay, 0, 0);
            ctx.restore();
            octx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);
            overlay.style.opacity = '1';
        }

        function finishStroke() {
            if (!stroke) return;
            const last = stroke.last;
            octx.beginPath();
            octx.moveTo(stroke.mid.x, stroke.mid.y);
            octx.lineTo(last.x, last.y);
            octx.stroke();
            commitOverlay();
            stroke = null;
        }

        function onPointerDown(event) {
            if (disabled || stroke || (event.pointerType === 'mouse' && event.button !== 0)) return;
            event.preventDefault();
            frame.setPointerCapture(event.pointerId);
            rect = canvas.getBoundingClientRect();
            stroke = {pointerId: event.pointerId};
            beginStroke(toCanvas(event));
        }

        function onPointerMove(event) {
            if (event.pointerType === 'mouse') moveCursor(event);
            if (!stroke || event.pointerId !== stroke.pointerId) return;
            event.preventDefault();
            const events = typeof event.getCoalescedEvents === 'function' ? event.getCoalescedEvents() : [];
            (events.length ? events : [event]).forEach(sample => extendStroke(toCanvas(sample)));
        }

        function onPointerEnd(event) {
            if (!stroke || event.pointerId !== stroke.pointerId) return;
            finishStroke();
        }

        frame.addEventListener('pointerdown', onPointerDown);
        frame.addEventListener('pointermove', onPointerMove);
        frame.addEventListener('pointerup', onPointerEnd);
        frame.addEventListener('pointercancel', onPointerEnd);
        frame.addEventListener('pointerleave', () => { cursor.hidden = true; });

        // A ring that matches the real brush size helps choose the width.
        function syncCursor() {
            const diameter = Math.max(4, settings.size * displaySize / CANVAS_SIZE);
            cursor.style.width = cursor.style.height = `${diameter}px`;
        }

        function moveCursor(event) {
            const bounds = frame.getBoundingClientRect();
            cursor.hidden = disabled;
            cursor.style.left = `${event.clientX - bounds.left}px`;
            cursor.style.top = `${event.clientY - bounds.top}px`;
        }

        // ---- Keyboard shortcuts --------------------------------------------
        function onKeyDown(event) {
            if (disabled || event.altKey || event.ctrlKey || event.metaKey) return;
            if (event.target.closest?.('input, textarea, select, [contenteditable="true"]')) return;
            const tool = TOOLS.find(item => item.key === event.key.toLowerCase());
            if (tool) { selectTool(tool.id); event.preventDefault(); return; }
            const index = SIZES.findIndex(size => size.value === settings.size);
            if (event.key === '[' && index > 0) selectSize(SIZES[index - 1].value);
            if (event.key === ']' && index < SIZES.length - 1) selectSize(SIZES[index + 1].value);
        }
        document.addEventListener('keydown', onKeyDown);

        // ---- Public API ----------------------------------------------------
        function isBlank() {
            const pixels = new Uint32Array(ctx.getImageData(0, 0, CANVAS_SIZE, CANVAS_SIZE).data.buffer);
            return pixels.every(pixel => pixel === 0xffffffff);
        }

        function toPng() {
            finishStroke();
            const data = canvas.toDataURL('image/png');
            if (data.length <= MAX_DATA_URL_LENGTH) return data;
            // A very detailed picture can exceed the upload limit; a smaller
            // copy keeps the work instead of rejecting it.
            const smaller = el('canvas');
            smaller.width = smaller.height = 600;
            smaller.getContext('2d').drawImage(canvas, 0, 0, 600, 600);
            return smaller.toDataURL('image/png');
        }

        function setDisabled(value) {
            disabled = Boolean(value);
            if (disabled) finishStroke();
            element.classList.toggle('is-disabled', disabled);
            element.querySelectorAll('button, input').forEach(control => { control.disabled = disabled; });
            cursor.hidden = true;
        }

        function destroy() {
            resizeObserver.disconnect();
            document.removeEventListener('keydown', onKeyDown);
        }

        selectTool('pen');
        selectSize(settings.size);
        selectColor(settings.color);
        selectOpacity(settings.opacity);
        cursor.hidden = true;

        return {element, isBlank, toPng, finishStroke, setDisabled, destroy};
    }

    window.createDrawingBoard = createDrawingBoard;
})();
