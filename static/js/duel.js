const wheel = document.getElementById('duelWheel');
const wheelName = document.getElementById('duelWheelName');
const question = document.getElementById('duelQuestion');
const participants = document.getElementById('duelParticipants');
const action = document.getElementById('duelAction');
const notice = document.getElementById('duelNotice');
let displayedRound = null;
let spinningTimer = null;

function spin(round) {
    clearInterval(spinningTimer);
    const names = round.candidate_pool.length ? round.candidate_pool : round.participants.map(item => item.name);
    let index = 0;
    wheel.classList.add('spinning');
    spinningTimer = setInterval(() => { wheelName.textContent = names[index++ % names.length]; }, 130);
    setTimeout(() => {
        clearInterval(spinningTimer);
        wheel.classList.remove('spinning');
        wheelName.textContent = `Обрано: ${round.participants.map(item => item.name).join(' та ')}`;
    }, 1800);
}

async function send(url, payload) {
    const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'Не вдалося виконати дію.');
    return data;
}

function render(round) {
    if (!round) { window.location.href = '/lobby'; return; }
    question.textContent = `Питання кімнати: ${round.question}`;
    participants.replaceChildren(...round.participants.map(item => {
        const card = document.createElement('article');
        card.className = 'roulette-person';
        card.innerHTML = `<strong></strong>`;
        card.querySelector('strong').textContent = item.name;
        return card;
    }));
    action.replaceChildren();
    notice.textContent = '';
    if (displayedRound !== round.id) { displayedRound = round.id; spin(round); }
    if (round.status === 'answering') {
        if (!round.can_answer) { notice.textContent = 'Обрані учасники готують відповіді.'; return; }
        const form = document.createElement('form');
        form.className = 'roulette-form';
        form.innerHTML = '<textarea name="answer" maxlength="1000" required placeholder="Напишіть свою відповідь…"></textarea><button class="primary-btn" type="submit">Надіслати відповідь</button>';
        form.addEventListener('submit', async event => {
            event.preventDefault();
            try { await send('/api/roulette/answer', {answer: form.elements.answer.value.trim()}); poll(); }
            catch (error) { showToast(error.message, {type:'error'}); }
        });
        action.append(form);
        return;
    }
    const list = document.createElement('div');
    list.className = 'roulette-answer-list';
    round.participants.forEach(item => {
        const card = document.createElement('article');
        card.className = 'roulette-answer';
        const title = document.createElement('strong'); title.textContent = item.name;
        const text = document.createElement('p'); text.textContent = item.answer_text || 'Готує відповідь…';
        card.append(title, text);
        if (round.can_vote) {
            const button = document.createElement('button');
            button.className = 'secondary-btn'; button.type = 'button'; button.textContent = `👍 Лайк (${item.votes})`;
            button.onclick = async () => { try { await send('/api/roulette/vote', {choice_student_id:item.student_id}); poll(); } catch (error) { showToast(error.message, {type:'error'}); } };
            card.append(button);
        } else { const votes = document.createElement('span'); votes.textContent = `👍 ${item.votes}`; card.append(votes); }
        list.append(card);
    });
    action.append(list);
    if (round.user_vote) notice.textContent = 'Ваш лайк уже зараховано.';
}

async function poll() {
    try { const response = await fetch('/api/roulette/current'); if (response.ok) render((await response.json()).round); }
    catch (error) { console.error(error); }
}

connectRoomSocket({
    state(state) {
        if (state.activity_type === 'duel') {
            poll();
            return;
        }
        window.location.href = state.activity_type === 'quiz' ? '/quiz' : '/lobby';
    },
    duel() { poll(); },
});
