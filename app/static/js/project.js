/* Project page: metadata editing, uploads, the file table, and transcription. */

(() => {
  const slug = window.PROJECT.slug;
  let documents = window.PROJECT.documents || [];

  const rows = document.getElementById('doc-rows');
  const noDocs = document.getElementById('no-docs');
  const table = document.getElementById('doc-table');
  const transcribeBtn = document.getElementById('transcribe-btn');
  const docCount = document.getElementById('doc-count');
  const queueNote = document.getElementById('queue-note');

  const ACTIVE = ['queued', 'probing', 'decoding', 'transcribing'];

  const STATUS = {
    uploaded: ['badge', 'Ready to transcribe'],
    queued: ['badge badge-run', 'Queued'],
    probing: ['badge badge-run', 'Inspecting'],
    decoding: ['badge badge-run', 'Decoding audio'],
    transcribing: ['badge badge-run', 'Transcribing'],
    transcribed: ['badge badge-ok', 'Transcribed'],
    failed: ['badge badge-err', 'Failed'],
    cancelled: ['badge badge-warn', 'Cancelled'],
    unusable: ['badge badge-err', 'Unusable file'],
  };

  /* ------------------------------------------------------------ file table */

  function render() {
    if (!rows) return;
    rows.innerHTML = '';

    if (!documents.length) {
      if (table) table.hidden = true;
      if (noDocs) noDocs.hidden = false;
    } else {
      if (table) table.hidden = false;
      if (noDocs) noDocs.hidden = true;
    }

    documents.forEach((doc) => {
      const [cls, normalLabel] = STATUS[doc.status] || ['badge', doc.status];
      const label = doc.media_missing ? 'Source media missing' : normalLabel;
      const media = doc.media || {};
      const kind = media.has_video ? 'video' : 'audio';
      const codec = media.audio_codec ? ` / ${media.audio_codec}` : '';
      const done = doc.status === 'transcribed';

      const tr = document.createElement('tr');
      tr.dataset.id = doc.id;
      tr.innerHTML = `
        <td>
          ${done
            ? `<a href="/project/${encodeURIComponent(slug)}/document/${encodeURIComponent(doc.id)}"><strong>${LS.escapeHtml(doc.filename)}</strong></a>`
            : `<strong>${LS.escapeHtml(doc.filename)}</strong>`}
          <div class="small muted">${LS.bytes(doc.size_bytes)}${
            doc.human_edited ? ' &middot; <span class="badge badge-ok">reviewed</span>' : ''}${
            doc.low_confidence ? ` &middot; ${doc.low_confidence} low-confidence words` : ''}</div>
        </td>
        <td class="small">${LS.escapeHtml(media.container || kind)}<div class="muted small">${LS.escapeHtml(kind + codec)}</div></td>
        <td class="num mono">${doc.duration ? LS.clock(doc.duration) : '-'}</td>
        <td class="num mono">${doc.words ? doc.words.toLocaleString() : '-'}</td>
        <td>
          <span class="${cls}">${LS.escapeHtml(label)}</span>
          <div class="small muted status-detail">${LS.escapeHtml(
            doc.media_missing
              ? 'This archive did not include the original recording.'
              : (doc.status_detail || '')
          )}</div>
        </td>
        <td class="nowrap" style="text-align:right">
          ${done
            ? `<a class="btn btn-small" href="/project/${encodeURIComponent(slug)}/document/${encodeURIComponent(doc.id)}">Review</a>`
            : ''}
          ${doc.media_missing
            ? '<span class="small muted">Add the source recording to transcribe</span>'
            : ACTIVE.includes(doc.status)
            ? '<span class="small muted">working...</span>'
            : `<button type="button" class="btn btn-small btn-quiet" data-act="one" data-id="${doc.id}">${done ? 'Redo' : 'Transcribe'}</button>`}
          <button type="button" class="btn btn-small btn-quiet btn-danger" data-act="del" data-id="${doc.id}">Remove</button>
        </td>`;
      rows.appendChild(tr);
    });

    const pending = documents.filter(
      (d) => !d.media_missing && !ACTIVE.includes(d.status) &&
        d.status !== 'unusable' && d.status !== 'transcribed'
    ).length;
    const busy = documents.some((d) => ACTIVE.includes(d.status));
    const missingMedia = documents.some((d) => d.media_missing);

    if (docCount) docCount.textContent = documents.length;
    if (transcribeBtn) {
      transcribeBtn.disabled = busy || (!pending && !documents.length);
      transcribeBtn.innerHTML = busy
        ? 'Transcribing...'
        : (pending
          ? `Transcribe <span class="badge badge-ok">${pending}</span>`
          : 'Transcribe');
      if (!busy && !pending && documents.length) {
        transcribeBtn.disabled = true;
        transcribeBtn.textContent = missingMedia ? 'Source media missing' : 'All transcribed';
      }
    }
  }

  async function refresh() {
    try {
      const data = await LS.get(`/api/projects/${encodeURIComponent(slug)}`);
      documents = data.documents || [];
      render();
    } catch (err) {
      LS.toast(`Could not refresh the file list: ${err.message}`, 'warn');
    }
  }

  if (rows) {
    rows.addEventListener('click', async (event) => {
      const button = event.target.closest('button[data-act]');
      if (!button) return;
      const id = button.dataset.id;

      if (button.dataset.act === 'del') {
        const doc = documents.find((d) => d.id === id);
        const name = doc ? doc.filename : 'this file';
        if (!confirm(
          `Remove "${name}"?\n\nThis permanently deletes the media file, its ` +
          `transcript, and every exported output for it.`
        )) return;
        const snapshot = confirm(
          'Create a local recovery snapshot of the whole project first?\n\n' +
          'Choose Cancel to continue without a snapshot.'
        );
        button.disabled = true;
        try {
          await LS.del(
            `/api/projects/${encodeURIComponent(slug)}/documents/` +
            `${encodeURIComponent(id)}?snapshot=${snapshot}`
          );
          documents = documents.filter((d) => d.id !== id);
          render();
          LS.toast(`Removed ${name}.`, 'info');
        } catch (err) {
          LS.toast(err.message, 'error');
          button.disabled = false;
        }
        return;
      }

      if (button.dataset.act === 'one') {
        await startTranscription([id]);
      }
    });
  }

  const refreshBtn = document.getElementById('refresh-btn');
  if (refreshBtn) refreshBtn.addEventListener('click', refresh);

  /* ---------------------------------------------------------- transcribing */

  async function startTranscription(ids) {
    if (window.LSConsole) LSConsole.open();
    if (transcribeBtn) transcribeBtn.disabled = true;

    try {
      const result = await LS.post(`/api/projects/${encodeURIComponent(slug)}/transcribe`,
        ids ? { documents: ids, force: true } : {});
      documents = result.documents || documents;
      render();

      if (result.queued.length) {
        LS.toast(
          `Queued ${LS.plural(result.queued.length, 'file')} for transcription. ` +
          `Watch the console for progress.`, 'ok');
      }
      if (result.skipped.length && !result.queued.length) {
        const reasons = [...new Set(result.skipped.map((s) => s.reason))].join('; ');
        LS.toast(`Nothing was queued: ${reasons}`, 'warn', 8000);
      }
      if (queueNote) {
        if (result.skipped.length) {
          queueNote.hidden = false;
          queueNote.innerHTML = `Skipped ${LS.plural(result.skipped.length, 'file')}: ` +
            result.skipped.map((s) => LS.escapeHtml(s.reason)).join(', ');
        } else {
          queueNote.hidden = true;
        }
      }
    } catch (err) {
      LS.toast(err.message, 'error', 12000);
      render();
    }
  }

  if (transcribeBtn) {
    transcribeBtn.addEventListener('click', () => startTranscription(null));
  }

  /* Console traffic drives the table: a finished or failed job refreshes it,
     and status lines update the row in place without a round trip. */
  document.addEventListener('ls:console', (event) => {
    const e = event.detail;
    if (!e || !e.data) return;
    if (e.level === 'success' && /=== .* done ===/.test(e.message)) refresh();
    if (e.level === 'error' && e.data.job) refresh();
    if (e.level === 'heartbeat') return;
  });

  // A slow poll is the backstop: the console covers the normal case, this
  // catches anything that finished while the socket was reconnecting.
  setInterval(() => {
    if (documents.some((d) => ACTIVE.includes(d.status))) refresh();
  }, 5000);

  /* ---------------------------------------------------------------- upload */

  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const pickBtn = document.getElementById('pick-files');
  const progress = document.getElementById('upload-progress');
  const progressFill = progress ? progress.firstElementChild : null;
  const uploadStatus = document.getElementById('upload-status');

  if (pickBtn && fileInput) pickBtn.addEventListener('click', () => fileInput.click());
  if (fileInput) {
    fileInput.addEventListener('change', () => {
      if (fileInput.files && fileInput.files.length) upload(fileInput.files);
    });
  }

  if (dropzone) {
    ['dragenter', 'dragover'].forEach((type) => {
      dropzone.addEventListener(type, (event) => {
        event.preventDefault();
        dropzone.classList.add('hot');
      });
    });
    ['dragleave', 'drop'].forEach((type) => {
      dropzone.addEventListener(type, (event) => {
        event.preventDefault();
        if (type === 'dragleave' && dropzone.contains(event.relatedTarget)) return;
        dropzone.classList.remove('hot');
      });
    });
    dropzone.addEventListener('drop', (event) => {
      const files = event.dataTransfer && event.dataTransfer.files;
      if (files && files.length) upload(files);
    });
  }

  function upload(files) {
    const body = new FormData();
    let total = 0;
    Array.from(files).forEach((file) => {
      body.append('files', file, file.name);
      total += file.size;
    });

    if (progress) progress.hidden = false;
    if (uploadStatus) {
      uploadStatus.textContent =
        `Uploading ${LS.plural(files.length, 'file')} (${LS.bytes(total)})...`;
    }

    // XHR rather than fetch: upload progress events matter for a 2 GB video.
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `/api/projects/${encodeURIComponent(slug)}/documents`);
    xhr.setRequestHeader('X-Instance-Token', LS.token);

    xhr.upload.addEventListener('progress', (event) => {
      if (!event.lengthComputable || !progressFill) return;
      progressFill.style.width = `${Math.round((event.loaded / event.total) * 100)}%`;
      if (uploadStatus) {
        uploadStatus.textContent =
          `Uploading ${LS.bytes(event.loaded)} of ${LS.bytes(event.total)}...`;
      }
    });

    xhr.addEventListener('load', () => {
      if (progress) progress.hidden = true;
      if (progressFill) progressFill.style.width = '0%';
      if (fileInput) fileInput.value = '';

      let payload = null;
      try { payload = JSON.parse(xhr.responseText); } catch (e) { /* non-JSON error */ }

      if (xhr.status < 200 || xhr.status >= 300) {
        const detail = (payload && payload.detail) || `${xhr.status} ${xhr.statusText}`;
        if (uploadStatus) uploadStatus.textContent = '';
        LS.toast(`Upload failed: ${detail}`, 'error', 10000);
        return;
      }

      documents = payload.documents || documents;
      render();

      const added = (payload.added || []).length;
      const rejected = payload.rejected || [];
      if (uploadStatus) {
        uploadStatus.textContent = added
          ? `Added ${LS.plural(added, 'file')}. Press Transcribe when ready.`
          : '';
      }
      if (added) LS.toast(`Added ${LS.plural(added, 'file')}.`, 'ok');
      rejected.forEach((r) => LS.toast(`${r.filename}: ${r.reason}`, 'warn', 9000));
    });

    xhr.addEventListener('error', () => {
      if (progress) progress.hidden = true;
      LS.toast('The upload could not complete. Is the app still running?', 'error');
    });

    xhr.send(body);
  }

  /* ------------------------------------------------------------- metadata */

  const metaForm = document.getElementById('meta-form');
  const editBtn = document.getElementById('edit-meta-btn');
  const metaCancel = document.getElementById('meta-cancel');
  const metaState = document.getElementById('meta-state');

  if (editBtn && metaForm) {
    editBtn.addEventListener('click', () => {
      metaForm.hidden = !metaForm.hidden;
      if (!metaForm.hidden) document.getElementById('m-title').focus();
    });
  }
  if (metaCancel && metaForm) {
    metaCancel.addEventListener('click', () => { metaForm.hidden = true; });
  }

  if (metaForm) {
    metaForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = new FormData(metaForm);
      const payload = {};
      data.forEach((value, key) => { payload[key] = value.toString(); });

      const submit = metaForm.querySelector('button[type=submit]');
      submit.disabled = true;
      if (metaState) { metaState.textContent = 'Saving...'; metaState.className = 'save-state'; }

      try {
        const result = await LS.put(`/api/projects/${encodeURIComponent(slug)}`, payload);
        if (metaState) {
          metaState.textContent = 'Saved';
          metaState.className = 'save-state saved';
        }
        LS.toast('Project details saved.', 'ok');
        const sensitivity = metaForm.elements.namedItem('data_sensitivity');
        document.getElementById('project-sensitivity').textContent =
          `User-declared sensitivity: ${sensitivity.selectedOptions[0].textContent}`;
        if (result.project.title) {
          document.querySelector('.page-head h1').textContent = result.project.title;
          document.title = `${result.project.title} - Local Scribe`;
        }
      } catch (err) {
        if (metaState) {
          metaState.textContent = 'Not saved';
          metaState.className = 'save-state dirty';
        }
        LS.toast(`Could not save: ${err.message}`, 'error');
      } finally {
        submit.disabled = false;
      }
    });
  }

  /* ----------------------------------------- reusable vocabulary profiles */

  const profileSelect = document.getElementById('vocabulary-profile');
  const profileState = document.getElementById('vocabulary-state');

  function showProfileState(text, className = 'save-state') {
    if (!profileState) return;
    profileState.textContent = text;
    profileState.className = className;
  }

  async function assignVocabularyProfile(profileId) {
    await LS.put(`/api/projects/${encodeURIComponent(slug)}`, {
      vocabulary_profile_id: profileId,
    });
    window.PROJECT.vocabularyProfileId = profileId;
    showProfileState('Saved', 'save-state saved');
    LS.toast(profileId ? 'Vocabulary profile assigned to this project.' : 'Profile removed.', 'ok');
  }

  const assignProfileBtn = document.getElementById('save-vocabulary-profile');
  if (assignProfileBtn && profileSelect) {
    assignProfileBtn.addEventListener('click', async () => {
      assignProfileBtn.disabled = true;
      showProfileState('Saving...');
      try {
        await assignVocabularyProfile(profileSelect.value);
      } catch (err) {
        showProfileState('Not saved', 'save-state dirty');
        LS.toast(`Could not assign the profile: ${err.message}`, 'error');
      } finally {
        assignProfileBtn.disabled = false;
      }
    });
  }

  const deleteProfileBtn = document.getElementById('delete-vocabulary-profile');
  if (deleteProfileBtn && profileSelect) {
    deleteProfileBtn.addEventListener('click', async () => {
      const profileId = profileSelect.value;
      if (!profileId) {
        LS.toast('Choose a profile to delete.', 'info');
        return;
      }
      if (!confirm(
        'Delete this reusable profile from the local library? Its terms will be ' +
        'removed from this computer, but transcripts already created are unchanged.'
      )) return;
      deleteProfileBtn.disabled = true;
      try {
        await LS.del(`/api/vocabulary-profiles/${encodeURIComponent(profileId)}`);
        await refreshVocabularyProfiles('');
        showProfileState('Profile deleted', 'save-state saved');
        LS.toast('Vocabulary profile deleted.', 'ok');
      } catch (err) {
        LS.toast(`Could not delete the profile: ${err.message}`, 'warn');
      } finally {
        deleteProfileBtn.disabled = false;
      }
    });
  }

  async function refreshVocabularyProfiles(selectedId) {
    const result = await LS.get('/api/vocabulary-profiles');
    const current = selectedId || (profileSelect && profileSelect.value) || '';
    if (!profileSelect) return;
    profileSelect.replaceChildren(new Option('No profile', ''));
    (result.profiles || []).forEach((profile) => {
      const option = new Option(
        `${profile.name} · ${profile.term_count} terms`, profile.id
      );
      profileSelect.add(option);
    });
    profileSelect.value = current;
  }

  const profileCreateForm = document.getElementById('vocabulary-create-form');
  if (profileCreateForm) {
    profileCreateForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const settings = {};
      const language = document.getElementById('vocabulary-language').value.trim();
      const task = document.getElementById('vocabulary-task').value;
      const beamSize = document.getElementById('vocabulary-beam-size').value;
      const bestOf = document.getElementById('vocabulary-best-of').value;
      const vad = document.getElementById('vocabulary-vad').value;
      if (language) settings.language = language;
      if (task) settings.task = task;
      if (beamSize) settings.beam_size = Number(beamSize);
      if (bestOf) settings.best_of = Number(bestOf);
      if (vad) settings.vad_filter = vad === 'true';
      if (document.getElementById('vocabulary-multilingual').checked) {
        settings.multilingual = true;
      }
      const submit = profileCreateForm.querySelector('button[type=submit]');
      submit.disabled = true;
      try {
        const result = await LS.post('/api/vocabulary-profiles', {
          name: document.getElementById('vocabulary-name').value,
          target: document.getElementById('vocabulary-target').value,
          terms: document.getElementById('vocabulary-terms').value.split(/[\n,;]+/),
          settings,
        });
        await refreshVocabularyProfiles(result.profile.id);
        await assignVocabularyProfile(result.profile.id);
        profileCreateForm.reset();
        LS.toast(`Created reusable profile “${result.profile.name}”.`, 'ok');
      } catch (err) {
        showProfileState('Not saved', 'save-state dirty');
        LS.toast(`Could not create the profile: ${err.message}`, 'error');
      } finally {
        submit.disabled = false;
      }
    });
  }

  const profileImportForm = document.getElementById('vocabulary-import-form');
  if (profileImportForm) {
    profileImportForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const file = document.getElementById('vocabulary-file').files[0];
      if (!file) return;
      const body = new FormData();
      body.append('file', file);
      body.append('name', document.getElementById('vocabulary-import-name').value);
      body.append('target', document.getElementById('vocabulary-import-target').value);
      const submit = profileImportForm.querySelector('button[type=submit]');
      submit.disabled = true;
      try {
        const result = await LS.post('/api/vocabulary-profiles/import', body);
        await refreshVocabularyProfiles(result.profile.id);
        await assignVocabularyProfile(result.profile.id);
        profileImportForm.reset();
        LS.toast(`Imported reusable profile “${result.profile.name}”.`, 'ok');
      } catch (err) {
        showProfileState('Not saved', 'save-state dirty');
        LS.toast(`Could not import the profile: ${err.message}`, 'error');
      } finally {
        submit.disabled = false;
      }
    });
  }

  /* -------------------------------------------------------- export/delete */

  const exportBtn = document.getElementById('export-btn');
  if (exportBtn) {
    exportBtn.addEventListener('click', () => {
      LS.toast('Building the project archive. The download will start shortly.', 'info');
      // A plain navigation lets the browser handle the download and the
      // Content-Disposition filename.
      location.href = `/api/projects/${encodeURIComponent(slug)}/export?include_media=true`;
    });
  }

  const snapshotIncludeMedia = document.getElementById('snapshot-include-media');
  const createSnapshotBtn = document.getElementById('create-snapshot-btn');
  if (createSnapshotBtn) {
    createSnapshotBtn.addEventListener('click', async () => {
      createSnapshotBtn.disabled = true;
      try {
        const result = await LS.post(
          `/api/projects/${encodeURIComponent(slug)}/snapshots`,
          { include_media: !snapshotIncludeMedia || snapshotIncludeMedia.checked }
        );
        LS.toast('Local recovery snapshot created.', 'ok');
        const select = document.getElementById('snapshot-select');
        if (select && result.snapshot) {
          const option = document.createElement('option');
          option.value = result.snapshot.snapshot_id;
          option.textContent =
            `${result.snapshot.created.slice(0, 19).replace('T', ' ')} · ` +
            `${result.snapshot.size_bytes.toLocaleString()} bytes`;
          select.prepend(option);
          select.value = option.value;
          document.getElementById('restore-snapshot-btn').disabled = false;
        }
        location.reload();
      } catch (err) {
        LS.toast(`Could not create a snapshot: ${err.message}`, 'error');
      } finally {
        createSnapshotBtn.disabled = false;
      }
    });
  }

  const restoreSnapshotBtn = document.getElementById('restore-snapshot-btn');
  if (restoreSnapshotBtn) {
    restoreSnapshotBtn.addEventListener('click', async () => {
      const select = document.getElementById('snapshot-select');
      const mode = document.getElementById('snapshot-restore-mode').value;
      if (!select || !select.value || mode === 'abort') {
        LS.toast('No restore was performed.', 'info');
        return;
      }
      if (mode === 'replace' && !confirm(
        'Replace this project with the selected snapshot? A safety snapshot of ' +
        'the current project will be created first.'
      )) return;
      restoreSnapshotBtn.disabled = true;
      try {
        const result = await LS.post(
          `/api/projects/${encodeURIComponent(slug)}/snapshots/` +
          `${encodeURIComponent(select.value)}/restore`,
          { mode }
        );
        if (result.aborted) {
          LS.toast('Restore cancelled.', 'info');
        } else {
          location.href = `/project/${encodeURIComponent(result.project.slug)}`;
        }
      } catch (err) {
        LS.toast(`Could not restore the snapshot: ${err.message}`, 'error', 10000);
        restoreSnapshotBtn.disabled = false;
      }
    });
  }

  const startBoxBackupBtn = document.getElementById('start-box-backup-btn');
  const cancelBoxBackupBtn = document.getElementById('cancel-box-backup-btn');
  const boxBackupStatus = document.getElementById('box-backup-status');
  let boxBackupJobId = null;
  let boxBackupPoll = null;
  let boxBackupReported = null;

  function showBoxBackup(job) {
    if (!job || !boxBackupStatus) return;
    const labels = {
      queued: 'Waiting to start…',
      running: job.stage === 'building_archive'
        ? 'Building checksummed archive…'
        : `Copying archive (${LS.bytes(job.bytes_copied)} of ${LS.bytes(job.total_bytes)})…`,
      complete: `Backup verified: ${job.filename} (${LS.bytes(job.total_bytes)}).`,
      failed: `Backup failed: ${job.error || 'Retry the operation.'}`,
      cancelled: 'Backup cancelled. Any incomplete copy was removed.',
    };
    boxBackupStatus.textContent = labels[job.status] || 'Checking backup status…';
    const active = job.status === 'queued' || job.status === 'running';
    startBoxBackupBtn.disabled = active;
    cancelBoxBackupBtn.hidden = !active;
    if (job.status === 'complete' && job.verified
        && boxBackupReported !== job.job_id) {
      boxBackupReported = job.job_id;
      LS.toast('Box Sync copy completed and checksum verification passed.', 'ok');
    }
    if (!active && boxBackupPoll) {
      clearInterval(boxBackupPoll);
      boxBackupPoll = null;
    }
  }

  async function pollBoxBackup() {
    if (!boxBackupJobId) return;
    try {
      const result = await LS.get(
        `/api/projects/${encodeURIComponent(slug)}/box-backup` +
        `?job_id=${encodeURIComponent(boxBackupJobId)}`
      );
      showBoxBackup(result.backup);
    } catch (err) {
      if (boxBackupStatus) boxBackupStatus.textContent = err.message;
      if (boxBackupPoll) clearInterval(boxBackupPoll);
      boxBackupPoll = null;
    }
  }

  if (startBoxBackupBtn) {
    startBoxBackupBtn.addEventListener('click', async () => {
      const syncConfirmed =
        document.getElementById('confirm-box-sync-destination').checked;
      if (!syncConfirmed) {
        LS.toast('Confirm your selected folder is managed by your Box Sync client.', 'warn');
        return;
      }
      if (!confirm(
        'Copy a checksummed archive of this project into the configured local ' +
        'Box Sync folder? The Box Sync client may upload it according to your ' +
        'institutional account and folder policy.'
      )) return;

      startBoxBackupBtn.disabled = true;
      boxBackupStatus.textContent = 'Starting explicit backup…';
      try {
        const result = await LS.post(
          `/api/projects/${encodeURIComponent(slug)}/box-backup`,
          {
            confirm_sync_destination: true,
            independently_verified_box_health:
              document.getElementById('confirm-box-health').checked,
            include_media:
              document.getElementById('box-backup-include-media').checked,
          }
        );
        boxBackupJobId = result.backup.job_id;
        showBoxBackup(result.backup);
        if (!boxBackupPoll) boxBackupPoll = setInterval(pollBoxBackup, 700);
      } catch (err) {
        boxBackupStatus.textContent = err.message;
        startBoxBackupBtn.disabled = false;
      }
    });
  }

  if (cancelBoxBackupBtn) {
    cancelBoxBackupBtn.addEventListener('click', async () => {
      if (!boxBackupJobId) return;
      cancelBoxBackupBtn.disabled = true;
      try {
        await LS.post(
          `/api/projects/${encodeURIComponent(slug)}/box-backup/` +
          `${encodeURIComponent(boxBackupJobId)}/cancel`
        );
        boxBackupStatus.textContent = 'Cancellation requested…';
      } catch (err) {
        LS.toast(err.message, 'warn');
      } finally {
        cancelBoxBackupBtn.disabled = false;
      }
    });
  }

  if (startBoxBackupBtn) {
    LS.get(`/api/projects/${encodeURIComponent(slug)}/box-backup`)
      .then((result) => {
        const job = result.backup;
        boxBackupJobId = job.job_id;
        showBoxBackup(job);
        if (job.status === 'queued' || job.status === 'running') {
          boxBackupPoll = setInterval(pollBoxBackup, 700);
        }
      })
      .catch(() => {});
  }

  const deleteBtn = document.getElementById('delete-project-btn');
  if (deleteBtn) {
    deleteBtn.addEventListener('click', async () => {
      const count = documents.length;
      if (!confirm(
        `Delete this entire project?\n\nThis permanently removes ` +
        `${LS.plural(count, 'recording')}, all transcripts, and all exported ` +
        `files. Existing recovery snapshots are kept.`
      )) return;
      const snapshot = confirm(
        'Create a local recovery snapshot of the whole project first?\n\n' +
        'Choose Cancel to continue without a new snapshot.'
      );

      try {
        await LS.del(
          `/api/projects/${encodeURIComponent(slug)}?snapshot=${snapshot}`
        );
        location.href = '/';
      } catch (err) {
        LS.toast(err.message, 'error');
      }
    });
  }

  render();
})();
