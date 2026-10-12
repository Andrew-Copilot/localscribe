(() => {
  const previewButton = document.getElementById('preview-diagnostics');
  const saveButton = document.getElementById('save-diagnostics');
  const preview = document.getElementById('diagnostics-preview');
  let report = null;

  previewButton.addEventListener('click', async () => {
    previewButton.disabled = true;
    try {
      report = await LS.get('/api/diagnostics');
      preview.textContent = JSON.stringify(report, null, 2);
      preview.hidden = false;
      saveButton.disabled = false;
    } catch (err) {
      report = null;
      saveButton.disabled = true;
      LS.toast(`Could not prepare diagnostics: ${err.message}`, 'error');
    } finally {
      previewButton.disabled = false;
    }
  });

  saveButton.addEventListener('click', () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'localscribe-diagnostics.json';
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
})();
