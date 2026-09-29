const avatarLayer = document.getElementById('dvdAvatars');
const lobbyCount = document.getElementById('lobbyCount');
const isHost = document.body.dataset.host === 'true';
const avatars = new Map();
const LOGICAL_WIDTH = 1000;
const LOGICAL_HEIGHT = 600;
// Canonical DVD square is 72px in the participant lobby. Keeping the
// collision box at the same size prevents an invisible early bounce gap.
const LOGICAL_AVATAR_SIZE = 72;
const DVD_MIN_VIEWPORT_WIDTH = 640;
const PHYSICS_STEP = 1 / 60;
const BASE_SPEED_X = 96;
const BASE_SPEED_Y = 76;
const BOOST_IMPULSE_MULTIPLIER = 2.15;
const BOOST_COLLISION_MASS = 2.6;
let clockOffset = 0;
let sceneParticipants = [];
let sceneBoosts = {};
let viewerId = null;
let viewerAppearance = null;
let latestBoost = null;
let lastAnimationAt = performance.now();
let physicsAccumulator = 0;
let dvdMotionEnabled = null;
const dvdDiagnostics = {
    frames: 0,
    collisions: 0,
    droppedFrames: 0,
    maxFrameMs: 0,
    maxCorrectionPx: 0,
    reconciles: 0,
};

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

function axisState(participantId, salt, serverTimeSeconds, range, speed) {
    const seed = Math.abs(Math.sin(participantId * 12.9898 + salt * 78.233)) % 1;
    const travel = (seed * range * 2 + serverTimeSeconds * speed) % (range * 2);
    return travel <= range
        ? {position: travel, direction: 1}
        : {position: range * 2 - travel, direction: -1};
}

function createMotionState(participant, node, occupiedStates = avatars) {
    const serverSeconds = (Date.now() + clockOffset) / 1000;
    const speedX = BASE_SPEED_X + (participant.id * 17 % 35);
    const speedY = BASE_SPEED_Y + (participant.id * 13 % 29);
    const horizontal = axisState(participant.id, 1, serverSeconds, LOGICAL_WIDTH - LOGICAL_AVATAR_SIZE, speedX);
    const vertical = axisState(participant.id, 2, serverSeconds, LOGICAL_HEIGHT - LOGICAL_AVATAR_SIZE, speedY);
    let x = horizontal.position;
    let y = vertical.position;

    for (let attempt = 0; attempt < 24; attempt += 1) {
        const overlaps = [...occupiedStates.values()].some(avatar =>
            x < avatar.x + LOGICAL_AVATAR_SIZE && x + LOGICAL_AVATAR_SIZE > avatar.x
            && y < avatar.y + LOGICAL_AVATAR_SIZE && y + LOGICAL_AVATAR_SIZE > avatar.y
        );
        if (!overlaps) break;
        x = (x + 137) % (LOGICAL_WIDTH - LOGICAL_AVATAR_SIZE);
        y = (y + 83) % (LOGICAL_HEIGHT - LOGICAL_AVATAR_SIZE);
    }

    return {
        id: String(participant.id), node, x, y,
        dx: speedX * horizontal.direction,
        dy: speedY * vertical.direction,
        cruiseSpeed: Math.hypot(speedX, speedY),
        appearanceKey: appearanceKey(participant),
        boostedUntil: 0,
        appliedBoostUntil: 0,
        lastBump: 0,
    };
}

function applyBoostState(avatar, boost) {
    const boostedUntil = Date.parse(boost?.boosted_until || 0);
    const serverNow = Date.now() + clockOffset;
    avatar.boostedUntil = boostedUntil;
    if (boostedUntil <= serverNow || boostedUntil === avatar.appliedBoostUntil) return;

    const currentSpeed = Math.hypot(avatar.dx, avatar.dy) || avatar.cruiseSpeed;
    const impulseSpeed = avatar.cruiseSpeed * BOOST_IMPULSE_MULTIPLIER;
    avatar.dx = avatar.dx / currentSpeed * impulseSpeed;
    avatar.dy = avatar.dy / currentSpeed * impulseSpeed;
    avatar.appliedBoostUntil = boostedUntil;
    avatar.node.classList.remove('boost-fired');
    requestAnimationFrame(() => avatar.node.classList.add('boost-fired'));
    window.setTimeout(() => avatar.node.classList.remove('boost-fired'), 260);
}

function reseedMotionAtCurrentTime() {
    const placed = new Map();
    sceneParticipants.forEach(participant => {
        const id = String(participant.id);
        const previous = avatars.get(id);
        if (!previous) return;
        const next = createMotionState(participant, previous.node, placed);
        applyBoostState(next, sceneBoosts[id]);
        placed.set(id, next);
    });
    avatars.clear();
    placed.forEach((avatar, id) => avatars.set(id, avatar));
}

function stageLayout() {
    const bounds = avatarLayer.getBoundingClientRect();
    const enabled = window.innerWidth >= DVD_MIN_VIEWPORT_WIDTH
        && bounds.width > 0
        && bounds.height > 0;
    if (dvdMotionEnabled !== enabled) {
        if (dvdMotionEnabled === false && enabled) reseedMotionAtCurrentTime();
        dvdMotionEnabled = enabled;
        avatarLayer.classList.toggle('dvd-motion-disabled', !enabled);
        avatarLayer.setAttribute('aria-live', enabled ? 'off' : 'polite');
        lastAnimationAt = performance.now();
        physicsAccumulator = 0;
    }
    if (!enabled) return {enabled: false, bounds};
    const scale = Math.min(bounds.width / LOGICAL_WIDTH, bounds.height / LOGICAL_HEIGHT);
    return {
        enabled: true,
        bounds,
        scale,
        offsetX: (bounds.width - LOGICAL_WIDTH * scale) / 2,
        offsetY: (bounds.height - LOGICAL_HEIGHT * scale) / 2,
    };
}

function fillAvatarNode(node, participant) {
    node.replaceChildren(createAvatarArt(participant.appearance));
    const name = document.createElement('small');
    name.textContent = participant.name;
    node.appendChild(name);
}

function resetScene(participants, boosts = {}) {
    sceneParticipants = participants;
    sceneBoosts = boosts;
    const desiredIds = new Set(participants.map(participant => String(participant.id)));
    avatars.forEach((avatar, id) => {
        if (desiredIds.has(id)) return;
        avatar.node.remove();
        avatars.delete(id);
    });

    participants.forEach((participant, index) => {
        const id = String(participant.id);
        const existing = avatars.get(id);
        if (existing) {
            const nextAppearanceKey = appearanceKey(participant);
            if (existing.appearanceKey !== nextAppearanceKey) {
                fillAvatarNode(existing.node, participant);
                existing.appearanceKey = nextAppearanceKey;
            }
            applyBoostState(existing, boosts[id]);
            return;
        }
        const node = document.createElement('div');
        node.className = 'dvd-avatar';
        if (String(participant.id) === String(viewerId)) node.classList.add('me');
        node.style.setProperty('--avatar-color', colorFor(participant.id));
        fillAvatarNode(node, participant);
        avatarLayer.appendChild(node);
        const state = createMotionState(participant, node);
        applyBoostState(state, boosts[id]);
        avatars.set(id, state);
    });
    dvdDiagnostics.reconciles += 1;
}

function triggerBump(avatar, timestamp, strong = false) {
    if (timestamp - avatar.lastBump < 170) return;
    avatar.lastBump = timestamp;
    const className = strong ? 'boost-hit' : 'bumped';
    avatar.node.classList.remove(className);
    requestAnimationFrame(() => avatar.node.classList.add(className));
    window.setTimeout(() => avatar.node.classList.remove(className), strong ? 240 : 180);
}

function stabilizeSpeed(avatar, step, serverNow) {
    const boosted = avatar.boostedUntil > serverNow;
    const targetSpeed = avatar.cruiseSpeed * (boosted ? BOOST_IMPULSE_MULTIPLIER : 1);
    const currentSpeed = Math.hypot(avatar.dx, avatar.dy);
    if (!currentSpeed) return;
    const response = boosted ? .8 : 2.4;
    const nextSpeed = currentSpeed + (targetSpeed - currentSpeed) * Math.min(1, response * step);
    const limitedSpeed = Math.min(nextSpeed, avatar.cruiseSpeed * 2.75);
    avatar.dx *= limitedSpeed / currentSpeed;
    avatar.dy *= limitedSpeed / currentSpeed;
}

function advanceOneFrame(step, serverNow) {
    const items = [...avatars.values()];
    items.forEach(avatar => {
        stabilizeSpeed(avatar, step, serverNow);
        avatar.x += avatar.dx * step;
        avatar.y += avatar.dy * step;
        const boosted = avatar.boostedUntil > serverNow;
        const wallRestitution = boosted ? 1.08 : 1;
        let hitWall = false;
        if (avatar.x <= 0) {
            avatar.x = 0;
            avatar.dx = Math.abs(avatar.dx) * wallRestitution;
            hitWall = true;
        }
        if (avatar.x + LOGICAL_AVATAR_SIZE >= LOGICAL_WIDTH) {
            avatar.x = LOGICAL_WIDTH - LOGICAL_AVATAR_SIZE;
            avatar.dx = -Math.abs(avatar.dx) * wallRestitution;
            hitWall = true;
        }
        if (avatar.y <= 0) {
            avatar.y = 0;
            avatar.dy = Math.abs(avatar.dy) * wallRestitution;
            hitWall = true;
        }
        if (avatar.y + LOGICAL_AVATAR_SIZE >= LOGICAL_HEIGHT) {
            avatar.y = LOGICAL_HEIGHT - LOGICAL_AVATAR_SIZE;
            avatar.dy = -Math.abs(avatar.dy) * wallRestitution;
            hitWall = true;
        }
        if (hitWall) triggerBump(avatar, performance.now(), boosted);
    });

    for (let index = 0; index < items.length; index += 1) {
        for (let otherIndex = index + 1; otherIndex < items.length; otherIndex += 1) {
            const first = items[index];
            const second = items[otherIndex];
            const overlapX = Math.min(first.x, second.x) + LOGICAL_AVATAR_SIZE
                - Math.max(first.x, second.x);
            const overlapY = Math.min(first.y, second.y) + LOGICAL_AVATAR_SIZE
                - Math.max(first.y, second.y);
            if (overlapX <= 0 || overlapY <= 0) continue;

            let normalX = 0;
            let normalY = 0;
            let penetration = 0;
            if (overlapX < overlapY) {
                const firstIsLeft = first.x < second.x
                    || (first.x === second.x && Number(first.id) < Number(second.id));
                normalX = firstIsLeft ? 1 : -1;
                penetration = overlapX;
            } else {
                const firstIsAbove = first.y < second.y
                    || (first.y === second.y && Number(first.id) < Number(second.id));
                normalY = firstIsAbove ? 1 : -1;
                penetration = overlapY;
            }

            // Correct only the overlap. The cap prevents a newly joined avatar
            // or a crowded corner from visibly teleporting in a single frame.
            const correction = Math.min(4, Math.max(0, penetration - .25) * .5);
            first.x -= normalX * correction;
            first.y -= normalY * correction;
            second.x += normalX * correction;
            second.y += normalY * correction;
            dvdDiagnostics.maxCorrectionPx = Math.max(dvdDiagnostics.maxCorrectionPx, correction);

            // Equal-mass collision impulse. Apply it only while the avatars are
            // moving towards each other; repeated overlap frames no longer
            // reverse their direction over and over.
            const relativeVelocityX = second.dx - first.dx;
            const relativeVelocityY = second.dy - first.dy;
            const velocityAlongNormal = relativeVelocityX * normalX + relativeVelocityY * normalY;
            if (velocityAlongNormal < 0) {
                const firstBoosted = first.boostedUntil > serverNow;
                const secondBoosted = second.boostedUntil > serverNow;
                const firstInverseMass = 1 / (firstBoosted ? BOOST_COLLISION_MASS : 1);
                const secondInverseMass = 1 / (secondBoosted ? BOOST_COLLISION_MASS : 1);
                const restitution = firstBoosted || secondBoosted ? 1.02 : .84;
                const impulse = -(1 + restitution) * velocityAlongNormal
                    / (firstInverseMass + secondInverseMass);
                first.dx -= impulse * firstInverseMass * normalX;
                first.dy -= impulse * firstInverseMass * normalY;
                second.dx += impulse * secondInverseMass * normalX;
                second.dy += impulse * secondInverseMass * normalY;
            }
            first.x = Math.max(0, Math.min(LOGICAL_WIDTH - LOGICAL_AVATAR_SIZE, first.x));
            first.y = Math.max(0, Math.min(LOGICAL_HEIGHT - LOGICAL_AVATAR_SIZE, first.y));
            second.x = Math.max(0, Math.min(LOGICAL_WIDTH - LOGICAL_AVATAR_SIZE, second.x));
            second.y = Math.max(0, Math.min(LOGICAL_HEIGHT - LOGICAL_AVATAR_SIZE, second.y));
            const bumpedAt = performance.now();
            const strongImpact = first.boostedUntil > serverNow || second.boostedUntil > serverNow;
            triggerBump(first, bumpedAt, strongImpact);
            triggerBump(second, bumpedAt, strongImpact);
            dvdDiagnostics.collisions += 1;
        }
    }
}

function animate(timestamp) {
    const layout = stageLayout();
    if (!layout.enabled) {
        window.setTimeout(() => requestAnimationFrame(animate), 250);
        return;
    }
    const frameMs = Math.min(100, Math.max(0, timestamp - lastAnimationAt));
    lastAnimationAt = timestamp;
    dvdDiagnostics.frames += 1;
    dvdDiagnostics.maxFrameMs = Math.max(dvdDiagnostics.maxFrameMs, frameMs);
    physicsAccumulator += frameMs / 1000;
    let steps = 0;
    const serverNow = Date.now() + clockOffset;
    while (physicsAccumulator >= PHYSICS_STEP && steps < 5) {
        advanceOneFrame(PHYSICS_STEP, serverNow);
        physicsAccumulator -= PHYSICS_STEP;
        steps += 1;
    }
    if (physicsAccumulator >= PHYSICS_STEP) {
        physicsAccumulator = 0;
        dvdDiagnostics.droppedFrames += 1;
    }
    avatars.forEach(avatar => {
        const renderX = layout.offsetX + avatar.x * layout.scale;
        const renderY = layout.offsetY + avatar.y * layout.scale;
        avatar.node.style.transform = `translate3d(${renderX}px, ${renderY}px, 0) scale(${layout.scale})`;
        avatar.node.classList.toggle('boosting', avatar.boostedUntil > serverNow);
    });
    requestAnimationFrame(animate);
}

async function pollLobby() {
    try {
        const response = await fetch('/api/lobby');
        if (!response.ok) return;
        const data = await response.json();
        clockOffset = Date.parse(data.server_time) - Date.now();
        viewerId = data.viewer_id;
        if (['duel', 'flash_question'].includes(data.current_activity_type) && !isHost) { window.location.href = '/activity'; return; }
        if (data.status === 'active' && data.has_active_attempt && !isHost) { window.location.href = '/quiz'; return; }
        resetScene(data.participants, data.boosts);
        const currentParticipant = data.participants.find(participant => String(participant.id) === String(viewerId));
        if (currentParticipant) updateAvatarPicker(currentParticipant.appearance);
        lobbyCount.textContent = `${data.participants.length} учасник${data.participants.length === 1 ? '' : data.participants.length < 5 ? 'и' : 'ів'} у лобі`;
        if (data.boost_enabled) {
            latestBoost = data.boosts[String(data.viewer_id)] || null;
            updateBoostButton(latestBoost);
        }
    } catch (error) { console.error(error); }
}

function updateBoostButton(boost) {
    const button = document.getElementById('boostButton');
    if (!button) return;
    const cooldown = boost?.cooldown_seconds || 0;
    button.disabled = cooldown > 0;
    button.textContent = cooldown ? `⚡ Буст · ${cooldown}с` : '⚡ Буст';
}

function dvdSnapshot() {
    return {
        participants: avatars.size,
        frames: dvdDiagnostics.frames,
        collisions: dvdDiagnostics.collisions,
        dropped_frames: dvdDiagnostics.droppedFrames,
        max_frame_ms: Math.round(dvdDiagnostics.maxFrameMs * 10) / 10,
        max_correction_px: Math.round(dvdDiagnostics.maxCorrectionPx * 10) / 10,
        reconciles: dvdDiagnostics.reconciles,
        boost_active: [...avatars.values()].some(avatar => avatar.boostedUntil > Date.now() + clockOffset),
        motion_enabled: Boolean(dvdMotionEnabled),
    };
}

window.__dvdSnapshot = dvdSnapshot;
window.setInterval(async () => {
    if (!avatars.size) return;
    const snapshot = dvdSnapshot();
    console.info('[DVD lobby]', snapshot);
    if (!isHost) {
        fetch('/api/lobby/dvd-telemetry', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(snapshot),
            keepalive: true,
        }).catch(() => {});
    }
    dvdDiagnostics.frames = 0;
    dvdDiagnostics.collisions = 0;
    dvdDiagnostics.droppedFrames = 0;
    dvdDiagnostics.maxFrameMs = 0;
    dvdDiagnostics.maxCorrectionPx = 0;
    dvdDiagnostics.reconciles = 0;
}, 10000);

window.setInterval(() => {
    if (!latestBoost?.cooldown_seconds) return;
    latestBoost = {...latestBoost, cooldown_seconds: Math.max(0, latestBoost.cooldown_seconds - 1)};
    if (!latestBoost.cooldown_seconds) latestBoost.active = false;
    updateBoostButton(latestBoost);
}, 1000);

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
        if (!isHost && ['duel', 'flash_question'].includes(state.activity_type)) {
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
