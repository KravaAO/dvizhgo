(() => {
    function openLeaveModal(form) {
        let modal = document.getElementById('leaveRoomModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'leaveRoomModal';
            modal.className = 'leave-modal-backdrop';
            modal.innerHTML = '<section class="leave-modal" role="dialog" aria-modal="true" aria-labelledby="leaveModalTitle"><div class="dv-micro">ПІДТВЕРДЖЕННЯ</div><h2 id="leaveModalTitle">Вийти з кімнати?</h2><p>Ваш поточний прогрес залишиться в результатах кімнати.</p><div><button type="button" class="leave-cancel">Залишитись</button><button type="button" class="leave-confirm">Вийти</button></div></section>';
            document.body.appendChild(modal);
        }
        modal.classList.add('open');
        modal.querySelector('.leave-cancel').focus();
        const close = () => modal.classList.remove('open');
        modal.querySelector('.leave-cancel').onclick = close;
        modal.querySelector('.leave-confirm').onclick = () => { modal.remove(); form.submit(); };
        modal.onclick = event => { if (event.target === modal) close(); };
    }
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('form[data-confirm-leave]').forEach(form => form.addEventListener('submit', event => { event.preventDefault(); openLeaveModal(form); }));
    });
})();
