// fragments/pdf-chart-generation/app.js
(function () {
  // =========================
  // Constants & configuration
  // =========================
  const DETAILS_DOWNLOAD_SUFFIX = '_modified.json';
  const SERVER_ENDPOINT = '/api/generate-pdf';

  // =========================
  // Module state
  // =========================
  let rawDataCsvText = null;              // raw data csv text
  let detailsJson = null;                 // details.json as a JavaScript object
  let detailsOriginalName = '';           // original details file name

  const metadataInputs = new Map();       // label -> <input|checkbox>
  const channelEditors = [];              // [{ ...inputs }]

  let uiWired = false;                    // prevent double binding
  let allContentSections = [];            // sections created by buildEditor()

  // =========================
  // DOM helpers
  // =========================
  const byId = (id) => /** @type {HTMLElement|null} */(document.getElementById(id));
  const el = (tag, props = {}, children = []) => {
    const node = document.createElement(tag);
    Object.assign(node, props);
    for (const c of children) node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    return node;
  };

  // Simple reusable error dialog
  function showErrorDialog(title, message, details = '') {
    let backdrop = byId('pcg-error-backdrop');
    let dialog = byId('pcg-error-dialog');

    if (!backdrop) {
      backdrop = el('div', {
        id: 'pcg-error-backdrop',
        style: `
          position: fixed;
          inset: 0;
          background: rgba(0,0,0,0.55);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 9999;
        `
      });

      dialog = el('div', {
        id: 'pcg-error-dialog',
        style: `
          background: #1b1b1b;
          color: #fff;
          max-width: 520px;
          width: 90%;
          border-radius: 12px;
          box-shadow: 0 20px 40px rgba(0,0,0,.6);
          padding: 18px 20px;
          box-sizing: border-box;
          font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          border: 1px solid #333;
        `
      });

      const titleEl = el('h2', {
        id: 'pcg-error-title',
        style: 'margin: 0 0 8px; font-size: 1.1rem; font-weight: 600;'
      });

      const msgEl = el('p', {
        id: 'pcg-error-message',
        style: 'margin: 0 0 8px; white-space: pre-wrap; color:#ddd;'
      });

      const detailsEl = el('pre', {
        id: 'pcg-error-details',
        style: `
          margin: 8px 0 0;
          padding: 8px;
          max-height: 160px;
          overflow: auto;
          font-size: 0.8rem;
          background: rgba(0,0,0,0.35);
          border-radius: 8px;
          white-space: pre-wrap;
          border: 1px solid #333;
          color:#cfcfcf;
        `
      });

      const buttonRow = el('div', {
        style: 'margin-top: 14px; display: flex; justify-content: flex-end; gap: 8px;'
      });

      const closeBtn = el('button', {
        textContent: 'Close',
        style: `
          padding: 8px 14px;
          border-radius: 999px;
          border: 1px solid #3a3a3a;
          background: #2a2a2a;
          color: #fff;
          cursor: pointer;
        `
      });

      closeBtn.addEventListener('click', () => {
        backdrop.style.display = 'none';
        document.body.style.overflow = '';
      });

      buttonRow.append(closeBtn);
      dialog.append(titleEl, msgEl, detailsEl, buttonRow);
      backdrop.appendChild(dialog);
      document.body.appendChild(backdrop);
    }

    const titleEl = byId('pcg-error-title');
    const msgEl = byId('pcg-error-message');
    const detailsEl = byId('pcg-error-details');

    if (titleEl) titleEl.textContent = title || 'Error';
    if (msgEl) msgEl.textContent = message || 'Something went wrong.';
    if (detailsEl) {
      detailsEl.textContent = (details || '').trim();
      detailsEl.style.display = details ? 'block' : 'none';
    }

    backdrop.style.display = 'flex';
  }

  // Helper for table headers
  const th = (text, width = '') => el('th', {
    textContent: text,
    style: `white-space: nowrap; padding: 8px; ${width ? 'width: ' + width : ''}`
  });

  // Helper for table inputs
  const tableInputProps = (extraClass = '') => ({
    className: `form-input ${extraClass}`,
    style: `
      width: 100%;
      box-sizing: border-box;
      min-width: 40px;
      padding: 8px 10px;
      background: #000;
      border: 1px solid #333;
      border-radius: 10px;
      color: #fff;
    `
  });

  function labelledInput(labelText, value = '') {
    const wrap = el('div', { style: 'margin: 10px 0' });
    const label = el('label', {
      textContent: labelText,
      style: 'display:block; margin-bottom: 6px; color:#ccc; font-size: 0.9rem;'
    });
    const input = el('input', { type: 'text', value, ...tableInputProps() });
    wrap.append(label, input);
    return { wrap, input };
  }

  function labelledCheckbox(labelText, checked = false) {
    const wrap = el('div', { style: 'margin: 10px 0; display:flex; align-items:center; justify-content:space-between; gap:12px;' });
    const label = el('label', {
      textContent: labelText,
      style: 'color:#ccc; font-size: 0.9rem;'
    });
    const cb = el('input', { type: 'checkbox' });
    cb.checked = !!checked;
    wrap.append(label, cb);
    return { wrap, cb };
  }

  function filenameFromContentDisposition(cdHeader) {
    if (!cdHeader) return null;

    const m1 = cdHeader.match(/filename\*=UTF-8''([^;]+)/i);
    if (m1 && m1[1]) {
      try { return decodeURIComponent(m1[1]); } catch {}
    }

    const m2 = cdHeader.match(/filename="?([^"]+)"?/i);
    if (m2 && m2[1]) return m2[1];

    return null;
  }

  // =========================
  // File picking & classification
  // =========================
  function classifyFiles(files) {
    if (files.length !== 2) {
      return { error: 'Please select a data CSV file and a details JSON file.' };
    }

    const a = files[0];
    const b = files[1];

    if (a.name.toLowerCase().endsWith('.csv') && b.name.toLowerCase().endsWith('.json')) {
      return { data: a, details: b };
    }
    if (a.name.toLowerCase().endsWith('.json') && b.name.toLowerCase().endsWith('.csv')) {
      return { data: b, details: a };
    }

    return { error: 'Please select one .csv file and one .json file.' };
  }

  // =========================
  // Sidebar section switching
  // =========================
  function setActiveSidebarButton(btn) {
    const nav = byId('pcg-editor-nav');
    if (!nav) return;
    nav.querySelectorAll('button[data-section]').forEach(b => b.classList.toggle('active', b === btn));
  }

  function showSection(sectionId) {
    for (const s of allContentSections) {
      s.style.display = (s.id === sectionId) ? 'block' : 'none';
    }
  }

  // =========================
  // Details form builders
  // =========================
  function buildEditor(details) {
    const contentHost = byId('pcg-editor-content-host');
    if (!contentHost) {
      console.error("Required host element not found: pcg-editor-content-host");
      return;
    }

    contentHost.innerHTML = '';

    metadataInputs.clear();
    channelEditors.length = 0;
    allContentSections = [];

    const createSection = (key, title, contentNode) => {
      const section = el('section', { id: key, style: 'display:none;' }, [
        el('h2', { textContent: title, style: 'margin: 0 0 14px;' }),
        contentNode
      ]);
      contentHost.appendChild(section);
      allContentSections.push(section);
    };

    // -------- Metadata --------
    const metadataForm = el('div');
    for (const key in details.metadata) {
      const value = details.metadata[key];
      const field = (typeof value === 'boolean')
        ? labelledCheckbox(key, value)
        : labelledInput(key, value);
      metadataForm.appendChild(field.wrap);
      metadataInputs.set(key, field.input || field.cb);
    }
    createSection('metadata', 'Metadata', metadataForm);

    // -------- Channel Info --------
    const channelInfoForm = el('div');
    const channelTable = el('table', { style: 'width: 100%; border-collapse: collapse;' });
    const channelHeader = el('tr', {}, [
      th('Unique #', '1%'),
      th('Transducer'),
      th('Visible', '1%'),
      th('SOS'),
      th('SOH'),
      th('EOH'),
      th('BTO', '1%'),
      th('RTO', '1%')
    ]);
    const channelBody = el('tbody');
    channelTable.append(channelHeader, channelBody);

    (details.channel_info || []).forEach(channel => {
      const uniqueNumberInput = el('input', { type: 'text', value: channel.unique_number, ...tableInputProps() });
      const transducerInput = el('input', { type: 'text', value: channel.transducer, ...tableInputProps() });
      const visibleCheckbox = el('input', { type: 'checkbox' });
      visibleCheckbox.checked = !!channel.visible;
      const sosInput = el('input', { type: 'text', value: channel.start_of_stabilisation, ...tableInputProps() });
      const sohInput = el('input', { type: 'text', value: channel.start_of_hold, ...tableInputProps() });
      const eohInput = el('input', { type: 'text', value: channel.end_of_hold, ...tableInputProps() });
      const btoInput = el('input', { type: 'text', value: channel.breakout_torque, ...tableInputProps() });
      const rtoInput = el('input', { type: 'text', value: channel.running_torque, ...tableInputProps() });

      const tr = el('tr', {}, [
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [uniqueNumberInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [transducerInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222; text-align:center;' }, [visibleCheckbox]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [sosInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [sohInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [eohInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [btoInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [rtoInput])
      ]);
      channelBody.appendChild(tr);

      channelEditors.push({
        uniqueNumberInput,
        transducerInput,
        visibleCheckbox,
        sosInput,
        sohInput,
        eohInput,
        btoInput,
        rtoInput
      });
    });

    channelInfoForm.appendChild(channelTable);
    createSection('channel-info', 'Channel Info', channelInfoForm);

    // show first section by default
    if (allContentSections.length) {
      showSection(allContentSections[0].id);
    }
  }

  function loadDetails(jsonText) {
    try {
      const details = JSON.parse(jsonText);
      detailsJson = details;
      buildEditor(details);

      // Swap pages
      byId('pcg-initial-content')?.classList.add('hidden');
      byId('pcg-editor-page')?.classList.remove('hidden');
      byId('pcg-editor-nav')?.classList.remove('hidden');

    } catch (e) {
      console.error('Error parsing details.json:', e);
      showErrorDialog(
        'Invalid details JSON',
        'The details file could not be parsed. Please check that it is valid JSON and try again.',
        e && e.message ? e.message : String(e)
      );
    }
  }

  // =========================
  // Apply UI edits back to detailsJson object
  // =========================
  function applyEditsToDetails() {
    if (!detailsJson) return;

    // Metadata
    if (detailsJson.metadata) {
      for (const [key, input] of metadataInputs.entries()) {
        detailsJson.metadata[key] = input.type === 'checkbox' ? input.checked : input.value;
      }
    }

    // Channel Info
    if (Array.isArray(detailsJson.channel_info)) {
      detailsJson.channel_info.forEach((channel, i) => {
        const editor = channelEditors[i];
        if (editor) {
          channel.unique_number = editor.uniqueNumberInput.value;
          channel.transducer = editor.transducerInput.value;
          channel.visible = editor.visibleCheckbox.checked;
          channel.start_of_stabilisation = editor.sosInput.value;
          channel.start_of_hold = editor.sohInput.value;
          channel.end_of_hold = editor.eohInput.value;
          channel.breakout_torque = editor.btoInput.value;
          channel.running_torque = editor.rtoInput.value;
        }
      });
    }
  }

  // =========================
  // Downloads & server I/O
  // =========================
  function downloadTextFile(text, downloadName) {
    const blob = new Blob([text], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = downloadName;
    a.click();
    Promise.resolve().then(() => URL.revokeObjectURL(a.href));
  }

  function timestampedName(prefix, ext = 'json') {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    return `${prefix}_${stamp}.${ext}`;
  }

  async function postFilesToServer(dataCsvText, detailsJsonText) {
    const detailsFile = new File(
      [detailsJsonText],
      timestampedName('details_modified'),
      { type: 'application/json', lastModified: Date.now() }
    );

    const dataFile = new File(
      [dataCsvText],
      timestampedName('data', 'csv'),
      { type: 'text/csv', lastModified: Date.now() }
    );

    const fd = new FormData();
    fd.append('data_csv', dataFile);
    fd.append('details_json', detailsFile);

    let res;
    try {
      res = await fetch(SERVER_ENDPOINT, {
        method: 'POST',
        body: fd,
        cache: 'no-store',
      });
    } catch (err) {
      return { ok: false, networkError: true, errorText: err?.message || String(err) };
    }

    const cd = res.headers.get('Content-Disposition') || '';
    const suggestedName =
      filenameFromContentDisposition(cd) ||
      timestampedName('chart', 'pdf');

    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      return { ok: false, status: res.status, statusText: res.statusText, name: suggestedName, errorText: errText };
    }

    const blob = await res.blob();
    return { ok: true, blob, name: suggestedName };
  }

  // =========================
  // UI wiring
  // =========================
  function initUI() {
    if (uiWired) return;

    const fileInput = /** @type {HTMLInputElement|null} */ (byId('pcg-files'));
    const selectBtn = byId('pcg-btn-select-files');
    const editorNav = byId('pcg-editor-nav');
    const summaryEl = byId('pcg-file-summary');
    const overlay = byId('pcg-loading-overlay');
    const generateBtn = byId('pcg-btn-generate');

    if (!fileInput || !selectBtn || !editorNav || !overlay) {
      console.log('[pcg] initUI: waiting for elements...');
      return;
    }

    uiWired = true;
    console.log('[pcg] UI wired');

    // Select Files button -> opens OS picker (must be synchronous)
    selectBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      fileInput.click();
    });

    // Sidebar section buttons (Metadata, Channel Info, etc.)
    editorNav.querySelectorAll('button[data-section]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const section = btn.getAttribute('data-section');
        if (!section) return;
        setActiveSidebarButton(btn);
        showSection(section);
      });
    });

    // Generate PDF Chart button (sidebar)
    if (generateBtn) {
      generateBtn.addEventListener('click', async (e) => {
        e.preventDefault();

        if (!detailsJson || !rawDataCsvText) {
          showErrorDialog('Files not loaded', 'Please load a data CSV and details JSON before generating the PDF.');
          return;
        }

        applyEditsToDetails();

        const prevOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        overlay.classList.remove('hidden');

        const detailsText = JSON.stringify(detailsJson, null, 2);

        // download modified details.json locally
        {
          const stem = (detailsOriginalName || 'details').replace(/\.json$/i, '') + DETAILS_DOWNLOAD_SUFFIX;
          downloadTextFile(detailsText, stem);
        }

        try {
          const res = await postFilesToServer(rawDataCsvText, detailsText);

          if (!res.ok) {
            const msg = res.networkError
              ? 'Cannot reach the PDF generator. Please make sure the server is running and that you are on the right network.'
              : `The PDF generator returned an error (${res.status} ${res.statusText}).`;

            showErrorDialog('PDF generation failed', msg, (res.errorText || '').slice(0, 2000));
            return;
          }

          const url = URL.createObjectURL(res.blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = res.name;
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);

        } catch (err) {
          console.error(err);
          showErrorDialog('PDF generator unreachable', 'Network or server error while generating the PDF.', err?.message || String(err));
        } finally {
          overlay.classList.add('hidden');
          document.body.style.overflow = prevOverflow;
        }
      });
    }

    // File input change handler
    fileInput.addEventListener('change', async (e) => {

      const files = Array.from(fileInput.files || []);
      const picked = classifyFiles(files);

      if (picked.error) {
        if (summaryEl) {
          summaryEl.textContent = picked.error;
          summaryEl.style.color = 'salmon';
        }
        showErrorDialog('File selection error', picked.error);
        fileInput.value = '';
        return;
      }

      if (summaryEl) {
        summaryEl.style.color = '#cfcfcf';
        summaryEl.textContent = `Data: ${picked.data.name}\nDetails: ${picked.details.name}`;
      }

      detailsOriginalName = picked.details.name;

      const [dataText, detailsText] = await Promise.all([
        picked.data.text(),
        picked.details.text()
      ]);

      rawDataCsvText = dataText;
      loadDetails(detailsText);

      // default to Metadata section
      const firstBtn = editorNav.querySelector('button[data-section="metadata"]');
      if (firstBtn) {
        setActiveSidebarButton(firstBtn);
        showSection('metadata');
      }

      fileInput.value = '';
    });
  }

  // init for standalone page
  document.addEventListener('DOMContentLoaded', initUI);

})();
