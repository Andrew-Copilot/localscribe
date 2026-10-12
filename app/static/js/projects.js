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

      const body = new FormData();
      body.append('file', file);
      const replace = confirm(
        'If a project with this archive’s name already exists, replace it?\n\n' +
        'Choose Cancel to keep both projects by importing a renamed copy.'
      );
      const mode = replace ? 'replace' : 'rename';
      let snapshotBeforeReplace = null;
      if (replace) {
        snapshotBeforeReplace = confirm(
          'Create a local recovery snapshot before replacing an existing project?\n\n' +
          'Choose Cancel to skip the snapshot.'
        ) ? 'yes' : 'no';
        if (snapshotBeforeReplace === 'no' && !confirm(
          'Replace an existing project without a recovery snapshot?'
        )) {
          importInput.value = '';
          return;
        }
      }
      body.append('mode', mode);
      if (snapshotBeforeReplace) {
        body.append('snapshot_before_replace', snapshotBeforeReplace);
      }

      importBtn.disabled = true;
      importBtn.textContent = 'Importing...';
      if (window.LSConsole) LSConsole.open();

      try {
        const result = await LS.request('POST', '/api/projects/import', body);
        if (result.project.archive_integrity_verified) {
          LS.toast(`Imported "${result.project.title}".`, 'ok');
        } else {
          window.alert(
            `Imported "${result.project.title}", but this legacy archive could not be checksum-verified.`
          );
        }
        location.href = `/project/${result.project.slug}`;
      } catch (err) {
        LS.toast(`Import failed: ${err.message}`, 'error', 10000);
        importBtn.disabled = false;
        importBtn.textContent = 'Import project';
        importInput.value = '';
      }
    });
  }
})();
