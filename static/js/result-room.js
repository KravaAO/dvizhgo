connectRoomSocket({
    state(state) {
        if (state.activity_type === 'duel') window.location.href = '/activity';
    },
    duel() { window.location.href = '/activity'; },
});
