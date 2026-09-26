(() => {
    let socket = null;
    const subscribers = new Set();

    function dispatch(eventName, payload) {
        subscribers.forEach(handlers => {
            const handler = handlers[eventName];
            if (typeof handler === 'function') handler(payload);
        });
    }

    function connectRoomSocket(handlers = {}) {
        subscribers.add(handlers);
        if (socket) return socket;
        if (typeof window.io !== 'function') return null;

        socket = window.io({
            transports: ['websocket'],
            upgrade: false,
            timeout: 10000,
            reconnection: true,
            reconnectionDelay: 700,
            reconnectionDelayMax: 5000,
        });
        window.roomSocket = socket;

        socket.on('connect', () => socket.emit('presence:heartbeat'));
        socket.on('room:state', payload => dispatch('state', payload));
        socket.on('room:presence', payload => dispatch('presence', payload));
        socket.on('room:results_updated', payload => dispatch('results', payload));
        socket.on('room:duel_updated', payload => dispatch('duel', payload));

        window.setInterval(() => {
            if (socket && socket.connected) socket.emit('presence:heartbeat');
        }, 25000);
        return socket;
    }

    window.connectRoomSocket = connectRoomSocket;
})();
