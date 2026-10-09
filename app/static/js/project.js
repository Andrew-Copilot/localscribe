/* Project page: operation, metadata editing, uploads, the file table, and processing.

   Two operations share this page: Transcribe (the spoken language, written as
   spoken) and Translate to English (a machine translation). Every label that
   depends on the operation comes from window.PROJECT.info.terms, which the
   server builds once from app/languages.py, so the wording here cannot drift
   from the exports and the document page. */

(() => {
  const slug = window.PROJECT.slug;
  const info = window.PROJECT.info || { terms: {}, compat: {}, model: {}, suggestion: null };
  const TERMS = info.terms || {};
  let operation = window.PROJECT.operation === 'translate' ? 'translate' : 'transcribe';
  let documents = window.PROJECT.documents || [];

  const rows = document.getElementById('doc-rows');
  const noDocs = document.getElementById('no-docs');
  const table = document.getElementById('doc-table');
  const transcribeBtn = document.getElementById('transcribe-btn');
  const docCount = document.getElementById('doc-count');
  const queueNote = document.getElementById('queue-note');
  const languageSelect = document.getElementById('language-select');
  const opSummary = document.getElementById('op-summary');
  const opNote = document.getElementById('op-note');
  const emptyHint = document.getElementById('empty-hint');
  const uploadStatus = document.getElementById('upload-status');

  const ACTIVE = ['queued', 'probing', 'decoding', 'transcribing'];

  const T = (op) => TERMS[op === 'translate' ? 'translate' : 'transcribe'] || {};
  const compat = (op) => (info.compat && info.compat[op]) || { ok: true, level: 'ok', message: '' };
  const blocked = () => !compat(operation).ok;
  const docOperation = (doc) => (doc.operation === 'translate' ? 'translate' : 'transcribe');

  /* How a finished recording is labelled. This reflects what is stored on the
     recording, never the operation currently selected: switching the project
     to Translate does not relabel a transcript that was made before. */
  function resultBadge(doc) {
    switch (doc.output_status) {
      case 'translated':
      case 'english_source':
        return ['badge badge-ok', T('translate').done];
      case 'untranslated':
        return ['badge badge-warn', 'Not translated'];
      case 'unverified':
        return ['badge badge-warn', `${T('translate').done} (unconfirmed)`];
      default:
        return ['badge badge-ok', T('transcribe').done];
    }
  }

  function statusBadge(doc) {
    const op = doc.pending_operation || operation;
    switch (doc.status) {
      case 'uploaded': return ['badge', T(operation).ready];
      case 'queued': return ['badge badge-run', 'Queued'];
      case 'probing': return ['badge badge-run', 'Inspecting'];
      case 'decoding': return ['badge badge-run', 'Decoding audio'];
      case 'transcribing': return ['badge badge-run', T(op).progressive];
      case 'transcribed': return resultBadge(doc);
      case 'failed': return ['badge badge-err', 'Failed'];
      case 'cancelled': return ['badge badge-warn', 'Cancelled'];
      case 'unusable': return ['badge badge-err', 'Unusable file'];
      default: return ['badge', doc.status];
    }
  }

  function resultNote(doc) {
    if (!doc.language_name) return '';
    let text = LS.escapeHtml(doc.language_name) + (doc.language_requested === 'auto' ? ' (detected)' : '');
    switch (doc.output_status) {
      case 'translated': text += ', English translation'; break;
      case 'english_source': text += ', English translation (the speech was English)'; break;
      case 'untranslated': text += ', translation requested but the text is still not English'; break;
      case 'unverified': text += ', translation to English not confirmed'; break;
      default: break;
    }
    return ` &middot; ${text}`;
  }

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

    const action = T(operation).action;
    const off = blocked();

    documents.forEach((doc) => {
      const [cls, label] = statusBadge(doc);
      const media = doc.media || {};
      const kind = media.has_video ? 'video' : 'audio';
      const codec = media.audio_codec ? ` / ${media.audio_codec}` : '';
      const done = doc.status === 'transcribed';
      const name = LS.escapeHtml(doc.filename);
      // On a finished recording the button either redoes the same operation
      // or runs the other one; either way it asks before replacing anything.
      const buttonLabel = done && docOperation(doc) === operation ? 'Redo' : action;

      const tr = document.createElement('tr');
      tr.dataset.id = doc.id;
      tr.innerHTML = `
        <td>
          ${done
            ? `<a href="/project/${encodeURIComponent(slug)}/document/${encodeURIComponent(doc.id)}"><strong>${name}</strong></a>`
            : `<strong>${name}</strong>`}
          <div class="small muted">${LS.bytes(doc.size_bytes)}${
            doc.human_edited ? ' &middot; <span class="badge badge-ok">reviewed</span>' : ''}${
            done ? resultNote(doc) : ''}${
            (doc.low_confidence && doc.output_status !== 'translated' && doc.output_status !== 'unverified')
              ? ` &middot; ${doc.low_confidence} low-confidence words` : ''}</div>
        </td>
        <td class="small">${LS.escapeHtml(media.container || kind)}<div class="muted small">${LS.escapeHtml(kind + codec)}</div></td>
        <td class="num mono">${doc.duration ? LS.clock(doc.duration) : '-'}</td>
        <td class="num mono">${doc.words
          ? doc.words.toLocaleString() + (doc.length_unit === 'characters' ? ' chars' : '')
          : '-'}</td>
        <td>
          <span class="${cls}">${LS.escapeHtml(label)}</span>
          <div class="small muted status-detail">${LS.escapeHtml(doc.status_detail || '')}</div>
        </td>
        <td class="nowrap" style="text-align:right">
          ${done
            ? `<a class="btn btn-small" href="/project/${encodeURIComponent(slug)}/document/${encodeURIComponent(doc.id)}" aria-label="Review ${name}">Review</a>`
            : ''}
          ${ACTIVE.includes(doc.status)
            ? '<span class="small muted">working...</span>'
            : `<button type="button" class="btn btn-small btn-quiet" data-act="one" data-id="${doc.id}"
                 aria-label="${LS.escapeHtml(buttonLabel)}: ${name}"
                 ${off ? 'disabled title="The selected model cannot do this. See the note above."' : ''}>${LS.escapeHtml(buttonLabel)}</button>`}
          <button type="button" class="btn btn-small btn-quiet btn-danger" data-act="del" data-id="${doc.id}"
                  aria-label="Remove ${name}">Remove</button>
        </td>`;
      rows.appendChild(tr);
    });

    const pending = documents.filter(
      (d) => !ACTIVE.includes(d.status) && d.status !== 'unusable' && d.status !== 'transcribed'
    ).length;
    const busy = documents.some((d) => ACTIVE.includes(d.status));

    if (docCount) docCount.textContent = documents.length;
    if (transcribeBtn) {
      transcribeBtn.disabled = busy || off || (!pending && !documents.length);
      transcribeBtn.innerHTML = busy
        ? `${LS.escapeHtml(T(operation).progressive)}...`
        : (pending
          ? `${LS.escapeHtml(action)} <span class="badge badge-ok">${pending}</span>`
          : LS.escapeHtml(action));
      if (!busy && !pending && documents.length) {
        transcribeBtn.disabled = true;
        transcribeBtn.textContent = T(operation).all_done;
      }
      transcribeBtn.title = off ? 'The selected model cannot do this. See the note above.' : '';
    }
    renderOperation();
  }

  /* ------------------------------------------------------------- operation */

  function languageLabel() {
    const option = languageSelect && languageSelect.options[languageSelect.selectedIndex];
    return option ? option.textContent : '';
  }

  /* Everything that explains the current choice, rebuilt whenever it changes:
     what will happen, in which language, with which model, whether that model
     is suitable, and whether anything existing would be replaced. */
  function renderOperation() {
    const terms = T(operation);
    const check = compat(operation);

    document.querySelectorAll('input[name="operation"]').forEach((radio) => {
      radio.checked = radio.value === operation;
    });

    if (opSummary) {
      const existing = documents.filter((d) => d.status === 'transcribed').length;
      opSummary.innerHTML =
        `<strong>${LS.escapeHtml(terms.name)}.</strong> ${LS.escapeHtml(terms.explain)} ` +
        `Spoken language: ${LS.escapeHtml(languageLabel())}. ` +
        `You will get: ${LS.escapeHtml(terms.output)}. ` +
        `Model: ${LS.escapeHtml(info.model.label || '')}` +
        `${check.ok ? '' : ' (not suitable for this)'}.` +
        (existing
          ? ` ${LS.plural(existing, 'recording')} already ${existing === 1 ? 'has' : 'have'} a result;` +
            ' nothing is replaced unless you confirm it.'
          : '');
    }

    if (opNote) {
      opNote.innerHTML = '';
      if (check.message) {
        opNote.hidden = false;
        opNote.className = `notice small${check.ok ? '' : ' notice-warn'}`;
        const text = document.createElement('div');
        text.textContent = check.message;
        opNote.appendChild(text);

        const suggestion = info.suggestion;
        if (!check.ok && suggestion && suggestion.key !== info.model.key) {
          const row = document.createElement('div');
          row.className = 'row';
          row.style.marginTop = '.5rem';
          if (suggestion.downloaded) {
            const use = document.createElement('button');
            use.type = 'button';
            use.className = 'btn btn-small';
            use.id = 'op-use-model';
            use.textContent = `Use ${suggestion.label}`;
            use.title = 'Changes the selected model for every project';
            use.addEventListener('click', () => useModel(suggestion));
            row.appendChild(use);
            const hint = document.createElement('span');
            hint.className = 'muted';
            hint.textContent = 'Already downloaded. This changes the model for every project.';
            row.appendChild(hint);
          } else {
            const link = document.createElement('a');
            link.className = 'btn btn-small';
            link.href = '/settings';
            link.textContent = `Download ${suggestion.label} in AI Settings`;
            row.appendChild(link);
          }
          opNote.appendChild(row);
        }
      } else {
        opNote.hidden = true;
      }
    }

    if (emptyHint) emptyHint.textContent = terms.empty_hint;
  }

  async function useModel(suggestion) {
    try {
      await LS.post('/api/settings', { values: { model: suggestion.key } });
      LS.toast(`Now using ${suggestion.label} for every project.`, 'ok');
      location.reload();
    } catch (err) {
      LS.toast(err.message, 'error');
    }
  }

  document.querySelectorAll('input[name="operation"]').forEach((radio) => {
    radio.addEventListener('change', async () => {
      if (!radio.checked) return;
      operation = radio.value === 'translate' ? 'translate' : 'transcribe';
      render();          // labels, buttons, explanations, compatibility: immediately
      try {
        // Per project. This never rewrites the AI Settings default, and it
        // never touches a recording that already has a result.
        await LS.put(`/api/projects/${encodeURIComponent(slug)}`, { operation });
      } catch (err) {
        LS.toast(`Could not remember this choice for the project: ${err.message}`, 'warn');
      }
    });
  });

  if (languageSelect) languageSelect.addEventListener('change', renderOperation);

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
          `transcript or translation, and every exported output for it. This cannot be undone.`
        )) return;
        button.disabled = true;
        try {
          await LS.del(`/api/projects/${encodeURIComponent(slug)}/documents/${encodeURIComponent(id)}`);
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
        const doc = documents.find((d) => d.id === id);
        let replace = false;
        if (doc && doc.status === 'transcribed') {
          const existing = T(docOperation(doc)).result;
          const next = T(operation).result;
          if (!confirm(
            `"${doc.filename}" already has a ${existing}.\n\n` +
            `${T(operation).action} will replace it as the current result with a new ${next}. ` +
            `The earlier ${existing} is kept in this recording's Edit history, where it can be restored.\n\n` +
            'Continue?'
          )) return;
          replace = true;
        }
        await startTranscription([id], replace);
      }
    });
  }

  const refreshBtn = document.getElementById('refresh-btn');
  if (refreshBtn) refreshBtn.addEventListener('click', refresh);

  /* ----------------------------------------------------------- processing */

  async function startTranscription(ids, replace) {
    if (window.LSConsole) LSConsole.open();
    if (transcribeBtn) transcribeBtn.disabled = true;

    // Sent explicitly, so a run uses exactly what the page shows rather than
    // whatever the saved defaults happen to be by the time the job starts.
    const language = languageSelect ? languageSelect.value : undefined;
    const body = ids
      ? { documents: ids, force: true, replace: !!replace, language, operation }
      : { language, operation };

    try {
      const result = await LS.post(`/api/projects/${encodeURIComponent(slug)}/transcribe`, body);
      documents = result.documents || documents;
      render();

      if (result.queued.length) {
        LS.toast(
          `Queued ${LS.plural(result.queued.length, 'file')} (${T(operation).action}). ` +
          'Watch the console for progress.', 'ok');
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
    transcribeBtn.addEventListener('click', () => startTranscription(null, false));
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
          ? `Added ${LS.plural(added, 'file')}. ${T(operation).upload_hint}`
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

  const deleteBtn = document.getElementById('delete-project-btn');
  if (deleteBtn) {
    deleteBtn.addEventListener('click', async () => {
      const count = documents.length;
      if (!confirm(
        `Delete this entire project?\n\nThis permanently removes ` +
        `${LS.plural(count, 'recording')}, all transcripts and translations, and all exported ` +
        `files. This cannot be undone.\n\nConsider exporting the project first.`
      )) return;
      if (!confirm('Last check: really delete everything in this project?')) return;

      try {
        await LS.del(`/api/projects/${encodeURIComponent(slug)}`);
        location.href = '/';
      } catch (err) {
        LS.toast(err.message, 'error');
      }
    });
  }

  render();
})();
