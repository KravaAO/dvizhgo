(() => {
    const form = document.getElementById('drawingSettingsForm');
    const button = form.querySelector('button[type="submit"]');
    const prompts = form.elements.prompts;
    const roundCount = document.querySelector('#drawingRoundCount output');
    const maxRounds = Number(roundCount.dataset.max);
    const status = document.getElementById('drawingSettingsStatus');

    // One round per non-empty line, so the count always matches the themes.
    const promptList = () => prompts.value.split(/\r\n?|\n/).map(prompt => prompt.trim()).filter(Boolean);
    const updateRoundCount = () => {
        const count = promptList().length;
        roundCount.value = count > maxRounds ? `${count} (максимум ${maxRounds})` : String(count);
        roundCount.parentElement.classList.toggle('is-over-limit', count > maxRounds);
    };
    prompts.addEventListener('input', updateRoundCount);
    updateRoundCount();

    form.addEventListener('submit', async event => {
        event.preventDefault();
        button.disabled = true;
        prompts.readOnly = true;
        status.textContent = 'Зберігаємо налаштування…';
        try {
            const response = await fetch(form.action, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    prompts: promptList(),
                    time_limit: Number(form.elements.time_limit.value),
                }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || 'Не вдалося зберегти теми.');
            prompts.value = data.settings.prompts.join('\n');
            form.elements.time_limit.value = String(data.settings.time_limit);
            updateRoundCount();
            status.textContent = 'Налаштування збережено';
        } catch (error) {
            status.textContent = error.message;
        } finally {
            button.disabled = false;
            prompts.readOnly = false;
        }
    });
})();
