(() => {
    const transitionKey = 'dv-page-transition-pending';
    const leaveDuration = 150;
    const enterDuration = 230;
    const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const root = document.documentElement;

    function enterPage() {
        if (motionPreference.matches) return;
        root.classList.add('dv-page-entering');
        window.setTimeout(() => root.classList.remove('dv-page-entering'), enterDuration + 40);
    }

    if (sessionStorage.getItem(transitionKey)) {
        sessionStorage.removeItem(transitionKey);
        enterPage();
    }

    window.addEventListener('pageshow', event => {
        if (!event.persisted) return;
        sessionStorage.removeItem(transitionKey);
        root.classList.remove('dv-page-leaving');
        enterPage();
    });

    let navigating = false;
    function transitionBeforeNavigation(continueNavigation) {
        if (motionPreference.matches) {
            continueNavigation();
            return true;
        }
        if (navigating) return false;

        navigating = true;
        sessionStorage.setItem(transitionKey, '1');
        root.classList.add('dv-page-leaving');
        window.setTimeout(continueNavigation, leaveDuration);
        return true;
    }

    function navigateTo(destination) {
        const target = new URL(destination, window.location.href);
        if (
            target.origin !== window.location.origin
            || !/^https?:$/.test(target.protocol)
            || (target.pathname === window.location.pathname && target.search === window.location.search)
            || motionPreference.matches
        ) {
            window.location.assign(target.href);
            return;
        }
        transitionBeforeNavigation(() => window.location.assign(target.href));
    }

    function submitForm(form) {
        const destination = new URL(form.action, window.location.href);
        const target = form.getAttribute('target');
        const submit = () => HTMLFormElement.prototype.submit.call(form);
        if (
            destination.origin !== window.location.origin
            || !/^https?:$/.test(destination.protocol)
            || (target && target.toLowerCase() !== '_self')
            || form.method.toLowerCase() === 'dialog'
            || motionPreference.matches
            || navigating
        ) {
            submit();
            return;
        }
        transitionBeforeNavigation(submit);
    }

    window.dvNavigate = navigateTo;
    window.dvSubmitForm = submitForm;

    document.addEventListener('click', event => {
        if (
            motionPreference.matches
            || event.defaultPrevented
            || event.button !== 0
            || event.detail === 0
            || event.metaKey
            || event.ctrlKey
            || event.shiftKey
            || event.altKey
        ) return;
        const link = event.target instanceof Element ? event.target.closest('a[href]') : null;
        if (!link || link.hasAttribute('download') || link.relList.contains('external')) return;
        if (link.target && link.target.toLowerCase() !== '_self') return;

        const destination = new URL(link.href, window.location.href);
        if (destination.origin !== window.location.origin || !/^https?:$/.test(destination.protocol)) return;
        if (destination.pathname === window.location.pathname && destination.search === window.location.search) return;
        event.preventDefault();
        navigateTo(destination.href);
    });

    document.addEventListener('submit', event => {
        const form = event.target;
        if (
            event.defaultPrevented
            || !(form instanceof HTMLFormElement)
            || (form.target && form.target.toLowerCase() !== '_self')
            || form.method.toLowerCase() === 'dialog'
        ) return;
        const destination = new URL(form.action, window.location.href);
        if (destination.origin !== window.location.origin || !/^https?:$/.test(destination.protocol)) return;
        event.preventDefault();
        submitForm(form);
    });
})();
