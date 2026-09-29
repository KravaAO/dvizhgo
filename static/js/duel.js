const wheelShell = document.querySelector('.roulette-wheel-shell');
const wheel = document.getElementById('duelWheel');
const wheelName = document.getElementById('duelWheelName');
const wheelCandidates = document.getElementById('duelWheelCandidates');
const question = document.getElementById('duelQuestion');
const participants = document.getElementById('duelParticipants');
const action = document.getElementById('duelAction');
const notice = document.getElementById('duelNotice');
let displayedRoundId = null;
let presentationReadyRoundId = null;
let latestRound = null;
let spinningTimer = null;
let spinFinishTimer = null;
let answerDraft = '';

function wait(milliseconds) {
    return new Promise(resolve => window.setTimeout(resolve, milliseconds));
}

function stopWheelTimers() {
    window.clearInterval(spinningTimer);
    window.clearTimeout(spinFinishTimer);
    spinningTimer = null;
    spinFinishTimer = null;
}

function candidateNamesWithoutFirstSelection(round) {
    const names = [...round.candidate_pool];
    const firstNameIndex = names.indexOf(round.participants[0]?.name);
    if (firstNameIndex >= 0) names.splice(firstNameIndex, 1);
    return names.length ? names : round.participants.slice(1).map(item => item.name);
}

function renderWheelCandidates(names) {
    const visibleNames = names.slice(0, 16);
    wheelCandidates.replaceChildren(...visibleNames.map((name, index) => {
        const label = document.createElement('span');
        const angle = (360 / visibleNames.length) * index;
        const radians = angle * Math.PI / 180;
        label.textContent = name;
        label.style.left = `${50 + 39 * Math.sin(radians)}%`;
        label.style.top = `${50 - 39 * Math.cos(radians)}%`;
        return label;
    }));
}

function spinOnce(names, selectedName, positionLabel) {
    return new Promise(resolve => {
        stopWheelTimers();
        renderWheelCandidates(names);
        let index = Math.floor(Math.random() * Math.max(1, names.length));
        wheel.classList.add('spinning');
        wheelName.textContent = names[index % names.length] || selectedName;
        spinningTimer = window.setInterval(() => {
            wheelName.textContent = names[index++ % names.length] || selectedName;
        }, 105);
        spinFinishTimer = window.setTimeout(() => {
            stopWheelTimers();
            wheel.classList.remove('spinning');
            wheelName.textContent = `${positionLabel}: ${selectedName}`;
            resolve();
        }, 1900);
    });
}

function selectionCard(item, labelText) {
    const card = document.createElement('article');
    card.className = 'roulette-person duel-selected-person';
    const label = document.createElement('span');
    label.className = 'roulette-person-label';
    label.textContent = labelText;
    const name = document.createElement('strong');
    name.textContent = item.name;
    card.append(label, name);
    return card;
}

function showSelectedParticipants(round, count) {
    participants.classList.add('duel-participants-selected');
    participants.replaceChildren(...round.participants.slice(0, count).map((item, index) => (
        selectionCard(item, index === 0 ? 'ПЕРШИЙ УЧАСНИК' : 'ДРУГИЙ УЧАСНИК')
    )));
}

async function startSelectionSequence(round) {
    wheelShell.classList.remove('duel-wheel-shell-hidden');
    wheel.classList.remove('spinning');
    wheelName.textContent = 'ОБИРАЄМО ПЕРШОГО…';
    question.textContent = '';
    participants.classList.remove('duel-participants-selected');
    participants.replaceChildren();
    action.replaceChildren();
    notice.textContent = 'Перше обертання обирає першого учасника.';

    const first = round.participants[0];
    const second = round.participants[1];
    const firstPool = round.candidate_pool.length ? round.candidate_pool : round.participants.map(item => item.name);
    await spinOnce(firstPool, first.name, 'ПЕРШИЙ');
    if (displayedRoundId !== round.id) return;
    showSelectedParticipants(round, 1);
    notice.textContent = `${first.name} — перший учасник. Готуємо друге обертання.`;
    await wait(850);

    if (displayedRoundId !== round.id) return;
    notice.textContent = 'Друге обертання обирає іншого учасника.';
    await spinOnce(candidateNamesWithoutFirstSelection(round), second.name, 'ДРУГИЙ');
    if (displayedRoundId !== round.id) return;
    showSelectedParticipants(round, 2);
    notice.textContent = `${first.name} та ${second.name} — пара ДВИЖ-ДУЕЛІ.`;
    await wait(750);

    if (displayedRoundId !== round.id) return;
    await window.playExtraIntro({type: 'duel', names: [first.name, second.name]});
    if (displayedRoundId !== round.id) return;
    presentationReadyRoundId = round.id;
    render(latestRound || round);
}

function writingIndicator() {
    const indicator = document.createElement('span');
    indicator.className = 'duel-writing-indicator';
    indicator.setAttribute('aria-label', 'Пише відповідь');
    indicator.append(document.createElement('i'), document.createElement('i'), document.createElement('i'));
    return indicator;
}

function renderAnsweringParticipants(round) {
    participants.classList.add('duel-participants-selected');
    participants.replaceChildren(...round.participants.map((item, index) => {
        const card = selectionCard(item, index === 0 ? 'УЧАСНИК 01' : 'УЧАСНИК 02');
        const state = document.createElement('div');
        state.className = `duel-writing-state ${item.answer_text ? 'is-ready' : 'is-writing'}`;
        const stateText = document.createElement('span');
        stateText.textContent = item.answer_text ? 'ВІДПОВІДЬ ГОТОВА' : 'ПИШЕ ВІДПОВІДЬ';
        state.appendChild(stateText);
        if (item.answer_text) {
            const readyMark = document.createElement('strong');
            readyMark.textContent = '✓';
            state.appendChild(readyMark);
        } else {
            state.appendChild(writingIndicator());
        }
        card.appendChild(state);
        return card;
    }));
}

async function send(url, payload) {
    const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'Не вдалося виконати дію.');
    return data;
}

function render(round) {
    if (!round) { window.location.href = '/lobby'; return; }
    latestRound = round;
    if (displayedRoundId !== round.id) {
        displayedRoundId = round.id;
        presentationReadyRoundId = null;
        startSelectionSequence(round).catch(error => {
            console.error(error);
            showToast('Не вдалося відтворити вступ ДВИЖ-ДУЕЛІ.', {type:'error'});
        });
        return;
    }
    if (presentationReadyRoundId !== round.id) return;

    wheelShell.classList.add('duel-wheel-shell-hidden');
    question.textContent = `Питання кімнати: ${round.question}`;
    action.replaceChildren();
    notice.textContent = '';

    if (round.status === 'answering') {
        renderAnsweringParticipants(round);
        if (!round.can_answer) {
            notice.textContent = 'Очікуємо відповіді обох учасників.';
            return;
        }
        const form = document.createElement('form');
        form.className = 'roulette-form';
        form.innerHTML = '<textarea name="answer" maxlength="1000" required placeholder="Напишіть свою відповідь…"></textarea><button class="primary-btn" type="submit">Надіслати відповідь</button>';
        form.elements.answer.value = answerDraft;
        form.elements.answer.addEventListener('input', () => { answerDraft = form.elements.answer.value; });
        form.addEventListener('submit', async event => {
            event.preventDefault();
            try {
                await send('/api/roulette/answer', {answer: form.elements.answer.value.trim()});
                answerDraft = '';
                poll();
            } catch (error) {
                showToast(error.message, {type:'error'});
            }
        });
        action.append(form);
        return;
    }

    participants.classList.remove('duel-participants-selected');
    participants.replaceChildren();
    const list = document.createElement('div');
    list.className = 'roulette-answer-list';
    round.participants.forEach(item => {
        const card = document.createElement('article');
        card.className = 'roulette-answer';
        if (round.user_vote === item.student_id) card.classList.add('is-selected');
        const owner = document.createElement('header');
        owner.className = 'roulette-answer-owner';
        const avatar = document.createElement('span');
        avatar.className = 'roulette-answer-owner-avatar';
        avatar.textContent = String(item.name || '?').trim().slice(0, 1).toUpperCase();
        const ownerCopy = document.createElement('div');
        const ownerLabel = document.createElement('small');
        ownerLabel.textContent = 'ВІДПОВІДЬ УЧАСНИКА';
        const title = document.createElement('strong');
        title.textContent = item.name;
        ownerCopy.append(ownerLabel, title);
        owner.append(avatar, ownerCopy);
        const text = document.createElement('p');
        text.textContent = item.answer_text || 'Готує відповідь…';
        card.append(owner, text);
        if (round.can_vote) {
            const button = document.createElement('button');
            button.className = 'secondary-btn';
            button.type = 'button';
            button.textContent = `👍 Голос за ${item.name} (${item.votes})`;
            button.onclick = async () => {
                try {
                    await send('/api/roulette/vote', {choice_student_id:item.student_id});
                    poll();
                } catch (error) {
                    showToast(error.message, {type:'error'});
                }
            };
            card.append(button);
        } else {
            const votes = document.createElement('span');
            votes.textContent = `👍 ${item.votes}`;
            card.append(votes);
        }
        list.append(card);
    });
    action.append(list);
    if (round.user_vote) notice.textContent = 'Ваш лайк уже зараховано.';
}

async function poll() {
    try {
        const response = await fetch('/api/roulette/current');
        if (response.ok) render((await response.json()).round);
    } catch (error) {
        console.error(error);
    }
}

connectRoomSocket({
    state(state) {
        if (state.activity_type === 'duel') {
            poll();
            return;
        }
        stopWheelTimers();
        window.location.href = state.activity_type === 'quiz' ? '/quiz' : '/lobby';
    },
    duel() { poll(); },
});
poll();
