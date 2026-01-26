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
  const channelEditors = [];              // [{ channel, transducerInput, gaugeInput, visibleCheckbox }]
  const massSpecTimingEditors = [];       // [{ label, startInput, stopInput }]
  const holdsEditors = [];                // [{...inputs}]
  const cyclesEditors = [];               // [{...inputs}]
  let calibrationEditor = {};             // {channelNameInput, channelIndexInput, maxRangeInput, keyPointsInputs}

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
    massSpecTimingEditors.length = 0;
    holdsEditors.length = 0;
    cyclesEditors.length = 0;
    calibrationEditor = {};
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
      th('Channel'),
      th('Transducer'),
      th('Gauge'),
      th('Visible', '1%')
    ]);
    const channelBody = el('tbody');
    channelTable.append(channelHeader, channelBody);

    details.channel_info.forEach(channel => {
      const transducerInput = el('input', { type: 'text', value: channel.transducer, ...tableInputProps() });
      const gaugeInput = el('input', { type: 'text', value: channel.gauge, ...tableInputProps() });
      const visibleCheckbox = el('input', { type: 'checkbox' });
      visibleCheckbox.checked = !!channel.visible;

      const tr = el('tr', {}, [
        el('td', { textContent: channel.channel, style: 'padding:8px; border-bottom:1px solid #222;' }),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [transducerInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [gaugeInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222; text-align:center;' }, [visibleCheckbox])
      ]);
      channelBody.appendChild(tr);

      channelEditors.push({ channel: channel.channel, transducerInput, gaugeInput, visibleCheckbox });
    });

    channelInfoForm.appendChild(channelTable);
    createSection('channel-info', 'Channel Info', channelInfoForm);

    // -------- Mass Spec Timings --------
    const massSpecTimingsForm = el('div');
    const massSpecTable = el('table', { style: 'width: 100%; border-collapse: collapse;' });
    const massSpecHeader = el('tr', {}, [
      th('Label', '20%'),
      th('Start'),
      th('Stop')
    ]);
    const massSpecBody = el('tbody');
    massSpecTable.append(massSpecHeader, massSpecBody);

    details.mass_spec_timings.forEach(timing => {
      const startInput = el('input', { type: 'text', value: timing.start, ...tableInputProps() });
      const stopInput = el('input', { type: 'text', value: timing.stop, ...tableInputProps() });

      const tr = el('tr', {}, [
        el('td', { textContent: timing.label, style: 'padding:8px; border-bottom:1px solid #222;' }),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [startInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [stopInput])
      ]);
      massSpecBody.appendChild(tr);

      massSpecTimingEditors.push({ label: timing.label, startInput, stopInput });
    });

    massSpecTimingsForm.appendChild(massSpecTable);
    createSection('mass-spec-timings', 'Mass Spec Timings', massSpecTimingsForm);

    // -------- Holds --------
    const holdsForm = el('div');
    const holdsTable = el('table', { style: 'width: 100%; border-collapse: collapse;' });
    const holdsHeader = el('tr', {}, [
      th('Cycle Index', '1%'),
      th('Channel'),
      th('Start of Stabilisation'),
      th('Start of Hold'),
      th('End of Hold'),
      th('Breakout Torque', '1%'),
      th('Running Torque', '1%'),
      th('', '1%')
    ]);
    const holdsBody = el('tbody');
    holdsTable.append(holdsHeader, holdsBody);

    const addHoldRow = (hold) => {
      const cycleIndexInput = el('input', { type: 'number', value: hold.cycle_index, min: '0', step: '1', ...tableInputProps() });
      const channelInput = el('input', { type: 'text', value: hold.channel, ...tableInputProps() });
      const startOfStabilisationInput = el('input', { type: 'text', value: hold.start_of_stabilisation, ...tableInputProps() });
      const startOfHoldInput = el('input', { type: 'text', value: hold.start_of_hold, ...tableInputProps() });
      const endOfHoldInput = el('input', { type: 'text', value: hold.end_of_hold, ...tableInputProps() });
      const breakoutTorqueInput = el('input', { type: 'text', value: hold.breakout_torque, ...tableInputProps() });
      const runningTorqueInput = el('input', { type: 'text', value: hold.running_torque, ...tableInputProps() });

      const deleteButton = el('button', {
        textContent: 'Delete',
        style: `
          width: 100%;
          padding: 8px 10px;
          border-radius: 10px;
          border: 1px solid #3a3a3a;
          background: #2a2a2a;
          color: #fff;
          cursor: pointer;
        `
      });

      const tr = el('tr', {}, [
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [cycleIndexInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [channelInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [startOfStabilisationInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [startOfHoldInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [endOfHoldInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [breakoutTorqueInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [runningTorqueInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [deleteButton])
      ]);

      holdsBody.appendChild(tr);

      const editor = {
        tr,
        cycleIndexInput,
        channelInput,
        startOfStabilisationInput,
        startOfHoldInput,
        endOfHoldInput,
        breakoutTorqueInput,
        runningTorqueInput
      };

      deleteButton.addEventListener('click', (e) => {
        e.preventDefault();
        holdsBody.removeChild(tr);
        const idx = holdsEditors.indexOf(editor);
        if (idx !== -1) holdsEditors.splice(idx, 1);
      });

      holdsEditors.push(editor);
    };

    (details.holds || []).forEach(addHoldRow);

    const addHoldButton = el('button', {
      textContent: 'Add Hold Row',
      style: `
        margin-top: 10px;
        width: 100%;
        padding: 10px 12px;
        border-radius: 12px;
        border: 1px solid #3a3a3a;
        background: #2a2a2a;
        color: #fff;
        cursor: pointer;
      `
    });

    let nextHoldIndex = Math.max(0, ...(details.holds || []).map(h => Number(h.cycle_index) || 0)) + 1;
    addHoldButton.addEventListener('click', (e) => {
      e.preventDefault();
      addHoldRow({
        cycle_index: nextHoldIndex++,
        channel: '',
        start_of_stabilisation: '',
        start_of_hold: '',
        end_of_hold: '',
        breakout_torque: '',
        running_torque: ''
      });
    });

    holdsForm.append(holdsTable, addHoldButton);
    createSection('holds', 'Holds', holdsForm);

    // -------- Cycles --------
    const cyclesForm = el('div');
    const cyclesTable = el('table', { style: 'width: 100%; border-collapse: collapse;' });
    const cyclesHeader = el('tr', {}, [
      th('Cycle Index', '1%'),
      th('BTO'),
      th('BTC'),
      th('', '1%')
    ]);
    const cyclesBody = el('tbody');
    cyclesTable.append(cyclesHeader, cyclesBody);

    const addCycleRow = (cycle) => {
      const cycleIndexInput = el('input', { type: 'number', value: cycle.cycle_index, min: '0', step: '1', ...tableInputProps() });
      const btoInput = el('input', { type: 'text', value: cycle.bto, ...tableInputProps() });
      const btcInput = el('input', { type: 'text', value: cycle.btc, ...tableInputProps() });

      const deleteButton = el('button', {
        textContent: 'Delete',
        style: `
          width: 100%;
          padding: 8px 10px;
          border-radius: 10px;
          border: 1px solid #3a3a3a;
          background: #2a2a2a;
          color: #fff;
          cursor: pointer;
        `
      });

      const tr = el('tr', {}, [
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [cycleIndexInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [btoInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [btcInput]),
        el('td', { style: 'padding:8px; border-bottom:1px solid #222;' }, [deleteButton])
      ]);

      cyclesBody.appendChild(tr);

      const editor = { tr, cycleIndexInput, btoInput, btcInput };

      deleteButton.addEventListener('click', (e) => {
        e.preventDefault();
        cyclesBody.removeChild(tr);
        const idx = cyclesEditors.indexOf(editor);
        if (idx !== -1) cyclesEditors.splice(idx, 1);
      });

      cyclesEditors.push(editor);
    };

    (details.cycles || []).forEach(addCycleRow);

    const addCycleButton = el('button', {
      textContent: 'Add Cycle Row',
      style: `
        margin-top: 10px;
        width: 100%;
        padding: 10px 12px;
        border-radius: 12px;
        border: 1px solid #3a3a3a;
        background: #2a2a2a;
        color: #fff;
        cursor: pointer;
      `
    });

    let nextCycleRowIndex = Math.max(0, ...(details.cycles || []).map(c => Number(c.cycle_index) || 0)) + 1;
    addCycleButton.addEventListener('click', (e) => {
      e.preventDefault();
      addCycleRow({ cycle_index: nextCycleRowIndex++, bto: '', btc: '' });
    });

    cyclesForm.append(cyclesTable, addCycleButton);
    createSection('cycles', 'Cycles', cyclesForm);

    // -------- Calibration --------
    const calibrationForm = el('div');

    const createVerticalField = (label, value) => {
      const wrapper = el('div', { style: 'display: flex; flex-direction: column; gap: 6px;' });
      const lbl = el('label', { textContent: label, style: 'font-weight: 600; color:#ccc; font-size:0.9rem;' });
      const inp = el('input', { type: 'text', value: value ?? '', ...tableInputProps() });
      wrapper.append(lbl, inp);
      return { wrapper, inp };
    };

    const gridContainer = el('div', {
      style: 'display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 20px;'
    });

    const cal = details.calibration || { channel_name: '', channel_index: '', max_range: '', key_points: [] };
    const nameField = createVerticalField('Channel Name', cal.channel_name);
    const indexField = createVerticalField('Channel Index', cal.channel_index);
    const rangeField = createVerticalField('Max Range', cal.max_range);

    gridContainer.append(nameField.wrapper, indexField.wrapper, rangeField.wrapper);

    const keyPointsHeader = el('h3', { textContent: 'Key Points', style: 'margin: 16px 0 10px;' });
    const keyPointsContainer = el('div', { style: 'display: flex; flex-wrap: wrap; gap: 12px;' });

    const keyPointsInputs = [];
    (cal.key_points || []).forEach(point => {
      const input = el('input', { type: 'text', value: point ?? '', ...tableInputProps() });
      input.style.flex = '1';
      input.style.minWidth = '120px';
      keyPointsContainer.appendChild(input);
      keyPointsInputs.push(input);
    });

    calibrationForm.append(gridContainer, keyPointsHeader, keyPointsContainer);

    calibrationEditor = {
      channelNameInput: nameField.inp,
      channelIndexInput: indexField.inp,
      maxRangeInput: rangeField.inp,
      keyPointsInputs
    };

    createSection('calibration', 'Calibration', calibrationForm);

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
          channel.transducer = editor.transducerInput.value;
          channel.gauge = editor.gaugeInput.value;
          channel.visible = editor.visibleCheckbox.checked;
        }
      });
    }

    // Mass Spec Timings
    if (Array.isArray(detailsJson.mass_spec_timings)) {
      detailsJson.mass_spec_timings.forEach((timing, i) => {
        const editor = massSpecTimingEditors[i];
        if (editor) {
          timing.start = editor.startInput.value;
          timing.stop = editor.stopInput.value;
        }
      });
    }

    // Holds
    detailsJson.holds = holdsEditors.map(editor => ({
      cycle_index: editor.cycleIndexInput.value,
      channel: editor.channelInput.value,
      start_of_stabilisation: editor.startOfStabilisationInput.value,
      start_of_hold: editor.startOfHoldInput.value,
      end_of_hold: editor.endOfHoldInput.value,
      breakout_torque: editor.breakoutTorqueInput.value,
      running_torque: editor.runningTorqueInput.value,
    }));

    // Cycles
    detailsJson.cycles = cyclesEditors.map(editor => ({
      cycle_index: editor.cycleIndexInput.value,
      bto: editor.btoInput.value,
      btc: editor.btcInput.value,
    }));

    // Calibration
    detailsJson.calibration = detailsJson.calibration || {};
    detailsJson.calibration.channel_name = calibrationEditor.channelNameInput?.value ?? '';
    detailsJson.calibration.channel_index = calibrationEditor.channelIndexInput?.value ?? '';
    detailsJson.calibration.max_range = calibrationEditor.maxRangeInput?.value ?? '';
    detailsJson.calibration.key_points = (calibrationEditor.keyPointsInputs || []).map(input => input.value);
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
    const statusEl = byId('pcg-status');
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
          if (statusEl) statusEl.textContent = 'Modified details JSON downloaded. Generating PDF…';
        }

        try {
          const res = await postFilesToServer(rawDataCsvText, detailsText);

          if (!res.ok) {
            const msg = res.networkError
              ? 'Cannot reach the PDF generator. Please make sure the server is running and that you are on the right network.'
              : `The PDF generator returned an error (${res.status} ${res.statusText}).`;

            showErrorDialog('PDF generation failed', msg, (res.errorText || '').slice(0, 2000));
            if (statusEl) statusEl.textContent = msg;
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

          if (statusEl) statusEl.textContent = 'Chart downloaded.';
        } catch (err) {
          console.error(err);
          showErrorDialog('PDF generator unreachable', 'Network or server error while generating the PDF.', err?.message || String(err));
          if (statusEl) statusEl.textContent = 'Network/server error.';
        } finally {
          overlay.classList.add('hidden');
          document.body.style.overflow = prevOverflow;
        }
      });
    }

    // File input change handler
    fileInput.addEventListener('change', async (e) => {
      if (statusEl) statusEl.textContent = '';

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

      if (statusEl) statusEl.textContent = 'Details loaded. Choose a section on the left to edit.';

      // default to Metadata section
      const firstBtn = editorNav.querySelector('button[data-section="metadata"]');
      if (firstBtn) {
        setActiveSidebarButton(firstBtn);
        showSection('metadata');
      }

      fileInput.value = '';
    });

    if (statusEl) statusEl.textContent = 'Ready — click Select Files.';
  }

  // init for standalone page
  document.addEventListener('DOMContentLoaded', initUI);

})();
