connectRoomSocket({
    state(state) {
        if (['duel', 'flash_question'].includes(state.activity_type)) window.location.href = '/activity';
    },
    duel() { window.location.href = '/activity'; },
});
