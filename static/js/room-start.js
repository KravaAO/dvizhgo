async function launchRoomActivity(button, roomMode) {
    const label = button.textContent;
    button.disabled = true;
    try {
        for (let seconds = 3; seconds > 0; seconds -= 1) {
            button.textContent = `Старт через ${seconds}…`;
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
        const response = await fetch(button.dataset.startUrl, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({expected_room_mode: roomMode}),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const error = new Error(data.error || 'Не вдалося розпочати активність.');
            error.roomMode = data.room_mode;
            throw error;
        }
        window.location.assign(data.redirect_url);
    } catch (error) {
        button.textContent = label;
        button.disabled = false;
        throw error;
    }
}
