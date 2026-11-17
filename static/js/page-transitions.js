(() => {
    const transitionKey = 'dv-page-transition-pending';
    const transitionDuration = 270;
    const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const root = document.documentElement;

    function enterPage() {
        if (motionPreference.matches) return;
        root.classList.add('dv-page-entering');
        window.setTimeout(() => root.classList.remove('dv-page-entering'), transitionDuration + 40);
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
    function navigateTo(destination, duration = transitionDuration) {
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
        if (navigating) return;

        navigating = true;
        sessionStorage.setItem(transitionKey, '1');
        root.classList.add('dv-page-leaving');
        window.setTimeout(() => window.location.assign(target.href), duration);
    }

    window.dvNavigate = navigateTo;

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
})();
