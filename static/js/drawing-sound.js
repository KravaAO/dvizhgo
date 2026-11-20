// Countdown cues for the end of a drawing round. The tones are synthesised
// with Web Audio, so there is nothing to download. The on/off choice is shared
// with the quiz page through the same localStorage key.
(() => {
    const PREF_KEY = 'quizSound';
    // A cue that the browser only lets through later (after a tap) is stale.
    const MAX_DELAY_MS = 300;

    function readPref() {
        try { return localStorage.getItem(PREF_KEY) !== 'off'; } catch { return true; }
    }
    function writePref(on) {
        try { localStorage.setItem(PREF_KEY, on ? 'on' : 'off'); } catch { /* private mode */ }
    }

    window.createCountdownSound = function createCountdownSound(toggle) {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        let enabled = readPref();
        let ctx = null;

        function context() {
            if (!ctx && AudioCtx) {
                try { ctx = new AudioCtx(); } catch { ctx = null; }
            }
            return ctx;
        }
        // Browsers start audio only from a user gesture; drawing provides one.
        function unlock() {
            if (!enabled) return;
            const audio = context();
            if (audio && audio.state === 'suspended') audio.resume().catch(() => {});
        }
        ['pointerdown', 'pointerup', 'touchend', 'keydown'].forEach(type => {
            document.addEventListener(type, unlock, {capture:true, passive:true});
        });

        function tone(freq, at, length, {type = 'sine', volume = .2, slideTo = null} = {}) {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            const start = ctx.currentTime + at;
            osc.type = type;
            osc.frequency.setValueAtTime(freq, start);
            if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, start + length);
            gain.gain.setValueAtTime(.0001, start);
            gain.gain.exponentialRampToValueAtTime(volume, start + .012);
            gain.gain.exponentialRampToValueAtTime(.0001, start + length);
            osc.connect(gain).connect(ctx.destination);
            osc.start(start);
            osc.stop(start + length + .05);
        }

        const CUES = {
            // Ten seconds left: a bright rising chime.
            warning() {
                tone(659, 0, .18, {type:'triangle', volume:.28});
                tone(880, .16, .18, {type:'triangle', volume:.28});
                tone(1319, .32, .32, {type:'triangle', volume:.24});
            },
            // The last seconds: a short clock tick, the final one higher.
            tick() { tone(1046, 0, .08, {type:'square', volume:.07}); },
            lastTick() { tone(1568, 0, .12, {type:'square', volume:.09}); },
            // Time is up: a falling game-show buzzer.
            end() {
                tone(392, 0, .6, {type:'sawtooth', volume:.12, slideTo:131});
                tone(196, 0, .6, {type:'square', volume:.06, slideTo:65});
            },
        };

        function play(cue) {
            if (!enabled) return;
            const audio = context();
            if (!audio) return;
            if (audio.state === 'running') { CUES[cue](); return; }
            const asked = performance.now();
            audio.resume()
                .then(() => { if (audio.state === 'running' && performance.now() - asked < MAX_DELAY_MS) CUES[cue](); })
                .catch(() => {});
        }

        function render() {
            toggle.textContent = enabled ? '🔊' : '🔇';
            toggle.setAttribute('aria-pressed', String(enabled));
            toggle.title = enabled ? 'Вимкнути звук' : 'Увімкнути звук';
        }
        toggle.addEventListener('click', () => {
            enabled = !enabled;
            writePref(enabled);
            if (enabled) unlock();
            render();
        });
        render();
        return {play};
    };
})();
