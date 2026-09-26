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
let viewerAppearance = null;

const AVATAR_ASSET_ROOT = '/static/images/avatars/';
const avatarOptions = ['avatar-1', 'avatar-2', 'avatar-3', 'avatar-4'];
const headwearOptions = ['headwear-1', 'headwear-2', 'headwear-3', 'headwear-4', 'headwear-5', 'headwear-6', 'headwear-7', 'headwear-8', 'headwear-9'];
const AVATAR_CALIBRATION_REFERENCE = 680;
const avatarBaseLayout = {scale: 0.77, x: 0, y: 138};
const headwearLayouts = {
    'headwear-1': {enabled: true, scale: 0.83, x: 0, y: -146, layerOrder: 'avatar-top'},
    'headwear-2': {enabled: true, scale: 0.75, x: 0, y: -62, layerOrder: 'avatar-top'},
    'headwear-3': {enabled: true, scale: 1.29, x: 0, y: 129, layerOrder: 'headwear-top'},
    'headwear-4': {enabled: true, scale: 1, x: 0, y: 0, layerOrder: 'avatar-top'},
    'headwear-5': {enabled: true, scale: 0.75, x: 0, y: -57, layerOrder: 'headwear-top'},
    'headwear-6': {enabled: true, scale: 0.91, x: 0, y: -88, layerOrder: 'avatar-top'},
    'headwear-7': {enabled: true, scale: 0.86, x: 0, y: -124, layerOrder: 'avatar-top'},
    'headwear-8': {enabled: true, scale: 0.84, x: 0, y: 0, layerOrder: 'avatar-top'},
    'headwear-9': {enabled: true, scale: 0.95, x: 0, y: -200, layerOrder: 'avatar-top'},
};

function colorFor(id) {
    return ['#82aeea', '#e7a86f', '#8bd5aa', '#c69ee7', '#e78392'][id % 5];
}

function normalizedAppearance(appearance = {}) {
    const headwear = appearance.headwear;
    return {
        avatar: avatarOptions.includes(appearance.avatar) ? appearance.avatar : avatarOptions[0],
        headwear: headwear === null ? null : (headwearOptions.includes(headwear) ? headwear : headwearOptions[0]),
    };
}

function appearanceKey(participant) {
    const appearance = normalizedAppearance(participant.appearance);
    return `${appearance.avatar}:${appearance.headwear}`;
}

function calibratedTransform(layout) {
    const x = (layout.x / AVATAR_CALIBRATION_REFERENCE) * 100;
    const y = (layout.y / AVATAR_CALIBRATION_REFERENCE) * 100;
    return `translate(${x}%, ${y}%) scale(${layout.scale})`;
}

function createAvatarArt(appearance, className = 'player-avatar-art') {
    const resolved = normalizedAppearance(appearance);
    const art = document.createElement('div');
    art.className = className;
    const avatar = document.createElement('img');
    avatar.className = 'player-avatar-base';
    avatar.src = `${AVATAR_ASSET_ROOT}${resolved.avatar}.png`;
    avatar.alt = '';
    avatar.style.transform = calibratedTransform(avatarBaseLayout);
    art.appendChild(avatar);
    if (resolved.headwear) {
        const layout = headwearLayouts[resolved.headwear];
        const headwear = document.createElement('img');
        headwear.className = 'player-avatar-headwear';
        headwear.src = `${AVATAR_ASSET_ROOT}${resolved.headwear}.png`;
        headwear.alt = '';
        headwear.style.transform = calibratedTransform(layout);
        const headwearIsTop = layout.layerOrder === 'headwear-top';
        avatar.style.zIndex = headwearIsTop ? '2' : '4';
        headwear.style.zIndex = headwearIsTop ? '4' : '2';
        headwear.hidden = !layout.enabled;
        art.appendChild(headwear);
    }
    return art;
}

function updateAvatarPicker(appearance) {
    const picker = document.getElementById('avatarPicker');
    const preview = document.getElementById('avatarPreview');
    if (!picker || !preview) return;
    viewerAppearance = normalizedAppearance(appearance);
    preview.replaceChildren(createAvatarArt(viewerAppearance, 'player-avatar-art player-avatar-art-preview'));
    document.getElementById('avatarChoice').textContent = `${String(avatarOptions.indexOf(viewerAppearance.avatar) + 1).padStart(2, '0')} / 04`;
    document.getElementById('headwearChoice').textContent = viewerAppearance.headwear
        ? `${String(headwearOptions.indexOf(viewerAppearance.headwear) + 1).padStart(2, '0')} / ${String(headwearOptions.length).padStart(2, '0')}`
        : 'БЕЗ УБОРУ';
}

function resetScene(participants, boosts = {}) {
    sceneParticipants = participants;
    sceneBoosts = boosts;
    sceneKey = participants.map(participant => `${participant.id}:${appearanceKey(participant)}:${boosts[String(participant.id)]?.active ? 'boost' : 'normal'}`).join(',');
    sceneEpoch = Math.floor((Date.now() + clockOffset) / SCENE_MS) * SCENE_MS;
    simulatedFrame = 0;
    avatarLayer.replaceChildren();
    avatars.clear();

    participants.forEach((participant, index) => {
        const node = document.createElement('div');
        node.className = 'dvd-avatar';
        if (String(participant.id) === String(viewerId)) node.classList.add('me');
        node.style.setProperty('--avatar-color', colorFor(participant.id));
        node.appendChild(createAvatarArt(participant.appearance));
        const name = document.createElement('small');
        name.textContent = participant.name;
        node.appendChild(name);
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
        if (data.current_activity_type === 'duel' && !isHost) { window.location.href = '/activity'; return; }
        if (data.status === 'active' && data.has_active_attempt && !isHost) { window.location.href = '/quiz'; return; }
        const key = data.participants.map(participant => `${participant.id}:${appearanceKey(participant)}:${data.boosts[String(participant.id)]?.active ? 'boost' : 'normal'}`).join(',');
        if (key !== sceneKey) resetScene(data.participants, data.boosts);
        const currentParticipant = data.participants.find(participant => String(participant.id) === String(viewerId));
        if (currentParticipant) updateAvatarPicker(currentParticipant.appearance);
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

document.querySelectorAll('[data-avatar-part]').forEach(button => {
    button.addEventListener('click', async () => {
        if (!viewerAppearance || button.disabled) return;
        const part = button.dataset.avatarPart;
        const options = part === 'headwear' ? headwearOptions : avatarOptions;
        const direction = Number(button.dataset.avatarDirection);
        const nextAppearance = {...viewerAppearance};
        const currentIndex = options.indexOf(nextAppearance[part]);
        nextAppearance[part] = currentIndex === -1
            ? options[direction > 0 ? 0 : options.length - 1]
            : options[(currentIndex + direction + options.length) % options.length];
        updateAvatarPicker(nextAppearance);
        button.disabled = true;
        try {
            const response = await fetch('/api/profile/avatar', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({appearance: nextAppearance}),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || 'Не вдалося зберегти персонажа.');
            updateAvatarPicker(data.appearance);
            const updatedParticipants = sceneParticipants.map(participant =>
                String(participant.id) === String(viewerId)
                    ? {...participant, appearance: data.appearance}
                    : participant
            );
            resetScene(updatedParticipants, sceneBoosts);
        } catch (error) {
            showToast(error.message || 'Не вдалося зберегти персонажа.', {type: 'error'});
            pollLobby();
        } finally {
            button.disabled = false;
        }
    });
});

const removeHeadwearButton = document.getElementById('removeHeadwear');
if (removeHeadwearButton) {
    removeHeadwearButton.addEventListener('click', async () => {
        if (!viewerAppearance || viewerAppearance.headwear === null || removeHeadwearButton.disabled) return;
        const nextAppearance = {...viewerAppearance, headwear: null};
        updateAvatarPicker(nextAppearance);
        removeHeadwearButton.disabled = true;
        try {
            const response = await fetch('/api/profile/avatar', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({appearance: nextAppearance}),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || 'Не вдалося оновити персонажа.');
            updateAvatarPicker(data.appearance);
            resetScene(sceneParticipants.map(participant => String(participant.id) === String(viewerId)
                ? {...participant, appearance: data.appearance} : participant), sceneBoosts);
        } catch (error) {
            showToast(error.message || 'Не вдалося оновити персонажа.', {type: 'error'});
            pollLobby();
        } finally {
            removeHeadwearButton.disabled = false;
        }
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

connectRoomSocket({
    state(state) {
        if (isHost && state.room_status !== 'lobby') {
            window.location.href = '/admin';
            return;
        }
        if (!isHost && state.activity_type === 'duel') {
            window.location.href = '/activity';
            return;
        }
        if (!isHost && state.activity_type === 'quiz' && state.activity_status === 'active') {
            window.location.href = '/quiz';
            return;
        }
        pollLobby();
    },
    presence() { pollLobby(); },
});
pollLobby();
requestAnimationFrame(animate);
