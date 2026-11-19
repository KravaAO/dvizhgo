(() => {
    // Every drawing is stored at the same square resolution, whatever the
    // screen. The display size is clamped separately so the field never gets
    // unusably small on phones or oversized on a projector.
    const CANVAS_SIZE = 800;
    const DISPLAY_MIN = 240;
    const DISPLAY_MAX = 720;
    const FRAME_CHROME = 14;
    const HISTORY_LIMIT = 15;
    const FILL_TOLERANCE = 48;
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
        fill: icon('<path d="M4 11l7-7 7 7-7 7z"/><path d="M4 11h14"/><path d="M20 15c1 1.5 1.5 2.5 1.5 3.2a1.5 1.5 0 0 1-3 0c0-.7.5-1.7 1.5-3.2z"/>'),
        picker: icon('<path d="M15 4l5 5"/><path d="M17.5 2.5l4 4-3 3-4-4z"/><path d="M14 8L5 17v2h2l9-9"/>'),
        line: icon('<path d="M5 19L19 5"/>'),
        rect: icon('<rect x="4" y="6" width="16" height="12"/>'),
        ellipse: icon('<ellipse cx="12" cy="12" rx="8.5" ry="6.5"/>'),
        triangle: icon('<path d="M12 4l9 16H3z"/>'),
        outline: icon('<rect x="5" y="5" width="14" height="14"/>'),
        solid: icon('<rect x="5" y="5" width="14" height="14" fill="currentColor"/>'),
        undo: icon('<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>'),
        redo: icon('<path d="M15 14l5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h3"/>'),
        clear: icon('<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>'),
    };
    const TOOLS = [
        {id: 'pen', label: 'Пензель', key: 'b'},
        {id: 'eraser', label: 'Гумка', key: 'e'},
        {id: 'fill', label: 'Заливка', key: 'g'},
        {id: 'picker', label: 'Піпетка', key: 'i'},
    ];
    const SHAPES = [
        {id: 'line', label: 'Лінія', key: 'l'},
        {id: 'rect', label: 'Прямокутник', key: 'r'},
        {id: 'ellipse', label: 'Еліпс', key: 'o'},
        {id: 'triangle', label: 'Трикутник', key: 't'},
    ];
    const ALL_TOOLS = [...TOOLS, ...SHAPES];
    const BRUSHES = new Set(['pen', 'eraser']);
    const SHAPE_IDS = new Set(SHAPES.map(shape => shape.id));
    const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
    const MOD = isMac ? '⌘' : 'Ctrl+';

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

    function group(label, className = 'draw-group') {
        const node = el('div', className);
        node.setAttribute('role', 'group');
        node.setAttribute('aria-label', label);
        return node;
    }

    function hexToRgb(hex) {
        const value = parseInt(hex.slice(1), 16);
        return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
    }

    function rgbToHex(r, g, b) {
        return `#${[r, g, b].map(part => part.toString(16).padStart(2, '0')).join('')}`;
    }

    function createDrawingBoard() {
        const settings = {tool: 'pen', color: PALETTE[0][0], size: SIZES[1].value, opacity: 1, solid: false};
        let disabled = false;
        let gesture = null;
        let lastDrawingTool = 'pen';
        const undoStack = [];
        const redoStack = [];

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
        palette.setAttribute('aria-label', 'Колір, товщина і прозорість');
        element.append(toolbar, stage, palette);

        const ctx = canvas.getContext('2d', {willReadFrequently: true});
        const octx = overlay.getContext('2d');
        ctx.fillStyle = BACKGROUND;
        ctx.fillRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

        // ---- Left: tools, shapes, history -----------------------------------
        const toolButtons = new Map();
        const addTools = (items, label) => {
            const node = group(label);
            items.forEach(tool => {
                const button = iconButton(`${tool.label} (${tool.key.toUpperCase()})`, ICONS[tool.id]);
                button.addEventListener('click', () => selectTool(tool.id));
                toolButtons.set(tool.id, button);
                node.append(button);
            });
            return node;
        };
        const toolGroup = addTools(TOOLS, 'Інструменти');
        const shapeGroup = addTools(SHAPES, 'Фігури');
        const outlineButton = iconButton('Фігура контуром', ICONS.outline);
        const solidButton = iconButton('Залита фігура', ICONS.solid);
        outlineButton.addEventListener('click', () => selectShapeStyle(false));
        solidButton.addEventListener('click', () => selectShapeStyle(true));
        shapeGroup.append(outlineButton, solidButton);

        const historyGroup = group('Історія');
        const undoButton = iconButton(`Скасувати (${MOD}Z)`, ICONS.undo);
        const redoButton = iconButton(`Повторити (${MOD}Shift+Z)`, ICONS.redo);
        const clearButton = iconButton('Очистити полотно', ICONS.clear);
        undoButton.addEventListener('click', undo);
        redoButton.addEventListener('click', redo);
        clearButton.addEventListener('click', clearCanvas);
        historyGroup.append(undoButton, redoButton, clearButton);
        toolbar.append(toolGroup, shapeGroup, historyGroup);

        // ---- Right: colour, width, opacity ----------------------------------
        const swatchGroup = group('Колір', 'draw-swatches');
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
        customLabel.title = 'Свій колір';
        const customInput = el('input');
        customInput.type = 'color';
        customInput.value = '#3a86ff';
        customInput.setAttribute('aria-label', 'Свій колір');
        customLabel.append(customInput);
        customInput.addEventListener('input', () => selectColor(customInput.value));
        swatchGroup.append(customLabel);

        const sizeButtons = new Map();
        const sizeGroup = group('Товщина лінії', 'draw-sizes');
        SIZES.forEach(size => {
            const button = el('button', 'draw-tool-btn draw-size');
            button.type = 'button';
            button.title = `${size.label} · ${size.value}px ([ / ])`;
            button.setAttribute('aria-label', `${size.label} лінія, ${size.value} пікселів`);
            const dot = el('i');
            dot.style.setProperty('--dot', `${size.dot}px`);
            button.append(dot);
            button.addEventListener('click', () => selectSize(size.value));
            sizeButtons.set(size.value, button);
            sizeGroup.append(button);
        });

        const opacityLabel = el('label', 'draw-opacity');
        const opacityText = el('span', 'draw-label');
        const opacityValue = el('output');
        opacityText.append(el('span', 'draw-opacity-name', 'Прозорість '), opacityValue);
        const opacityInput = el('input');
        opacityInput.type = 'range';
        opacityInput.min = '10';
        opacityInput.max = '100';
        opacityInput.step = '5';
        opacityInput.value = '100';
        opacityInput.setAttribute('aria-label', 'Прозорість');
        opacityInput.addEventListener('input', () => selectOpacity(Number(opacityInput.value) / 100));
        opacityLabel.append(opacityText, opacityInput);
        palette.append(
            el('span', 'draw-label', 'Колір'), swatchGroup,
            el('span', 'draw-label draw-size-label', 'Товщина'), sizeGroup,
            opacityLabel,
        );

        // ---- Selection state ------------------------------------------------
        function selectTool(id) {
            if (id !== 'picker') lastDrawingTool = id;
            settings.tool = id;
            toolButtons.forEach((button, key) => button.setAttribute('aria-pressed', String(key === id)));
            frame.dataset.tool = id;
            const styleMatters = SHAPE_IDS.has(id) && id !== 'line';
            outlineButton.disabled = solidButton.disabled = disabled || !styleMatters;
            syncCursor();
        }

        function selectShapeStyle(solid) {
            settings.solid = solid;
            outlineButton.setAttribute('aria-pressed', String(!solid));
            solidButton.setAttribute('aria-pressed', String(solid));
        }

        function selectSize(value) {
            settings.size = value;
            sizeButtons.forEach((button, key) => button.setAttribute('aria-pressed', String(key === value)));
            syncCursor();
        }

        function selectColor(value) {
            const preset = swatchButtons.has(value);
            settings.color = value;
            swatchButtons.forEach((button, key) => button.setAttribute('aria-pressed', String(key === value)));
            customLabel.classList.toggle('active', !preset);
            if (!preset) customInput.value = value;
            if (settings.tool === 'eraser') selectTool('pen');
        }

        function selectOpacity(value) {
            settings.opacity = value;
            opacityInput.value = String(Math.round(value * 100));
            opacityValue.textContent = `${Math.round(value * 100)}%`;
        }

        // ---- History --------------------------------------------------------
        function snapshot() {
            return ctx.getImageData(0, 0, CANVAS_SIZE, CANVAS_SIZE);
        }

        function remember() {
            undoStack.push(snapshot());
            if (undoStack.length > HISTORY_LIMIT) undoStack.shift();
            redoStack.length = 0;
            syncHistory();
        }

        function undo() {
            if (disabled || !undoStack.length) return;
            cancelGesture();
            redoStack.push(snapshot());
            ctx.putImageData(undoStack.pop(), 0, 0);
            syncHistory();
        }

        function redo() {
            if (disabled || !redoStack.length) return;
            cancelGesture();
            undoStack.push(snapshot());
            ctx.putImageData(redoStack.pop(), 0, 0);
            syncHistory();
        }

        function clearCanvas() {
            if (disabled || isBlank()) return;
            cancelGesture();
            remember();
            ctx.fillStyle = BACKGROUND;
            ctx.fillRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);
        }

        function syncHistory() {
            undoButton.disabled = disabled || !undoStack.length;
            redoButton.disabled = disabled || !redoStack.length;
        }

        // ---- Square sizing --------------------------------------------------
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

        // ---- Drawing operations ---------------------------------------------
        let rect = null;
        function toCanvas(event) {
            return {
                x: Math.max(0, Math.min(CANVAS_SIZE - 1, (event.clientX - rect.left) * CANVAS_SIZE / rect.width)),
                y: Math.max(0, Math.min(CANVAS_SIZE - 1, (event.clientY - rect.top) * CANVAS_SIZE / rect.height)),
            };
        }

        function prepareOverlay() {
            // Strokes and shapes are drawn opaque on the overlay and composited
            // once, so semi-transparent lines never darken where they overlap.
            octx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);
            const color = settings.tool === 'eraser' ? BACKGROUND : settings.color;
            octx.strokeStyle = octx.fillStyle = color;
            octx.lineWidth = settings.size;
            octx.lineCap = 'round';
            octx.lineJoin = SHAPE_IDS.has(settings.tool) ? 'miter' : 'round';
            overlay.style.opacity = String(settings.tool === 'eraser' ? 1 : settings.opacity);
        }

        function commitOverlay() {
            remember();
            ctx.save();
            ctx.globalAlpha = Number(overlay.style.opacity || 1);
            ctx.drawImage(overlay, 0, 0);
            ctx.restore();
            discardOverlay();
        }

        function discardOverlay() {
            octx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);
            overlay.style.opacity = '1';
        }

        function extendStroke(point) {
            const mid = {x: (gesture.last.x + point.x) / 2, y: (gesture.last.y + point.y) / 2};
            octx.beginPath();
            octx.moveTo(gesture.mid.x, gesture.mid.y);
            octx.quadraticCurveTo(gesture.last.x, gesture.last.y, mid.x, mid.y);
            octx.stroke();
            gesture.last = point;
            gesture.mid = mid;
        }

        function shapeEnd(point, constrain) {
            let dx = point.x - gesture.start.x;
            let dy = point.y - gesture.start.y;
            if (constrain && settings.tool === 'line') {
                const angle = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4);
                const length = Math.hypot(dx, dy);
                dx = Math.cos(angle) * length;
                dy = Math.sin(angle) * length;
            } else if (constrain) {
                const side = Math.max(Math.abs(dx), Math.abs(dy));
                dx = Math.sign(dx || 1) * side;
                dy = Math.sign(dy || 1) * side;
            }
            return {x: gesture.start.x + dx, y: gesture.start.y + dy};
        }

        function drawShape(point, constrain) {
            const start = gesture.start;
            const end = shapeEnd(point, constrain);
            gesture.size = Math.hypot(end.x - start.x, end.y - start.y);
            octx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);
            octx.beginPath();
            if (settings.tool === 'line') {
                octx.moveTo(start.x, start.y);
                octx.lineTo(end.x, end.y);
                octx.stroke();
                return;
            }
            const left = Math.min(start.x, end.x);
            const top = Math.min(start.y, end.y);
            const width = Math.abs(end.x - start.x);
            const height = Math.abs(end.y - start.y);
            if (settings.tool === 'rect') {
                octx.rect(left, top, width, height);
            } else if (settings.tool === 'ellipse') {
                octx.ellipse(left + width / 2, top + height / 2, width / 2, height / 2, 0, 0, Math.PI * 2);
            } else {
                // The apex follows the drag start, so dragging upwards flips it.
                octx.moveTo((start.x + end.x) / 2, start.y);
                octx.lineTo(end.x, end.y);
                octx.lineTo(start.x, end.y);
                octx.closePath();
            }
            if (settings.solid) octx.fill();
            else octx.stroke();
        }

        function floodFill(point) {
            const startX = Math.floor(point.x);
            const startY = Math.floor(point.y);
            const image = snapshot();
            const data = image.data;
            const seed = (startY * CANVAS_SIZE + startX) * 4;
            const target = [data[seed], data[seed + 1], data[seed + 2]];
            const [red, green, blue] = hexToRgb(settings.color);
            const alpha = settings.opacity;
            if (alpha === 1 && Math.abs(target[0] - red) + Math.abs(target[1] - green) + Math.abs(target[2] - blue) === 0) return;
            const total = CANVAS_SIZE * CANVAS_SIZE;
            const mask = new Uint8Array(total);
            const matches = index => {
                if (mask[index]) return false;
                const offset = index * 4;
                return Math.abs(data[offset] - target[0]) <= FILL_TOLERANCE
                    && Math.abs(data[offset + 1] - target[1]) <= FILL_TOLERANCE
                    && Math.abs(data[offset + 2] - target[2]) <= FILL_TOLERANCE;
            };
            // Scanline flood fill: walks horizontal runs instead of single
            // pixels, which keeps an 800×800 fill well under a frame.
            const stack = [startX, startY];
            while (stack.length) {
                const y = stack.pop();
                let x = stack.pop();
                const row = y * CANVAS_SIZE;
                while (x > 0 && matches(row + x - 1)) x -= 1;
                let spanUp = false;
                let spanDown = false;
                for (; x < CANVAS_SIZE && matches(row + x); x += 1) {
                    mask[row + x] = 1;
                    if (y > 0) {
                        const up = matches(row - CANVAS_SIZE + x);
                        if (up && !spanUp) stack.push(x, y - 1);
                        spanUp = up;
                    }
                    if (y < CANVAS_SIZE - 1) {
                        const down = matches(row + CANVAS_SIZE + x);
                        if (down && !spanDown) stack.push(x, y + 1);
                        spanDown = down;
                    }
                }
            }
            // Grow the area by one pixel so anti-aliased outlines do not leave
            // a pale halo between the fill and the line.
            const paint = mask.slice();
            for (let index = 0; index < total; index += 1) {
                if (mask[index]) continue;
                const x = index % CANVAS_SIZE;
                if ((x > 0 && mask[index - 1]) || (x < CANVAS_SIZE - 1 && mask[index + 1])
                    || (index >= CANVAS_SIZE && mask[index - CANVAS_SIZE])
                    || (index < total - CANVAS_SIZE && mask[index + CANVAS_SIZE])) paint[index] = 1;
            }
            remember();
            for (let index = 0; index < total; index += 1) {
                if (!paint[index]) continue;
                const offset = index * 4;
                data[offset] = Math.round(red * alpha + data[offset] * (1 - alpha));
                data[offset + 1] = Math.round(green * alpha + data[offset + 1] * (1 - alpha));
                data[offset + 2] = Math.round(blue * alpha + data[offset + 2] * (1 - alpha));
                data[offset + 3] = 255;
            }
            ctx.putImageData(image, 0, 0);
        }

        function pickColor(point) {
            const [red, green, blue] = ctx.getImageData(Math.floor(point.x), Math.floor(point.y), 1, 1).data;
            selectColor(rgbToHex(red, green, blue));
            selectTool(lastDrawingTool === 'eraser' ? 'pen' : lastDrawingTool);
        }

        // ---- Pointer input --------------------------------------------------
        function finishGesture() {
            if (!gesture) return;
            if (BRUSHES.has(gesture.tool)) {
                octx.beginPath();
                octx.moveTo(gesture.mid.x, gesture.mid.y);
                octx.lineTo(gesture.last.x, gesture.last.y);
                octx.stroke();
                commitOverlay();
            } else if (gesture.size >= 2) {
                commitOverlay();
            } else {
                discardOverlay();
            }
            gesture = null;
        }

        function cancelGesture() {
            if (gesture) discardOverlay();
            gesture = null;
        }

        function onPointerDown(event) {
            if (disabled || gesture || (event.pointerType === 'mouse' && event.button !== 0)) return;
            event.preventDefault();
            rect = canvas.getBoundingClientRect();
            const point = toCanvas(event);
            if (settings.tool === 'fill') { floodFill(point); return; }
            if (settings.tool === 'picker') { pickColor(point); return; }
            frame.setPointerCapture(event.pointerId);
            gesture = {pointerId: event.pointerId, tool: settings.tool, start: point, last: point, mid: point, size: 0};
            prepareOverlay();
            if (BRUSHES.has(settings.tool)) {
                octx.beginPath();
                octx.arc(point.x, point.y, settings.size / 2, 0, Math.PI * 2);
                octx.fill();
            }
        }

        function onPointerMove(event) {
            if (event.pointerType === 'mouse') moveCursor(event);
            if (!gesture || event.pointerId !== gesture.pointerId) return;
            event.preventDefault();
            if (BRUSHES.has(gesture.tool)) {
                const samples = typeof event.getCoalescedEvents === 'function' ? event.getCoalescedEvents() : [];
                (samples.length ? samples : [event]).forEach(sample => extendStroke(toCanvas(sample)));
            } else {
                drawShape(toCanvas(event), event.shiftKey);
            }
        }

        function onPointerEnd(event) {
            if (!gesture || event.pointerId !== gesture.pointerId) return;
            finishGesture();
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
            if (!BRUSHES.has(settings.tool)) cursor.hidden = true;
        }

        function moveCursor(event) {
            const bounds = frame.getBoundingClientRect();
            cursor.hidden = disabled || !BRUSHES.has(settings.tool);
            cursor.style.left = `${event.clientX - bounds.left}px`;
            cursor.style.top = `${event.clientY - bounds.top}px`;
        }

        // ---- Keyboard shortcuts ---------------------------------------------
        function onKeyDown(event) {
            if (disabled || event.altKey) return;
            if (event.target.closest?.('input, textarea, select, [contenteditable="true"]')) return;
            const key = event.key.toLowerCase();
            if (event.ctrlKey || event.metaKey) {
                if (key === 'z' && event.shiftKey) { redo(); event.preventDefault(); }
                else if (key === 'z') { undo(); event.preventDefault(); }
                else if (key === 'y') { redo(); event.preventDefault(); }
                return;
            }
            const tool = ALL_TOOLS.find(item => item.key === key);
            if (tool) { selectTool(tool.id); event.preventDefault(); return; }
            const index = SIZES.findIndex(size => size.value === settings.size);
            if (event.key === '[' && index > 0) selectSize(SIZES[index - 1].value);
            if (event.key === ']' && index < SIZES.length - 1) selectSize(SIZES[index + 1].value);
        }
        document.addEventListener('keydown', onKeyDown);

        // ---- Public API -----------------------------------------------------
        function isBlank() {
            const pixels = new Uint32Array(snapshot().data.buffer);
            return pixels.every(pixel => pixel === 0xffffffff);
        }

        function toPng() {
            finishGesture();
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
            if (disabled) finishGesture();
            element.classList.toggle('is-disabled', disabled);
            element.querySelectorAll('button, input').forEach(control => { control.disabled = disabled; });
            cursor.hidden = true;
            if (!disabled) { selectTool(settings.tool); syncHistory(); }
        }

        function destroy() {
            resizeObserver.disconnect();
            document.removeEventListener('keydown', onKeyDown);
        }

        selectTool('pen');
        selectShapeStyle(false);
        selectSize(settings.size);
        selectColor(settings.color);
        selectOpacity(settings.opacity);
        syncHistory();
        cursor.hidden = true;

        return {element, isBlank, toPng, finishGesture, setDisabled, destroy};
    }

    window.createDrawingBoard = createDrawingBoard;
})();
