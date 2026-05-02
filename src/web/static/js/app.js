// ── Topbar clock ────────────────────────────────────────────────────────
(function tickClock() {
  const el = document.getElementById('topbar-clock');
  if (!el) return;
  function fmt(d) {
    const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const hh = String(d.getHours()).padStart(2,'0');
    const mm = String(d.getMinutes()).padStart(2,'0');
    return `${days[d.getDay()]} · ${months[d.getMonth()]} ${d.getDate()} · ${hh}:${mm}`;
  }
  const update = () => { el.textContent = fmt(new Date()); };
  update();
  setInterval(update, 30_000);
})();

// ── Logout ──────────────────────────────────────────────────────────────
document.getElementById('logout-btn')?.addEventListener('click', async () => {
  await fetch('/auth/logout', { method: 'POST' });
  window.location.href = '/login';
});
