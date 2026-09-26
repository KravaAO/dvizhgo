(() => {
    function enhanceSelect(select) {
        if (select.dataset.enhanced) return;
        select.dataset.enhanced = 'true';
        const wrapper = document.createElement('div'); wrapper.className = 'custom-select';
        const button = document.createElement('button'); button.type = 'button'; button.className = 'custom-select-trigger'; button.setAttribute('aria-haspopup', 'listbox'); button.setAttribute('aria-expanded', 'false');
        const list = document.createElement('div'); list.className = 'custom-select-list hidden'; list.setAttribute('role', 'listbox');
        const close = () => { list.classList.add('hidden'); button.setAttribute('aria-expanded', 'false'); };
        const open = () => { list.classList.remove('hidden'); button.setAttribute('aria-expanded', 'true'); };
        const render = () => { button.textContent = select.options[select.selectedIndex]?.text || ''; list.replaceChildren(...[...select.options].map(option => { const item = document.createElement('button'); item.type = 'button'; item.className = 'custom-select-option'; item.textContent = option.text; item.setAttribute('role', 'option'); item.setAttribute('aria-selected', String(option.selected)); item.disabled = option.disabled; item.addEventListener('click', () => { select.value = option.value; select.dispatchEvent(new Event('change', {bubbles: true})); render(); close(); button.focus(); }); return item; })); };
        button.addEventListener('click', () => list.classList.contains('hidden') ? open() : close());
        button.addEventListener('keydown', event => { if (event.key === 'Escape') close(); if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); list.querySelector('[aria-selected="true"]')?.focus(); } });
        list.addEventListener('keydown', event => { const items = [...list.querySelectorAll('.custom-select-option:not(:disabled)')]; const current = items.indexOf(document.activeElement); if (event.key === 'Escape') { close(); button.focus(); } if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); items[(current + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus(); } });
        document.addEventListener('click', event => { if (!wrapper.contains(event.target)) close(); }); select.addEventListener('change', render); select.classList.add('native-select-hidden'); select.parentNode.insertBefore(wrapper, select); wrapper.append(button, list, select); render();
    }
    document.addEventListener('DOMContentLoaded', () => document.querySelectorAll('select[data-custom-select]').forEach(enhanceSelect));
})();
