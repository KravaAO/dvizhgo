connectRoomSocket({
    state(state) {
        if (state.activity_type === 'drawing') { window.dvNavigate('/drawing'); return; }
        if (['duel', 'flash_question'].includes(state.activity_type)) window.dvNavigate('/activity');
    },
    duel() { window.dvNavigate('/activity'); },
});
