(() => {
    const form = document.getElementById('drawingSettingsForm');
    const button = form.querySelector('button[type="submit"]');
    const rounds = form.elements.rounds;
    const prompts = form.elements.prompts;
    const status = document.getElementById('drawingSettingsStatus');

    form.addEventListener('submit', async event => {
        event.preventDefault();
        button.disabled = true;
        rounds.readOnly = prompts.readOnly = true;
        status.textContent = 'Зберігаємо налаштування…';
        try {
            const response = await fetch(form.action, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    rounds: rounds.valueAsNumber,
                    prompts: prompts.value.split(/\r\n?|\n/).map(prompt => prompt.trim()).filter(Boolean),
                    time_limit: Number(form.elements.time_limit.value),
                }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || 'Не вдалося зберегти теми.');
            rounds.value = data.settings.rounds;
            prompts.value = data.settings.prompts.join('\n');
            form.elements.time_limit.value = String(data.settings.time_limit);
            status.textContent = 'Налаштування збережено';
        } catch (error) {
            status.textContent = error.message;
        } finally {
            button.disabled = false;
            rounds.readOnly = prompts.readOnly = false;
        }
    });
})();
