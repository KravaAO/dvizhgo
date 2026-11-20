connectRoomSocket({
    state(state) {
        if (state.activity_type === 'drawing') { window.location.href = '/drawing'; return; }
        if (['duel', 'flash_question'].includes(state.activity_type)) window.location.href = '/activity';
    },
    duel() { window.location.href = '/activity'; },
});
