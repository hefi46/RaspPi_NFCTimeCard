// Phase 5 will fill this in
document.getElementById('logout-btn')?.addEventListener('click', async () => {
  await fetch('/auth/logout', { method: 'POST' });
  window.location.href = '/login';
});
