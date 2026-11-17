connectRoomSocket({
    state(state) {
        if (['duel', 'flash_question'].includes(state.activity_type)) window.dvNavigate('/activity');
    },
    duel() { window.dvNavigate('/activity'); },
});
