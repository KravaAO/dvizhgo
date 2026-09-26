const avatarLayer = document.getElementById('dvdAvatars');
const lobbyCount = document.getElementById('lobbyCount');
const isHost = document.body.dataset.host === 'true';
const avatars = new Map();
const FRAME_MS = 1000 / 60;
const SCENE_MS = 60000;
let clockOffset = 0;
let sceneKey = '';
let sceneEpoch = 0;
let simulatedFrame = 0;
let sceneParticipants = [];
let sceneBoosts = {};
let viewerId = null;

function colorFor(id) {
    return ['#82aeea', '#e7a86f', '#8bd5aa', '#c69ee7', '#e78392'][id % 5];
}

function resetScene(participants, boosts = {}) {
    sceneParticipants = participants;
    sceneBoosts = boosts;
    sceneKey = participants.map(participant => `${participant.id}:${boosts[String(participant.id)]?.active ? 'boost' : 'normal'}`).join(',');
    sceneEpoch = Math.floor((Date.now() + clockOffset) / SCENE_MS) * SCENE_MS;
    simulatedFrame = 0;
    avatarLayer.replaceChildren();
    avatars.clear();

    participants.forEach((participant, index) => {
        const node = document.createElement('div');
        node.className = 'dvd-avatar';
        if (String(participant.id) === String(viewerId)) node.classList.add('me');
        node.style.setProperty('--avatar-color', colorFor(participant.id));
        const mark = document.createElement('span');
        mark.textContent = 'DVD';
        const name = document.createElement('small');
        name.textContent = participant.name;
        node.append(mark, name);
        avatarLayer.appendChild(node);
        avatars.set(String(participant.id), {
            node,
            x: 18 + ((participant.id * 37 + index * 19) % 620),
            y: 14 + ((participant.id * 29 + index * 23) % 180),
            dx: .8 + (participant.id % 4) * .12,
            dy: .65 + (participant.id % 3) * .13,
            boosted: Boolean(boosts[String(participant.id)]?.active),
        });
    });
}

function advanceOneFrame() {
    const bounds = avatarLayer.getBoundingClientRect();
    const items = [...avatars.values()];
    items.forEach(avatar => {
        const size = avatar.node.offsetWidth || 82;
        const speed = avatar.boosted ? 2.4 : 1;
        avatar.x += avatar.dx * speed;
        avatar.y += avatar.dy * speed;
        if (avatar.x <= 0 || avatar.x + size >= bounds.width) avatar.dx *= -1;
        if (avatar.y <= 0 || avatar.y + size >= bounds.height) avatar.dy *= -1;
        avatar.x = Math.max(0, Math.min(bounds.width - size, avatar.x));
        avatar.y = Math.max(0, Math.min(bounds.height - size, avatar.y));
    });

    for (let index = 0; index < items.length; index += 1) {
        for (let otherIndex = index + 1; otherIndex < items.length; otherIndex += 1) {
            const first = items[index];
            const second = items[otherIndex];
            const size = first.node.offsetWidth || 82;
            const overlaps = first.x < second.x + size && first.x + size > second.x
                && first.y < second.y + size && first.y + size > second.y;
            if (!overlaps) continue;
            const horizontalGap = (first.x + size / 2) - (second.x + size / 2);
            const verticalGap = (first.y + size / 2) - (second.y + size / 2);
            if (Math.abs(horizontalGap) >= Math.abs(verticalGap)) {
                const direction = Math.sign(horizontalGap || 1);
                first.dx = Math.abs(first.dx) * direction;
                second.dx = -Math.abs(second.dx) * direction;
                first.x += direction * 2;
                second.x -= direction * 2;
            } else {
                const direction = Math.sign(verticalGap || 1);
                first.dy = Math.abs(first.dy) * direction;
                second.dy = -Math.abs(second.dy) * direction;
                first.y += direction * 2;
                second.y -= direction * 2;
            }
        }
    }
}

function animate() {
    if (!sceneKey) {
        requestAnimationFrame(animate);
        return;
    }
    const now = Date.now() + clockOffset;
    const epoch = Math.floor(now / SCENE_MS) * SCENE_MS;
    if (epoch !== sceneEpoch) resetScene(sceneParticipants, sceneBoosts);
    const targetFrame = Math.floor((now - sceneEpoch) / FRAME_MS);
    while (simulatedFrame < targetFrame) {
        advanceOneFrame();
        simulatedFrame += 1;
    }
    avatars.forEach(avatar => { avatar.node.style.transform = `translate(${avatar.x}px, ${avatar.y}px)`; });
    requestAnimationFrame(animate);
}

async function pollLobby() {
    try {
        const response = await fetch('/api/lobby');
        if (!response.ok) return;
        const data = await response.json();
        clockOffset = Date.parse(data.server_time) - Date.now();
        viewerId = data.viewer_id;
        if (data.status === 'active' && !isHost) { window.location.href = '/quiz'; return; }
        const key = data.participants.map(participant => `${participant.id}:${data.boosts[String(participant.id)]?.active ? 'boost' : 'normal'}`).join(',');
        if (key !== sceneKey) resetScene(data.participants, data.boosts);
        lobbyCount.textContent = `${data.participants.length} учасник${data.participants.length === 1 ? '' : data.participants.length < 5 ? 'и' : 'ів'} у лобі`;
        if (data.boost_enabled) updateBoostButton(data.boosts[String(data.viewer_id)]);
    } catch (error) { console.error(error); }
}

function updateBoostButton(boost) {
    const button = document.getElementById('boostButton');
    if (!button) return;
    const cooldown = boost?.cooldown_seconds || 0;
    button.disabled = cooldown > 0;
    button.textContent = cooldown ? `⚡ Буст · ${cooldown}с` : '⚡ Буст';
}

const boostButton = document.getElementById('boostButton');
if (boostButton) {
    boostButton.addEventListener('click', async () => {
        const response = await fetch('/api/lobby/boost', {method: 'POST'});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) return showToast(data.error || 'Буст не спрацював.', {type: 'error'});
        showToast('⚡ Буст увімкнено на 5 секунд!', {type: 'success'});
        pollLobby();
    });
}

if (isHost) {
    document.getElementById('startQuiz').addEventListener('click', async () => {
        const button = document.getElementById('startQuiz');
        if (button.disabled) return;
        button.disabled = true;
        for (let seconds = 3; seconds > 0; seconds -= 1) {
            button.textContent = `Старт через ${seconds}…`;
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
        const response = await fetch('/api/lobby/start', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({mode: document.getElementById('roomMode').value})});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) { button.disabled = false; button.textContent = 'Почати — дати завдання →'; return showToast(data.error || 'Не вдалося розпочати квіз.', {type: 'error'}); }
        button.textContent = 'Квіз розпочато';
        showToast('Учасники отримали завдання.', {type: 'success'});
        setTimeout(() => { window.location.href = '/admin'; }, 500);
    });
}

pollLobby();
setInterval(pollLobby, 2500);
requestAnimationFrame(animate);
