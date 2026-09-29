(() => {
    let activeIntro = null;

    function element(tag, className, text = '') {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text) node.textContent = text;
        return node;
    }

    function pulseFlash(root) {
        root.classList.remove('flash-now');
        void root.offsetWidth;
        root.classList.add('flash-now');
        window.setTimeout(() => root.classList.remove('flash-now'), 240);
    }

    function buildFrame(stage, type) {
        const header = element('header', 'extra-cinema-head');
        header.append(
            element('div', 'extra-cinema-badge', type === 'duel' ? 'EXTRA / DUEL' : 'EXTRA / FLASH QUESTION'),
            element('div', 'extra-cinema-mode', type === 'duel'
                ? 'КВІЗ ПРИЗУПИНЕНО · LIVE TAKEOVER'
                : 'ШВИДКЕ ПИТАННЯ · ВІДПОВІДАЮТЬ УСІ'),
        );
        stage.appendChild(header);
    }

    function buildDuel(stage, names) {
        const main = element('main', 'extra-cinema-duel-main');
        main.append(
            element('div', 'extra-cinema-duel-title', 'DUEL START'),
            element('i', 'extra-cinema-speedline line-1'),
            element('i', 'extra-cinema-speedline line-2'),
            element('i', 'extra-cinema-speedline line-3'),
            element('div', 'extra-cinema-impact'),
        );

        const resolvedNames = [names[0] || '?', names[1] || '?'];
        resolvedNames.forEach((name, index) => {
            const side = element('section', `extra-cinema-duel-side ${index === 0 ? 'left' : 'right'}`);
            const player = element('div', 'extra-cinema-player');
            player.append(
                element('div', 'extra-cinema-avatar', String(name).trim().slice(0, 1).toUpperCase() || '?'),
                element('h2', '', name),
                element('p', '', `УЧАСНИК 0${index + 1}`),
            );
            side.appendChild(player);
            if (index === 0) {
                const versus = element('div', 'extra-cinema-versus');
                versus.appendChild(element('div', 'extra-cinema-vs', 'VS'));
                main.append(side, versus);
            } else {
                main.appendChild(side);
            }
        });
        stage.appendChild(main);
    }

    function buildFooter(stage, type, durationSeconds) {
        const footer = element('footer', 'extra-cinema-foot');
        footer.append(
            element('span', '', type === 'duel'
                ? 'КВІЗ ПРИЗУПИНЕНО · ГОТУЄМО ДВОХ УЧАСНИКІВ'
                : `КВІЗ ПРИЗУПИНЕНО · ${durationSeconds} СЕКУНД НА ВІДПОВІДЬ`),
            element('strong', '', 'LIVE'),
        );
        stage.appendChild(footer);
    }

    function playFlashTransition() {
        const answerStage = document.querySelector('.flash-question-stage');
        if (!answerStage) return Promise.resolve();

        const root = element('section', 'extra-intro extra-cinema extra-cinema-flash-transition');
        root.setAttribute('aria-hidden', 'true');
        const shutters = element('div', 'extra-cinema-shutters');
        for (let index = 0; index < 6; index += 1) shutters.appendChild(document.createElement('i'));
        const screenFlash = element('div', 'extra-cinema-screen-flash');
        root.append(shutters, screenFlash);
        document.body.appendChild(root);
        answerStage.classList.add('flash-cinema-entering');

        const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
        activeIntro = new Promise(resolve => {
            requestAnimationFrame(() => root.classList.add('phase-in'));
            window.setTimeout(() => {
                root.classList.add('reveal-content');
                answerStage.classList.add('flash-cinema-ready');
                pulseFlash(root);
            }, reducedMotion ? 20 : 550);

            window.setTimeout(() => {
                answerStage.classList.remove('flash-cinema-entering', 'flash-cinema-ready');
                root.remove();
                activeIntro = null;
                resolve();
            }, reducedMotion ? 120 : 1600);
        });
        return activeIntro;
    }

    window.playExtraIntro = ({type, names = [], question = '', answers = [], durationSeconds = 20}) => {
        if (activeIntro) return activeIntro;
        if (type !== 'duel') return playFlashTransition();
        const variant = type === 'duel' ? 'duel' : 'flash_question';
        const root = element('section', `extra-intro extra-cinema extra-cinema-${variant}`);
        root.setAttribute('aria-hidden', 'true');

        const shutters = element('div', 'extra-cinema-shutters');
        for (let index = 0; index < 6; index += 1) shutters.appendChild(document.createElement('i'));
        const screenFlash = element('div', 'extra-cinema-screen-flash');
        const stage = element('section', `extra-cinema-stage ${variant === 'duel' ? 'duel-stage' : 'flash-stage'}`);
        buildFrame(stage, variant);
        buildDuel(stage, names);
        buildFooter(stage, variant, durationSeconds);
        root.append(shutters, screenFlash, stage);
        document.body.appendChild(root);

        const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
        activeIntro = new Promise(resolve => {
            requestAnimationFrame(() => root.classList.add('phase-in'));
            window.setTimeout(() => {
                root.classList.add('show-stage');
                pulseFlash(root);
                requestAnimationFrame(() => root.classList.add(variant === 'duel' ? 'duel-ready' : 'flash-ready'));
            }, reducedMotion ? 20 : 330);

            if (variant === 'duel' && !reducedMotion) {
                window.setTimeout(() => {
                    root.classList.add('impact-shake');
                    pulseFlash(root);
                    window.setTimeout(() => root.classList.remove('impact-shake'), 260);
                }, 790);
            }

            const outroAt = reducedMotion ? 420 : 1700;
            window.setTimeout(() => root.classList.add('phase-out'), outroAt);
            window.setTimeout(() => {
                root.remove();
                activeIntro = null;
                resolve();
            }, outroAt + (reducedMotion ? 30 : 260));
        });
        return activeIntro;
    };
})();
