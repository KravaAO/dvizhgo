const flashQuestionText = document.getElementById('flashQuestionText');
const flashQuestionOptions = document.getElementById('flashQuestionOptions');
const flashQuestionNotice = document.getElementById('flashQuestionNotice');
const flashQuestionTimer = document.getElementById('flashQuestionTimer');
const flashQuestionCount = document.getElementById('flashQuestionCount');
const flashQuestionLabel = document.getElementById('flashQuestionLabel');
let currentFlash = null;
let introPlayed = false;
let flashClockOffset = 0;
let flashCloseRequested = false;

function formatFlashTime(totalSeconds) {
    const seconds = Math.max(0, Math.ceil(totalSeconds || 0));
    return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

function secondsUntilFlashEnds() {
    if (!currentFlash?.ends_at) return 0;
    return Math.max(0, (Date.parse(currentFlash.ends_at) - (Date.now() + flashClockOffset)) / 1000);
}

function secondsUntilFlashStarts() {
    if (!currentFlash?.starts_at) return 0;
    return Math.max(0, (Date.parse(currentFlash.starts_at) - (Date.now() + flashClockOffset)) / 1000);
}

function secondsUntilFlashCloses() {
    if (!currentFlash?.closes_at) return 0;
    return Math.max(0, (Date.parse(currentFlash.closes_at) - (Date.now() + flashClockOffset)) / 1000);
}

function updateFlashTimer() {
    if (!currentFlash?.ends_at) return;
    const waitingForStart = secondsUntilFlashStarts() > 0;
    const answerSeconds = waitingForStart ? currentFlash.duration_seconds : secondsUntilFlashEnds();
    const timedOut = answerSeconds <= 0 || currentFlash.deadline_reached;
    if (timedOut) {
        const closeSeconds = secondsUntilFlashCloses();
        flashQuestionTimer.textContent = formatFlashTime(closeSeconds);
        flashQuestionOptions.querySelectorAll('button').forEach(button => { button.disabled = true; });
        const completionText = currentFlash.completion_reason === 'all_answered'
            ? 'Усі відповіли.'
            : 'Час завершився.';
        flashQuestionNotice.textContent = closeSeconds > 0
            ? `${completionText} Повернення до квіза через ${Math.ceil(closeSeconds)}…`
            : 'Повертаємося до квіза…';
        if (closeSeconds <= 0 && !flashCloseRequested) {
            flashCloseRequested = true;
            pollFlash().catch(() => { flashCloseRequested = false; });
        }
        return;
    }

    flashQuestionTimer.textContent = formatFlashTime(answerSeconds);
    if (!currentFlash.answered && !currentFlash.deadline_reached) {
        flashQuestionOptions.querySelectorAll('button').forEach(button => { button.disabled = waitingForStart; });
        flashQuestionNotice.textContent = waitingForStart
            ? 'Готуйся — відповідь відкриється після анімації.'
            : 'Обери один варіант до завершення таймера.';
    }
}

function renderFlash(flash, nextActivityType = null) {
    if (!flash) {
        window.location.href = nextActivityType === 'quiz' ? '/quiz' : '/lobby';
        return;
    }
    currentFlash = flash;
    const parsedServerTime = Date.parse(flash.server_time);
    if (Number.isFinite(parsedServerTime)) flashClockOffset = parsedServerTime - Date.now();
    flashQuestionText.textContent = flash.question;
    flashQuestionLabel.textContent = `${flash.duration_seconds} СЕКУНД · ВІДПОВІДАЮТЬ УСІ`;
    flashQuestionCount.textContent = flash.target_count
        ? `${flash.target_answer_count}/${flash.target_count} відповіли`
        : `${flash.answer_count} відповід${flash.answer_count === 1 ? 'ь' : 'ей'}`;
    const timedOut = flash.deadline_reached || secondsUntilFlashEnds() <= 0;
    const waitingForStart = secondsUntilFlashStarts() > 0;
    flashQuestionOptions.replaceChildren(...flash.answers.map((answer, index) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'flash-question-option';
        button.innerHTML = `<span>${String.fromCharCode(65 + index)}</span><strong></strong>`;
        button.querySelector('strong').textContent = answer;
        const selected = flash.selected_index === index;
        const reveal = Number.isInteger(flash.correct_index);
        if (selected) button.classList.add('selected');
        if (reveal && index === flash.correct_index) button.classList.add('correct');
        if (reveal && selected && index !== flash.correct_index) button.classList.add('wrong');
        button.disabled = flash.answered || timedOut || waitingForStart;
        button.onclick = () => submitFlashAnswer(index);
        return button;
    }));
    if (flash.answered) flashQuestionNotice.textContent = 'Відповідь зараховано.';
    else if (timedOut) flashQuestionNotice.textContent = 'Час завершився. Чекаємо, поки творець кімнати продовжить квіз.';
    else flashQuestionNotice.textContent = 'Обери один варіант до завершення таймера.';
    if (!introPlayed) {
        introPlayed = true;
        window.playExtraIntro({
            type: 'flash_question',
            question: flash.question,
            answers: flash.answers,
            durationSeconds: flash.duration_seconds,
        });
    }
    updateFlashTimer();
}

async function submitFlashAnswer(selected_index) {
    try {
        const response = await fetch('/api/flash-question/answer', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({selected_index})});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Не вдалося зберегти відповідь.');
        renderFlash(data.flash_question);
    } catch (error) { showToast(error.message, {type: 'error'}); }
}

async function pollFlash() {
    const response = await fetch('/api/flash-question/current');
    if (!response.ok) throw new Error('Не вдалося оновити Flash Question.');
    const data = await response.json();
    renderFlash(data.flash_question, data.activity_type);
}

window.setInterval(updateFlashTimer, 250);

connectRoomSocket({
    state(state) { if (state.activity_type !== 'flash_question') window.location.href = state.activity_type === 'quiz' ? '/quiz' : '/lobby'; },
    presence() { pollFlash().catch(() => {}); },
    flash_question_updated() { pollFlash(); },
});
pollFlash();
