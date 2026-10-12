/* Project list page: create, import. */

(() => {
  const form = document.getElementById('new-project');
  const openButtons = ['new-project-btn', 'empty-new']
    .map((id) => document.getElementById(id))
    .filter(Boolean);

  function show(open) {
    if (!form) return;
    form.hidden = !open;
    if (open) {
      const title = document.getElementById('np-title');
      if (title) title.focus();
    }
  }

  openButtons.forEach((button) => button.addEventListener('click', () => show(true)));
  const cancel = document.getElementById('np-cancel');
  if (cancel) cancel.addEventListener('click', () => show(false));

  if (form) {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = new FormData(form);
      const title = (data.get('title') || '').toString().trim();
      if (!title) {
        LS.toast('A project needs a title.', 'warn');
        return;
      }
      const submit = form.querySelector('button[type=submit]');
      submit.disabled = true;
      try {
        const result = await LS.post('/api/projects', {
          title,
          principal_investigator: (data.get('principal_investigator') || '').toString(),
          irb_protocol: (data.get('irb_protocol') || '').toString(),
          description: (data.get('description') || '').toString(),
          data_sensitivity: data.get('data_sensitivity').toString(),
        });
        location.href = `/project/${result.project.slug}`;
      } catch (err) {
        LS.toast(`Could not create the project: ${err.message}`, 'error');
        submit.disabled = false;
      }
    });
  }

  /* --------------------------------------------------------------- import */

  const importBtn = document.getElementById('import-btn');
  const importInput = document.getElementById('import-input');

  if (importBtn && importInput) {
    importBtn.addEventListener('click', () => importInput.click());

    importInput.addEventListener('change', async () => {
      const file = importInput.files && importInput.files[0];
      if (!file) return;

      importBtn.disabled = true;
      importBtn.textContent = 'Importing...';
      if (window.LSConsole) LSConsole.open();

      try {
        let result = await sendImport(file, 'prompt');
        let mode = 'rename';
        let snapshotBefore = false;
        if (result.conflict) {
          const choice = prompt(
            `A project named "${result.existing_title}" already exists. ` +
            `Type RENAME to keep both, REPLACE to overwrite it, or ABORT to cancel.`,
            'RENAME'
          );
          if (choice === null || choice.trim().toUpperCase() === 'ABORT') {
            LS.toast('Restore cancelled.', 'info');
            return;
          }
          mode = choice.trim().toLowerCase();
          if (!['rename', 'replace'].includes(mode)) {
            LS.toast('Type RENAME, REPLACE, or ABORT.', 'warn');
            return;
          }
          if (mode === 'replace') {
            const replaceChoice = prompt(
              'Replacing deletes the existing project. Type BACKUP to save an unencrypted ' +
              'local snapshot first, REPLACE to proceed without a snapshot, or Cancel to abort.',
              'BACKUP'
            );
            if (replaceChoice === null) {
              LS.toast('Restore cancelled.', 'info');
              return;
            }
            const backupAction = replaceChoice.trim().toUpperCase();
            if (!['BACKUP', 'REPLACE'].includes(backupAction)) {
              LS.toast('Type BACKUP or REPLACE.', 'warn');
              return;
            }
            snapshotBefore = backupAction === 'BACKUP';
          }
          result = await sendImport(file, mode, snapshotBefore);
        }
        LS.toast(`Imported "${result.project.title}".`, 'ok');
        location.href = `/project/${result.project.slug}`;
      } catch (err) {
        LS.toast(`Import failed: ${err.message}`, 'error', 10000);
        importBtn.disabled = false;
        importBtn.textContent = 'Import project';
        importInput.value = '';
      }
    });
  }

  async function sendImport(file, mode, snapshotBefore = false) {
    const body = new FormData();
    body.append('file', file);
    body.append('mode', mode);
    body.append('snapshot_before', String(snapshotBefore));
    return LS.request('POST', '/api/projects/import', body);
  }
})();
