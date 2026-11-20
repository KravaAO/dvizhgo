(() => {
    const controls = document.getElementById('roomControls');
    const modes = document.getElementById('roomModes');
    const start = document.getElementById('startRoom');
    const status = document.getElementById('roomModeStatus');
    const configs = controls.querySelectorAll('[data-room-config]');
    const drawingReady = controls.querySelector('[data-room-config="drawing"]').dataset.ready === 'true';
    const radios = modes.querySelectorAll('input');
    let savedMode = controls.dataset.mode;

    function showMode(mode) {
        for (const radio of radios) radio.checked = radio.value === mode;
        for (const config of configs) config.hidden = config.dataset.roomConfig !== mode;
        start.textContent = mode === 'drawing' ? 'Почати Малювалку' : 'Почати квіз';
        start.disabled = modes.disabled || (mode === 'drawing' && !drawingReady);
    }

    modes.addEventListener('change', async event => {
        const mode = event.target.value;
        if (modes.disabled || mode === savedMode) return;
        const modeHadFocus = modes.contains(document.activeElement);
        modes.disabled = true;
        showMode(mode);
        status.textContent = 'Зберігаємо режим…';
        try {
            const response = await fetch(controls.dataset.saveUrl, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({room_mode: mode}),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || 'Не вдалося зберегти режим.');
            savedMode = data.room_mode;
            status.textContent = 'Режим збережено';
        } catch (error) {
            status.textContent = error.message;
        } finally {
            modes.disabled = false;
            showMode(savedMode);
            if (modeHadFocus && document.activeElement === document.body) {
                Array.from(radios).find(radio => radio.checked)?.focus();
            }
        }
    });

    start.addEventListener('click', async () => {
        if (start.disabled) return;
        modes.disabled = true;
        status.textContent = '';
        try {
            await launchRoomActivity(start, savedMode);
        } catch (error) {
            savedMode = error.roomMode || savedMode;
            modes.disabled = false;
            showMode(savedMode);
            status.textContent = error.message;
        }
    });

    window.addEventListener('pageshow', event => {
        if (event.persisted) window.location.reload();
    });
})();
