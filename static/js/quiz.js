const page = document.body;
const question = JSON.parse(page.dataset.question);
const submitButton = document.getElementById("submitAnswer");
const card = document.getElementById("questionCard");
const answerButtons = [...document.querySelectorAll(".answer-option")];
const layer = document.getElementById("characterLayer");
const rainLayer = document.getElementById("rainLayer");
const reactionToast = document.getElementById("reactionToast");
const soundToggle = document.getElementById("soundToggle");
const comboLabel = document.getElementById("comboLabel");
const progressLabel = document.getElementById("progressLabel");
const rouletteOverlay = document.getElementById("rouletteOverlay");
const rouletteWheel = document.getElementById("rouletteWheel");
const rouletteWheelName = document.getElementById("rouletteWheelName");
const rouletteQuestion = document.getElementById("rouletteQuestion");
const rouletteParticipants = document.getElementById("rouletteParticipants");
const rouletteAction = document.getElementById("rouletteAction");
const rouletteNotice = document.getElementById("rouletteNotice");

const questionNumber = Number(page.dataset.questionNumber);
progressLabel.textContent = `Виконано: ${questionNumber - 1} · Завдання ${questionNumber} / 67`;

const correctMessages = [
    "+1 до IQ",
    "Python approves.",
    "Senior detected.",
    "Підозріло впевнено.",
    "Непогано."
];

const wrongMessages = [
    "Ну майже.",
    "Python це запам'ятав.",
    "Ми це точно проходили...",
    "F.",
    "Спроба була."
];

const correctSounds = [
    "/static/sounds/correct_1.wav",
    "/static/sounds/correct_2.wav",
    "/static/sounds/correct_3.wav"
];

const wrongMusic = [
    "/static/sounds/do-eeeweweewet.mp3",
    "/static/sounds/i-am-in-space-on-the-moon.mp3",
    "/static/sounds/i-bet-on-losing-dogs-low-quality.mp3",
    "/static/sounds/mario-kart-ds-music-lose-race-5th-8th-place-hd.mp3",
    "/static/sounds/my-reaction-that-i-might-lose-my-channel_wGvOByf.mp3",
    "/static/sounds/press-this-button-for-a-surprise-you-losers.mp3",
    "/static/sounds/the-price-is-right-losing-horn.mp3",
    "/static/sounds/Voicy_Brawl%20stars%20OST%20-%20Lose.mp3"
];

const emojis = ["🤔", "👀", "🧐", "😏", "🫣"];
const sides = ["left", "right", "top", "bottom"];

let selected = new Set();
let submitting = false;
let occupiedSides = [];
let characterTimers = [];
let characterHasAppeared = false;
let activeAudio = null;
let awaitingNext = false;
let nextUrl = null;
let displayedRouletteId = null;
let rouletteSpinTimer = null;
let startedAt = performance.now();

let combo = Number(sessionStorage.getItem("quizCombo") || 0);
let soundEnabled = localStorage.getItem("quizSound") !== "off";
updateSoundIcon();
updateCombo();

answerButtons.forEach(button => {
    button.addEventListener("click", () => {
        if (submitting) return;

        const index = Number(button.dataset.index);

        if (question.type === "single" || question.type === "true_false") {
            selected.clear();
            answerButtons.forEach(btn => btn.classList.remove("selected"));
            selected.add(index);
            button.classList.add("selected");
        } else {
            if (selected.has(index)) {
                selected.delete(index);
                button.classList.remove("selected");
            } else {
                selected.add(index);
                button.classList.add("selected");
            }
        }

        submitButton.disabled = selected.size === 0;
        scheduleThinkers();
    });
});

submitButton.addEventListener("click", () => {
    if (awaitingNext) {
        goToNextQuestion();
        return;
    }
    submitAnswer();
});
soundToggle.addEventListener("click", () => {
    soundEnabled = !soundEnabled;
    localStorage.setItem("quizSound", soundEnabled ? "on" : "off");
    if (!soundEnabled) stopActiveSound();
    updateSoundIcon();
});

function updateSoundIcon() {
    soundToggle.textContent = soundEnabled ? "🔊" : "🔇";
}

function updateCombo() {
    comboLabel.textContent = combo >= 2 ? `Combo x${combo}` : "";
}

function randomItem(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
}

function scheduleThinkers() {
    clearCharacterTimers();

    if (selected.size === 0) {
        hideCharacters();
        return;
    }

    if (!characterHasAppeared) {
        characterTimers.push(setTimeout(() => showCharacter(), 300 + Math.random() * 500));
    }
}

const idleTimer = setTimeout(() => {
    if (!submitting) showCharacter("bottom", "🗿", true);
}, 14000);

function clearCharacterTimers() {
    characterTimers.forEach(clearTimeout);
    characterTimers = [];
}

function showCharacter(forcedSide = null, forcedEmoji = null, isIdle = false) {
    if (characterHasAppeared) return;

    const available = sides.filter(side => !occupiedSides.includes(side));
    if (!available.length) return;

    const side = forcedSide && available.includes(forcedSide)
        ? forcedSide
        : randomItem(available);

    occupiedSides.push(side);
    characterHasAppeared = true;

    const el = document.createElement("div");
    el.className = `edge-character ${side}${isIdle ? " idle" : ""}`;
    el.textContent = forcedEmoji || randomItem(emojis);
    layer.appendChild(el);

    requestAnimationFrame(() => el.classList.add("visible"));
}

function hideCharacters() {
    [...layer.children].forEach(el => {
        el.classList.remove("visible");
        setTimeout(() => el.remove(), 250);
    });
    occupiedSides = [];
}

function showWrongCharacter() {
    layer.replaceChildren();
    const el = document.createElement("div");
    el.className = "edge-character wrong-character";
    el.textContent = "😭";
    layer.appendChild(el);
    requestAnimationFrame(() => el.classList.add("visible"));
}

function startRain() {
    const drops = document.createDocumentFragment();
    for (let index = 0; index < 72; index += 1) {
        const drop = document.createElement("span");
        drop.className = "rain-drop";
        drop.style.setProperty("--x", `${Math.random() * 100}%`);
        drop.style.setProperty("--length", `${14 + Math.random() * 24}px`);
        drop.style.setProperty("--duration", `${0.65 + Math.random() * 0.55}s`);
        drop.style.setProperty("--delay", `${-Math.random() * 1.2}s`);
        drops.appendChild(drop);
    }
    rainLayer.replaceChildren(drops);
    rainLayer.classList.add("active");
}

function stopRain() {
    rainLayer.classList.remove("active");
    rainLayer.replaceChildren();
}

function makeRoulettePerson(participant) {
    const item = document.createElement("div");
    item.className = "roulette-person";
    const name = document.createElement("strong");
    name.textContent = participant.name;
    item.appendChild(name);
    return item;
}

function startRouletteSpin(round) {
    clearInterval(rouletteSpinTimer);
    const names = round.candidate_pool.length ? round.candidate_pool : round.participants.map(p => p.name);
    let index = 0;
    rouletteWheel.classList.add("spinning");
    rouletteWheelName.textContent = "Рулетка обирає…";
    rouletteSpinTimer = setInterval(() => {
        rouletteWheelName.textContent = names[index % names.length];
        index += 1;
    }, 130);
    setTimeout(() => {
        clearInterval(rouletteSpinTimer);
        rouletteSpinTimer = null;
        rouletteWheel.classList.remove("spinning");
        rouletteWheelName.textContent = `Обрано: ${round.participants.map(p => p.name).join(" та ")}`;
    }, 1800);
}

function submitRouletteAnswer(form) {
    form.addEventListener("submit", async event => {
        event.preventDefault();
        const answer = form.elements.answer.value.trim();
        if (!answer) return;
        const res = await fetch("/api/roulette/answer", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ answer })
        });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            rouletteNotice.textContent = data.error || "Не вдалося надіслати відповідь.";
            return;
        }
        pollRoulette();
    });
}

function createVoteButton(participant) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary-btn";
    button.textContent = `👍 Лайк (${participant.votes})`;
    button.addEventListener("click", async () => {
        const res = await fetch("/api/roulette/vote", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ choice_student_id: participant.student_id })
        });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            rouletteNotice.textContent = data.error || "Не вдалося поставити лайк.";
            return;
        }
        pollRoulette();
    });
    return button;
}

function renderRoulette(round) {
    if (!round) {
        rouletteOverlay.classList.add("hidden");
        displayedRouletteId = null;
        return;
    }

    rouletteOverlay.classList.remove("hidden");
    const pendingAnswer = rouletteAction.querySelector('textarea[name="answer"]')?.value || "";
    rouletteQuestion.textContent = `Питання викладача: ${round.question}`;
    rouletteParticipants.replaceChildren(...round.participants.map(makeRoulettePerson));
    rouletteAction.replaceChildren();
    rouletteNotice.textContent = "";

    if (displayedRouletteId !== round.id) {
        displayedRouletteId = round.id;
        startRouletteSpin(round);
    } else if (!rouletteSpinTimer) {
        rouletteWheelName.textContent = `Обрано: ${round.participants.map(p => p.name).join(" та ")}`;
    }

    if (round.status === "answering") {
        if (round.can_answer) {
            const form = document.createElement("form");
            form.className = "roulette-form";
            const input = document.createElement("textarea");
            input.name = "answer";
            input.maxLength = 1000;
            input.placeholder = "Напишіть свою відповідь…";
            input.required = true;
            input.value = pendingAnswer;
            const button = document.createElement("button");
            button.className = "primary-btn";
            button.type = "submit";
            button.textContent = "Надіслати відповідь";
            form.append(input, button);
            rouletteAction.appendChild(form);
            submitRouletteAnswer(form);
        } else {
            rouletteNotice.textContent = "Обрані учні готують відповіді. Зачекайте на голосування.";
        }
        return;
    }

    const answers = document.createElement("div");
    answers.className = "roulette-answer-list";
    round.participants.forEach(participant => {
        const card = document.createElement("article");
        card.className = "roulette-answer";
        const title = document.createElement("strong");
        title.textContent = participant.name;
        const text = document.createElement("p");
        text.textContent = participant.answer_text;
        card.append(title, text);
        if (round.can_vote) card.appendChild(createVoteButton(participant));
        else {
            const votes = document.createElement("span");
            votes.textContent = `👍 ${participant.votes}`;
            card.appendChild(votes);
        }
        answers.appendChild(card);
    });
    rouletteAction.appendChild(answers);
    if (round.user_vote) rouletteNotice.textContent = "Ваш лайк уже зараховано.";
    if (!round.can_vote && !round.user_vote) rouletteNotice.textContent = "Учасники раунду не голосують за власні відповіді.";
    if (round.status === "voting") rouletteNotice.textContent += " Викладач завершить раунд після голосування.";
}

async function pollRoulette() {
    try {
        const res = await fetch("/api/roulette/current");
        if (!res.ok) return;
        const data = await res.json();
        renderRoulette(data.round);
    } catch (error) {
        console.error(error);
    }
}

function playSound(paths, volume = 0.65, loop = false) {
    if (!soundEnabled) return;
    stopActiveSound();

    const audio = new Audio(randomItem(paths));
    audio.volume = volume;
    audio.loop = loop;
    if (loop) activeAudio = audio;
    audio.play().catch(() => {});
}

function stopActiveSound() {
    if (!activeAudio) return;
    activeAudio.pause();
    activeAudio.currentTime = 0;
    activeAudio = null;
}

function showNextQuestionButton(finished) {
    awaitingNext = true;
    nextUrl = finished ? "/result" : "/quiz";
    submitButton.textContent = finished ? "Перейти до результату" : "Наступне питання";
    submitButton.disabled = false;
    submitButton.focus();
}

function goToNextQuestion() {
    if (!awaitingNext || !nextUrl) return;

    awaitingNext = false;
    submitButton.disabled = true;
    stopActiveSound();
    stopRain();
    card.classList.add("leaving");
    setTimeout(() => {
        window.location.href = nextUrl;
    }, 340);
}

function showReaction(message) {
    reactionToast.textContent = message;
    reactionToast.classList.add("show");
}

async function submitAnswer() {
    if (submitting || selected.size === 0) return;

    submitting = true;
    submitButton.disabled = true;
    answerButtons.forEach(btn => btn.disabled = true);
    clearCharacterTimers();
    clearTimeout(idleTimer);
    hideCharacters();

    const responseTime = (performance.now() - startedAt) / 1000;

    try {
        const res = await fetch("/api/answer", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question_id: question.id,
                selected_answers: [...selected],
                response_time: responseTime
            })
        });

        const data = await res.json();

        if (!res.ok) {
            showReaction(data.error || "Помилка збереження.");
            submitting = false;
            answerButtons.forEach(btn => btn.disabled = false);
            submitButton.disabled = false;
            return;
        }

        if (data.is_correct) {
            combo += 1;
            sessionStorage.setItem("quizCombo", String(combo));
            card.classList.add("correct");
            markCorrectAnswers(data.correct_answers);
            playSound(correctSounds);

            let message = randomItem(correctMessages);
            if (responseTime < 2) message = "Ти хоч питання прочитав?";
            if (combo === 3) message = "Combo x3";
            if (combo >= 5) message = `Combo x${combo} 🔥`;
            showReaction(message);
        } else {
            combo = 0;
            sessionStorage.setItem("quizCombo", "0");
            card.classList.add("wrong");
            markWrongAndCorrect(data.correct_answers);
            showWrongCharacter();
            startRain();
            playSound(wrongMusic, 0.1, true);
            showReaction(randomItem(wrongMessages));
        }

        updateCombo();

        if (!data.is_correct) {
            showNextQuestionButton(data.finished);
            return;
        }

        setTimeout(() => {
            card.classList.add("leaving");
            setTimeout(() => {
                window.location.href = data.finished ? "/result" : "/quiz";
            }, 340);
        }, 1050);

    } catch (error) {
        console.error(error);
        showReaction("Не вдалося зв'язатися з сервером.");
        submitting = false;
        answerButtons.forEach(btn => btn.disabled = false);
        submitButton.disabled = false;
    }
}

function markCorrectAnswers(correctIndexes) {
    answerButtons.forEach(btn => {
        if (correctIndexes.includes(Number(btn.dataset.index))) {
            btn.classList.add("answer-correct");
        }
    });
}

function markWrongAndCorrect(correctIndexes) {
    answerButtons.forEach(btn => {
        const index = Number(btn.dataset.index);
        if (selected.has(index) && !correctIndexes.includes(index)) {
            btn.classList.add("answer-wrong");
        }
        if (correctIndexes.includes(index)) {
            btn.classList.add("answer-correct");
        }
    });
}

pollRoulette();
setInterval(pollRoulette, 3000);
