const assetRoot = document.body.dataset.assetRoot;
const storageKey = 'dvizhgo:avatar-lab:layout:v1';
const stage = document.getElementById('avatarLabStage');
const baseImage = document.getElementById('avatarLabBase');
const headwearImage = document.getElementById('avatarLabHeadwear');
const baseBounds = document.getElementById('avatarLabBaseBounds');
const headwearBounds = document.getElementById('avatarLabHeadwearBounds');
const output = document.getElementById('avatarLabValues');
const saveStatus = document.getElementById('avatarLabSaveStatus');

const options = {
    base: ['avatar-1', 'avatar-2', 'avatar-3', 'avatar-4'],
    headwear: ['headwear-1', 'headwear-2', 'headwear-3', 'headwear-4', 'headwear-5', 'headwear-6', 'headwear-7', 'headwear-8', 'headwear-9'],
};
const defaults = {
    base: {asset: options.base[0], scale: 1, x: 0, y: 0},
    headwear: {asset: options.headwear[0], enabled: true, scale: 1, x: 0, y: 0, layerOrder: 'headwear-top'},
};
const state = {base: {...defaults.base}, headwear: {...defaults.headwear}, headwearLayouts: {}};
const controlInputs = {base: {}, headwear: {}};

function numberInRange(value, fallback, min, max) {
    const numeric = Number(value);
    return Number.isFinite(numeric) && numeric >= min && numeric <= max ? numeric : fallback;
}

function validBase(value) {
    return {
        asset: options.base.includes(value?.asset) ? value.asset : defaults.base.asset,
        scale: numberInRange(value?.scale, 1, 0.4, 1.8),
        x: numberInRange(value?.x, 0, -210, 210),
        y: numberInRange(value?.y, 0, -210, 210),
    };
}

function validHeadwear(value, asset) {
    return {
        asset,
        enabled: value?.enabled !== false,
        scale: numberInRange(value?.scale, 1, 0.4, 1.8),
        x: numberInRange(value?.x, 0, -210, 210),
        y: numberInRange(value?.y, 0, -210, 210),
        layerOrder: value?.layerOrder === 'avatar-top' ? 'avatar-top' : 'headwear-top',
    };
}

function saveCurrentHeadwearInMemory() {
    if (!options.headwear.includes(state.headwear.asset)) return;
    state.headwearLayouts[state.headwear.asset] = {
        enabled: state.headwear.enabled, scale: state.headwear.scale, x: state.headwear.x,
        y: state.headwear.y, layerOrder: state.headwear.layerOrder,
    };
}

function restoreLocalLayout() {
    try {
        const saved = JSON.parse(localStorage.getItem(storageKey) || '{}');
        state.base = validBase(saved.base);
        options.headwear.forEach(asset => {
            state.headwearLayouts[asset] = validHeadwear(saved.headwearLayouts?.[asset], asset);
        });
        const selectedHat = options.headwear.includes(saved.selectedHeadwear) ? saved.selectedHeadwear : defaults.headwear.asset;
        state.headwear = {asset: selectedHat, ...state.headwearLayouts[selectedHat]};
        saveStatus.textContent = 'Завантажено локальне налаштування';
    } catch {
        options.headwear.forEach(asset => { state.headwearLayouts[asset] = validHeadwear(null, asset); });
    }
}

function createControl(layer, label, key, config) {
    const row = document.createElement('label');
    row.className = 'avatar-lab-control';
    row.innerHTML = `<span>${label}</span><input type="range" min="${config.min}" max="${config.max}" step="${config.step}"><output></output>`;
    const input = row.querySelector('input');
    const value = row.querySelector('output');
    controlInputs[layer][key] = {input, value};
    input.addEventListener('input', () => {
        state[layer][key] = Number(input.value);
        if (layer === 'headwear') saveCurrentHeadwearInMemory();
        render();
    });
    return row;
}

function syncControls() {
    for (const layer of ['base', 'headwear']) {
        for (const [key, control] of Object.entries(controlInputs[layer])) {
            control.input.value = state[layer][key];
            control.value.textContent = key === 'scale' ? `${state[layer][key].toFixed(2)}×` : `${state[layer][key]} px`;
        }
    }
    document.getElementById('avatarLabBaseSelect').value = state.base.asset;
    document.getElementById('avatarLabHeadwearSelect').value = state.headwear.asset;
    document.getElementById('avatarLabHeadwearEnabled').checked = state.headwear.enabled;
    document.getElementById('avatarLabLayerOrder').value = state.headwear.layerOrder;
}

function populateSelect(select, values) {
    values.forEach((value, index) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = `${String(index + 1).padStart(2, '0')} / ${value}`;
        select.appendChild(option);
    });
}

function transformFor(layer) {
    const item = state[layer];
    return `translate(${item.x}px, ${item.y}px) scale(${item.scale})`;
}

function updateBounds(bounds, layer) {
    const item = state[layer];
    const size = 100 * item.scale;
    const start = (100 - size) / 2;
    bounds.style.left = `calc(${start}% + ${item.x}px)`;
    bounds.style.top = `calc(${start}% + ${item.y}px)`;
    bounds.style.width = `${size}%`;
    bounds.style.height = `${size}%`;
}

function serializableLayout() {
    saveCurrentHeadwearInMemory();
    return {version: 1, base: {...state.base}, selectedHeadwear: state.headwear.asset, headwearLayouts: state.headwearLayouts};
}

function render() {
    baseImage.src = `${assetRoot}${state.base.asset}.png`;
    headwearImage.src = `${assetRoot}${state.headwear.asset}.png`;
    baseImage.style.transform = transformFor('base');
    headwearImage.style.transform = transformFor('headwear');
    const headwearIsTop = state.headwear.layerOrder === 'headwear-top';
    baseImage.style.zIndex = headwearIsTop ? '2' : '4';
    headwearImage.style.zIndex = headwearIsTop ? '4' : '2';
    headwearImage.hidden = !state.headwear.enabled;
    headwearBounds.hidden = !state.headwear.enabled;
    updateBounds(baseBounds, 'base');
    updateBounds(headwearBounds, 'headwear');
    syncControls();
    output.textContent = JSON.stringify({
        current: {avatar: state.base, headwear: {...state.headwear, z_index: Number(headwearImage.style.zIndex)}},
        saved_layout: serializableLayout(),
        stage: {size: `${Math.round(stage.getBoundingClientRect().width)}px`, origin: 'center'},
    }, null, 2);
}

function selectHeadwear(asset) {
    if (!options.headwear.includes(asset)) return;
    saveCurrentHeadwearInMemory();
    state.headwear = {asset, ...state.headwearLayouts[asset]};
    render();
}

populateSelect(document.getElementById('avatarLabBaseSelect'), options.base);
populateSelect(document.getElementById('avatarLabHeadwearSelect'), options.headwear);
for (const layer of ['base', 'headwear']) {
    const controls = document.getElementById(`avatarLab${layer === 'base' ? 'Base' : 'Headwear'}Controls`);
    controls.append(
        createControl(layer, 'МАСШТАБ', 'scale', {min: 0.4, max: 1.8, step: 0.01}),
        createControl(layer, 'X', 'x', {min: -210, max: 210, step: 1}),
        createControl(layer, 'Y', 'y', {min: -210, max: 210, step: 1}),
    );
}
restoreLocalLayout();
document.getElementById('avatarLabBaseSelect').addEventListener('change', event => { state.base.asset = event.target.value; render(); });
document.getElementById('avatarLabHeadwearSelect').addEventListener('change', event => selectHeadwear(event.target.value));
document.getElementById('avatarLabHeadwearEnabled').addEventListener('change', event => { state.headwear.enabled = event.target.checked; saveCurrentHeadwearInMemory(); render(); });
document.getElementById('avatarLabLayerOrder').addEventListener('change', event => { state.headwear.layerOrder = event.target.value; saveCurrentHeadwearInMemory(); render(); });

document.getElementById('avatarLabSave').addEventListener('click', () => {
    try {
        localStorage.setItem(storageKey, JSON.stringify(serializableLayout()));
        saveStatus.textContent = 'Збережено в цьому браузері';
    } catch {
        saveStatus.textContent = 'Не вдалося зберегти локально';
    }
});
document.getElementById('avatarLabCopy').addEventListener('click', async () => {
    try {
        await navigator.clipboard.writeText(output.textContent);
        document.getElementById('avatarLabCopy').textContent = 'Скопійовано';
        setTimeout(() => { document.getElementById('avatarLabCopy').textContent = 'Копіювати'; }, 1200);
    } catch {
        document.getElementById('avatarLabCopy').textContent = 'Виділіть JSON';
    }
});

window.addEventListener('resize', render);
render();
