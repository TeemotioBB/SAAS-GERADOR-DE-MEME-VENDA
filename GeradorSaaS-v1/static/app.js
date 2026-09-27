(() => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const root = document.querySelector('.dashboard-shell');
  if (!root) return;

  const defaultLogo = root.dataset.defaultLogo === '1';
  const hasLogo = root.dataset.hasLogo === '1';
  const jobsGrid = document.getElementById('jobsGrid');
  const emptyState = document.getElementById('emptyState');
  const importBtn = document.getElementById('importBtn');
  const reelUrls = document.getElementById('reelUrls');
  const importStatus = document.getElementById('importStatus');
  const videoFiles = document.getElementById('videoFiles');
  const uploadStatus = document.getElementById('uploadStatus');
  const dropZone = document.querySelector('.drop-zone');
  const generateAllBtn = document.getElementById('generateAllBtn');
  const downloadZipBtn = document.getElementById('downloadZipBtn');
  const usageCount = document.getElementById('usageCount');
  const usageTrack = document.querySelector('.usage-track span');
  const generationModal = document.getElementById('generationModal');
  const generationModalTitle = document.getElementById('generationModalTitle');
  const generationModalMessage = document.getElementById('generationModalMessage');
  const generationModalStatus = document.getElementById('generationModalStatus');
  const generationModalIcon = document.getElementById('generationModalIcon');
  const generationModalAction = document.getElementById('generationModalAction');
  const workspace = document.getElementById('workspace');

  const jobs = new Map();
  const drafts = new Map();
  let pollTimer = null;
  let generationTrackedIds = new Set();

  function ensureDraft(job) {
    if (!drafts.has(job.id)) {
      drafts.set(job.id, {
        caption: job.last_caption || job.suggested_caption || '',
        crop: job.crop ? {...job.crop} : null,
        useLogo: defaultLogo,
        extraEdits: false,
        mirrorVideo: false,
        removeMetadata: true,
      });
    } else {
      const d = drafts.get(job.id);
      if (!d.caption && !d.touchedCaption && job.suggested_caption) d.caption = job.suggested_caption;
      if (!d.crop && job.crop) d.crop = {...job.crop};
    }
    return drafts.get(job.id);
  }

  async function api(url, options={}) {
    const headers = new Headers(options.headers || {});
    if (!headers.has('X-CSRFToken')) headers.set('X-CSRFToken', csrf);
    const response = await fetch(url, {...options, headers});
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) throw new Error((data && data.error) || data || `Erro HTTP ${response.status}`);
    return data;
  }

  const statusLabel = status => ({
    queued:'Na fila', importing:'Importando', analyzing:'Preparando', ready:'Pronto para gerar',
    rendering:'Gerando', done:'Concluído', error:'Precisa de atenção'
  }[status] || status);

  function escapeHtml(value='') {
    return String(value).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
  }

  function setStatus(element, message='', tone='') {
    if (!element) return;
    element.textContent = message;
    element.classList.remove('success','error','loading');
    if (tone) element.classList.add(tone);
  }

  function notify(message, tone='info') {
    let stack = document.querySelector('.toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'toast-stack';
      stack.setAttribute('aria-live', 'polite');
      document.body.appendChild(stack);
    }
    const toast = document.createElement('div');
    toast.className = `toast ${tone}`;
    toast.textContent = message;
    stack.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 220);
    }, 3600);
  }

  function frameStyle(job) {
    const w = Number(job.width || 0);
    const h = Number(job.height || 0);
    if (!w || !h) return '';
    const maxPreviewHeight = 430;
    const widthAtMaxHeight = maxPreviewHeight * (w / h);
    return `aspect-ratio:${w}/${h};width:min(100%,${widthAtMaxHeight.toFixed(2)}px);`;
  }

  function cropStyle(job, crop) {
    if (!crop || !job.width || !job.height) return '';
    return `left:${crop.x/job.width*100}%;top:${crop.y/job.height*100}%;width:${crop.w/job.width*100}%;height:${crop.h/job.height*100}%;`;
  }

  function updateFlowState(list) {
    const steps = [...document.querySelectorAll('[data-flow-step]')];
    const lines = [...document.querySelectorAll('.flow-line')];
    steps.forEach(s => s.classList.remove('active','complete'));
    lines.forEach(l => l.classList.remove('complete'));

    if (!list.length) {
      steps[0]?.classList.add('active');
      return;
    }

    steps[0]?.classList.add('complete');
    lines[0]?.classList.add('complete');

    const anyGenerating = list.some(j => ['queued','rendering'].includes(j.status));
    const anyDone = list.some(j => j.status === 'done');
    const allFinished = list.length > 0 && list.every(j => ['done','error'].includes(j.status));

    if (anyGenerating || anyDone) {
      steps[1]?.classList.add('complete');
      lines[1]?.classList.add('complete');
      if (allFinished && !list.some(j => j.status === 'error')) steps[2]?.classList.add('complete');
      else steps[2]?.classList.add('active');
    } else {
      steps[1]?.classList.add('active');
    }
  }

  function renderJobs() {
    const list = [...jobs.values()].sort((a,b) => (b.created_at || '').localeCompare(a.created_at || ''));
    jobsGrid.innerHTML = '';
    emptyState.classList.toggle('hidden', list.length > 0);
    root.classList.toggle('has-jobs', list.length > 0);
    updateFlowState(list);

    list.forEach((job, index) => {
      const d = ensureDraft(job);
      const card = document.createElement('article');
      card.className = 'job-card';
      card.dataset.jobId = job.id;
      const canEdit = ['ready','done','error'].includes(job.status) && !!job.has_frame;
      const canRender = canEdit;
      const hasResult = !!job.has_result;
      const isWorking = ['queued','importing','analyzing','rendering'].includes(job.status);

      card.innerHTML = `
        <div class="job-head">
          <div class="job-title-wrap">
            <span class="job-number">${String(index + 1).padStart(2,'0')}</span>
            <div class="job-name" title="${escapeHtml(job.original_name)}">${escapeHtml(job.original_name)}</div>
          </div>
          <span class="status-chip ${escapeHtml(job.status)}">${escapeHtml(statusLabel(job.status))}</span>
        </div>
        <div class="job-body">
          <div class="job-media-column">
            <span class="media-label">${hasResult ? 'Recorte detectado' : 'Prévia e recorte'}</span>
            ${job.has_frame ? `
              <div class="frame-wrap" style="${frameStyle(job)}">
                <img src="/api/jobs/${job.id}/frame?v=${encodeURIComponent(job.updated_at || '')}" alt="Frame do vídeo">
                ${d.crop && job.width && job.height ? `<div class="crop-box" style="${cropStyle(job,d.crop)}"><div class="crop-handle"></div></div>` : ''}
                <span class="confidence">Recorte ${Math.round((job.confidence || 0)*100)}%</span>
              </div>` : `<div class="frame-wrap placeholder-wrap"><div class="frame-placeholder">${job.status === 'error' ? 'Não foi possível preparar este vídeo.' : 'Preparando o vídeo…'}</div></div>`}
            ${hasResult ? `<div class="result-block"><span class="media-label">Resultado gerado</span><video class="result-preview" controls preload="metadata" src="/api/jobs/${job.id}/preview?v=${encodeURIComponent(`${job.generation_count || 0}-${job.updated_at || ''}`)}"></video></div>` : ''}
          </div>

          <div class="job-controls-column">
            ${job.error ? `<div class="job-error">${escapeHtml(job.error)}</div>` : ''}

            <div class="editor-block">
              <div class="editor-block-head">
                <div class="editor-block-title"><strong>Chamada do vídeo</strong><small>Opcional — pode gerar sem texto.</small></div>
                <button class="text-button reread" type="button" ${job.has_frame?'':'disabled'}>${isWorking ? 'Aguardando…' : 'Reler texto'}</button>
              </div>
              <textarea class="job-caption" placeholder="Escreva a chamada ou deixe vazio" ${canEdit?'':'disabled'}>${escapeHtml(d.caption)}</textarea>
            </div>

            <div class="editor-block">
              <div class="editor-block-head">
                <div class="editor-block-title"><strong>Opções de geração</strong><small>Ajustes independentes para este vídeo.</small></div>
              </div>
              <div class="job-options">
                <label class="option-toggle" title="Remove tags e metadados embutidos do MP4 final">
                  <input class="metadata-check" type="checkbox" ${d.removeMetadata?'checked':''}>
                  <span class="option-copy"><span>Remover metadados</span><small>Recomendado</small></span>
                </label>
                <label class="option-toggle" title="Aplica pequenas variações visuais: cor, grão, vinheta, zoom, crop leve e velocidade">
                  <input class="extras-check" type="checkbox" ${d.extraEdits?'checked':''}>
                  <span class="option-copy"><span>Edições extras</span><small>Cor, grão, zoom e mais</small></span>
                </label>
                <label class="option-toggle option-warning" title="Espelha somente o vídeo. Evite ativar quando houver texto visível dentro do vídeo">
                  <input class="mirror-check" type="checkbox" ${d.mirrorVideo?'checked':''}>
                  <span class="option-copy"><span>Espelhar vídeo</span><small>Cuidado com textos na imagem</small></span>
                </label>
                ${hasLogo ? `<label class="option-toggle"><input class="logo-check" type="checkbox" ${d.useLogo?'checked':''}><span class="option-copy"><span>Adicionar logo</span><small>Usa a logo da sua página</small></span></label>` : ''}
              </div>
              <div class="option-hint">O espelhamento é separado das edições extras para não inverter textos que já existem dentro do vídeo.</div>
            </div>

            <div class="job-toolbar">
              <button class="icon-btn danger delete-one" type="button">Excluir</button>
              <span class="spacer"></span>
              ${hasResult ? `<a class="icon-btn download-btn" href="/api/jobs/${job.id}/download?v=${encodeURIComponent(`${job.generation_count || 0}-${job.updated_at || ''}`)}">Baixar vídeo</a>` : ''}
              <button class="secondary generate-one" type="button" ${canRender?'':'disabled'}>${job.status === 'done' ? 'Gerar novamente' : isWorking ? 'Preparando…' : 'Gerar vídeo'}</button>
            </div>
          </div>
        </div>`;
      jobsGrid.appendChild(card);
      wireCard(card, job, d);
    });
  }

  function wireCard(card, job, draft) {
    const textarea = card.querySelector('.job-caption');
    textarea?.addEventListener('input', e => {
      draft.caption = e.target.value;
      draft.touchedCaption = true;
      const btn = card.querySelector('.generate-one');
      if (btn) btn.disabled = !['ready','done','error'].includes(job.status);
    });
    card.querySelector('.logo-check')?.addEventListener('change', e => draft.useLogo = e.target.checked);
    card.querySelector('.extras-check')?.addEventListener('change', e => draft.extraEdits = e.target.checked);
    card.querySelector('.mirror-check')?.addEventListener('change', e => draft.mirrorVideo = e.target.checked);
    card.querySelector('.metadata-check')?.addEventListener('change', e => draft.removeMetadata = e.target.checked);
    card.querySelector('.reread')?.addEventListener('click', () => reread(job.id));
    card.querySelector('.generate-one')?.addEventListener('click', () => generate(job.id));
    card.querySelector('.delete-one')?.addEventListener('click', () => removeJob(job.id));
    setupCrop(card, job, draft);
  }

  function setupCrop(card, job, draft) {
    const wrap = card.querySelector('.frame-wrap');
    const box = card.querySelector('.crop-box');
    const handle = card.querySelector('.crop-handle');
    if (!wrap || !box || !draft.crop || !job.width || !job.height) return;

    const begin = (event, resize=false) => {
      event.preventDefault();
      const startRect = wrap.getBoundingClientRect();
      const startX = event.clientX, startY = event.clientY;
      const start = {...draft.crop};
      const pointerId = event.pointerId;
      (resize ? handle : box).setPointerCapture?.(pointerId);

      const move = e => {
        const rect = wrap.getBoundingClientRect();
        const scaleW = rect.width || startRect.width || 1;
        const scaleH = rect.height || startRect.height || 1;
        const dx = (e.clientX - startX) / scaleW * job.width;
        const dy = (e.clientY - startY) / scaleH * job.height;
        if (resize) {
          draft.crop.w = Math.max(40, Math.min(job.width - start.x, start.w + dx));
          draft.crop.h = Math.max(40, Math.min(job.height - start.y, start.h + dy));
        } else {
          draft.crop.x = Math.max(0, Math.min(job.width - start.w, start.x + dx));
          draft.crop.y = Math.max(0, Math.min(job.height - start.h, start.y + dy));
        }
        box.style.cssText = cropStyle(job, draft.crop);
      };
      const end = () => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', end);
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', end, {once:true});
    };
    box.addEventListener('pointerdown', e => { if (e.target !== handle) begin(e,false); });
    handle?.addEventListener('pointerdown', e => begin(e,true));
  }

  async function refreshVisibleJobs() {
    const ids = [...jobs.keys()];
    if (!ids.length) {
      clearTimeout(pollTimer);
      renderJobs();
      refreshUsage();
      return;
    }

    try {
      const results = await Promise.allSettled(ids.map(id => api(`/api/jobs/${id}`)));
      results.forEach((result, index) => {
        if (result.status === 'fulfilled') jobs.set(ids[index], result.value);
        else console.warn(`Falha ao atualizar job ${ids[index]}:`, result.reason);
      });
      renderJobs();
      updateGenerationModal();
      const active = [...jobs.values()].some(j => ['queued','importing','analyzing','rendering'].includes(j.status));
      if (active) schedulePoll(2200); else clearTimeout(pollTimer);
      refreshUsage();
    } catch (e) {
      console.error(e);
      schedulePoll(5000);
    }
  }

  function schedulePoll(ms=2500) {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(refreshVisibleJobs, ms);
  }

  function showGenerationModal(ids) {
    generationTrackedIds = new Set(ids);
    if (!generationModal) return;
    const count = ids.length;
    generationModal.classList.add('is-open');
    generationModal.setAttribute('aria-hidden', 'false');
    generationModal.classList.remove('is-done', 'is-error');
    if (generationModalTitle) generationModalTitle.textContent = count > 1 ? `Gerando ${count} vídeos…` : 'Gerando vídeo…';
    if (generationModalMessage) generationModalMessage.textContent = count > 1
      ? 'Os vídeos foram enviados para processamento. Você pode continuar usando a página enquanto eles são preparados.'
      : 'Seu vídeo foi enviado para processamento. Você pode continuar usando a página enquanto ele é preparado.';
    if (generationModalStatus) generationModalStatus.textContent = 'Iniciando processamento…';
    if (generationModalAction) generationModalAction.textContent = 'Continuar usando';
    if (generationModalIcon) generationModalIcon.innerHTML = '<span class="generation-spinner"></span>';
  }

  function setGenerationModalError(message) {
    if (!generationModal) return;
    generationModal.classList.add('is-open', 'is-error');
    generationModal.classList.remove('is-done');
    generationModal.setAttribute('aria-hidden', 'false');
    if (generationModalTitle) generationModalTitle.textContent = 'Não foi possível iniciar a geração';
    if (generationModalMessage) generationModalMessage.textContent = message || 'Ocorreu um erro ao enviar o vídeo para processamento.';
    if (generationModalStatus) generationModalStatus.textContent = 'Revise as informações e tente novamente.';
    if (generationModalAction) generationModalAction.textContent = 'Fechar';
    if (generationModalIcon) generationModalIcon.textContent = '!';
  }

  function updateGenerationModal() {
    if (!generationModal?.classList.contains('is-open') || !generationTrackedIds.size) return;
    const tracked = [...generationTrackedIds].map(id => jobs.get(id)).filter(Boolean);
    if (!tracked.length) return;

    const done = tracked.filter(j => j.status === 'done').length;
    const errors = tracked.filter(j => j.status === 'error').length;
    const rendering = tracked.filter(j => ['queued','rendering'].includes(j.status)).length;

    if (done === tracked.length) {
      generationModal.classList.add('is-done');
      generationModal.classList.remove('is-error');
      if (generationModalTitle) generationModalTitle.textContent = tracked.length > 1 ? 'Vídeos prontos!' : 'Vídeo pronto!';
      if (generationModalMessage) generationModalMessage.textContent = tracked.length > 1
        ? 'As gerações foram concluídas. Os botões de download já estão disponíveis.'
        : 'A geração foi concluída. Seu vídeo já está disponível para baixar.';
      if (generationModalStatus) generationModalStatus.textContent = `${done}/${tracked.length} concluído${tracked.length > 1 ? 's' : ''}.`;
      if (generationModalAction) generationModalAction.textContent = 'Ver resultado';
      if (generationModalIcon) generationModalIcon.textContent = '✓';
      return;
    }

    if (errors && done + errors === tracked.length) {
      generationModal.classList.add('is-error');
      generationModal.classList.remove('is-done');
      if (generationModalTitle) generationModalTitle.textContent = 'Geração finalizada com erro';
      if (generationModalMessage) generationModalMessage.textContent = tracked.length > 1
        ? `${errors} vídeo(s) apresentaram erro. Confira os cartões para ver os detalhes.`
        : 'O vídeo apresentou um erro durante a geração. Confira o cartão para ver os detalhes.';
      if (generationModalStatus) generationModalStatus.textContent = `${done} concluído(s), ${errors} com erro.`;
      if (generationModalAction) generationModalAction.textContent = 'Fechar';
      if (generationModalIcon) generationModalIcon.textContent = '!';
      return;
    }

    if (generationModalStatus) {
      const current = done + errors;
      generationModalStatus.textContent = tracked.length > 1
        ? `${current}/${tracked.length} finalizado(s) · ${rendering} em processamento.`
        : 'Processando o vídeo…';
    }
  }

  function hideGenerationModal() {
    if (!generationModal) return;
    const done = generationModal.classList.contains('is-done');
    generationModal.classList.remove('is-open');
    generationModal.setAttribute('aria-hidden', 'true');
    if (done) workspace?.scrollIntoView({behavior:'smooth', block:'start'});
  }

  generationModal?.querySelectorAll('[data-close-generation-modal]').forEach(el => el.addEventListener('click', hideGenerationModal));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') hideGenerationModal(); });

  async function refreshUsage() {
    try {
      const data = await api('/api/usage');
      if (usageCount) usageCount.textContent = `${data.used} / ${data.limit}`;
      if (usageTrack) {
        const percent = data.limit ? Math.min(100, Math.max(0, data.used / data.limit * 100)) : 0;
        usageTrack.style.width = `${percent}%`;
      }
    } catch (_) {}
  }

  // Alterna entre link e upload sem mostrar dois caminhos ao mesmo tempo.
  document.querySelectorAll('[data-source-tab]').forEach(tab => {
    tab.addEventListener('click', () => {
      const name = tab.dataset.sourceTab;
      document.querySelectorAll('[data-source-tab]').forEach(btn => {
        const active = btn === tab;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-selected', active ? 'true' : 'false');
      });
      document.querySelectorAll('[data-source-pane]').forEach(pane => {
        const active = pane.dataset.sourcePane === name;
        pane.classList.toggle('active', active);
        pane.hidden = !active;
      });
      if (name === 'link') setTimeout(() => reelUrls?.focus(), 30);
    });
  });

  function scrollToWorkspaceAfterAdd() {
    setTimeout(() => workspace?.scrollIntoView({behavior:'smooth', block:'start'}), 160);
  }

  importBtn?.addEventListener('click', async () => {
    const urls = reelUrls.value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
    if (!urls.length) { setStatus(importStatus, 'Cole pelo menos um link para continuar.', 'error'); reelUrls.focus(); return; }
    importBtn.disabled = true;
    importBtn.querySelector('span').textContent = urls.length > 1 ? 'Importando vídeos…' : 'Importando vídeo…';
    setStatus(importStatus, 'Adicionando à fila…', 'loading');
    try {
      const data = await api('/api/jobs/import', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({urls})});
      data.jobs.forEach(j => jobs.set(j.id,j));
      renderJobs();
      schedulePoll(1200);
      if (data.errors?.length) setStatus(importStatus, `${data.jobs.length} adicionado(s) · ${data.errors.length} link(s) não puderam ser usados.`, 'error');
      else setStatus(importStatus, `${data.jobs.length} vídeo(s) adicionado(s). Preparando análise…`, 'success');
      reelUrls.value = '';
      scrollToWorkspaceAfterAdd();
    } catch(e) {
      setStatus(importStatus, e.message, 'error');
    } finally {
      importBtn.disabled = false;
      importBtn.querySelector('span').textContent = 'Importar vídeos';
    }
  });

  async function uploadFiles(files) {
    const fileList = [...files];
    if (!fileList.length) return;
    let ok = 0;
    setStatus(uploadStatus, `Enviando 1 de ${fileList.length}…`, 'loading');
    for (let i=0; i<fileList.length; i++) {
      setStatus(uploadStatus, `Enviando ${i+1} de ${fileList.length}: ${fileList[i].name}`, 'loading');
      const fd = new FormData();
      fd.append('video', fileList[i]);
      try {
        const job = await api('/api/jobs/upload', {method:'POST', body:fd});
        jobs.set(job.id,job);
        ok++;
        renderJobs();
      } catch(e) {
        setStatus(uploadStatus, `Falha em ${fileList[i].name}: ${e.message}`, 'error');
      }
    }
    if (ok === fileList.length) setStatus(uploadStatus, `${ok} vídeo(s) enviado(s). Preparando análise…`, 'success');
    else if (ok) setStatus(uploadStatus, `${ok} de ${fileList.length} vídeo(s) enviados.`, 'error');
    schedulePoll(1200);
    if (ok) scrollToWorkspaceAfterAdd();
  }

  videoFiles?.addEventListener('change', async () => {
    await uploadFiles(videoFiles.files);
    videoFiles.value='';
  });

  ['dragenter','dragover'].forEach(name => dropZone?.addEventListener(name, e => { e.preventDefault(); dropZone.classList.add('drag-over'); }));
  ['dragleave','drop'].forEach(name => dropZone?.addEventListener(name, e => { e.preventDefault(); dropZone.classList.remove('drag-over'); }));
  dropZone?.addEventListener('drop', async e => { if (e.dataTransfer?.files?.length) await uploadFiles(e.dataTransfer.files); });

  async function reread(id) {
    const card = jobsGrid.querySelector(`[data-job-id="${id}"]`);
    const btn = card?.querySelector('.reread');
    if (btn) { btn.disabled=true; btn.textContent='Lendo…'; }
    try {
      const data = await api(`/api/jobs/${id}/caption`, {method:'POST'});
      const d = ensureDraft(jobs.get(id));
      d.caption = data.text || '';
      d.touchedCaption = true;
      renderJobs();
      notify(data.text ? 'Chamada atualizada.' : 'Nenhum texto foi encontrado no frame.', data.text ? 'success' : 'info');
    } catch(e) {
      notify(e.message, 'error');
      if(btn){btn.disabled=false;btn.textContent='Reler texto';}
    }
  }

  async function generate(id, showNotice=true) {
    const job = jobs.get(id), d = ensureDraft(job);
    if (showNotice) showGenerationModal([id]);
    try {
      const data = await api(`/api/jobs/${id}/render`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          caption:d.caption,
          crop:d.crop,
          use_logo:d.useLogo,
          extra_edits:d.extraEdits,
          mirror_video:d.mirrorVideo,
          remove_metadata:d.removeMetadata
        })
      });
      jobs.set(id,data.job);
      renderJobs();
      updateGenerationModal();
      schedulePoll(1200);
      return true;
    } catch(e) {
      setGenerationModalError(e.message);
      return false;
    }
  }

  generateAllBtn?.addEventListener('click', async () => {
    const targets = [...jobs.values()].filter(j => j.status === 'ready');
    if (!targets.length) return notify('Não há vídeos prontos para gerar.', 'info');
    showGenerationModal(targets.map(j => j.id));
    generateAllBtn.disabled=true;
    let failed = 0;
    const originalText = generateAllBtn.textContent;
    for (let i=0;i<targets.length;i++) {
      generateAllBtn.textContent=`Enfileirando ${i+1}/${targets.length}`;
      const ok = await generate(targets[i].id, false);
      if (!ok) failed++;
    }
    generateAllBtn.textContent=originalText;
    generateAllBtn.disabled=false;
    if (!failed) updateGenerationModal();
    schedulePoll(1000);
  });

  downloadZipBtn?.addEventListener('click', async () => {
    const ids = [...jobs.values()].filter(j=>j.has_result).map(j=>j.id);
    if (!ids.length) return notify('Gere pelo menos um vídeo antes de baixar o ZIP.', 'info');
    downloadZipBtn.disabled=true;
    const originalText = downloadZipBtn.textContent;
    downloadZipBtn.textContent = 'Preparando ZIP…';
    try {
      const response = await fetch('/api/jobs/zip',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({ids})});
      if (!response.ok) { const d=await response.json().catch(()=>({})); throw new Error(d.error||'Falha ao criar ZIP.'); }
      const blob=await response.blob(), url=URL.createObjectURL(blob), a=document.createElement('a');
      a.href=url;a.download='videos.zip';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2000);
      notify('ZIP pronto para download.', 'success');
    } catch(e){
      notify(e.message, 'error');
    } finally {
      downloadZipBtn.disabled=false;
      downloadZipBtn.textContent=originalText;
    }
  });

  async function removeJob(id) {
    if (!confirm('Excluir este vídeo desta sessão e remover seus arquivos?')) return;
    try {
      await api(`/api/jobs/${id}`,{method:'DELETE'});
      jobs.delete(id);
      drafts.delete(id);
      renderJobs();
      notify('Vídeo excluído.', 'success');
    } catch(e){
      notify(e.message, 'error');
    }
  }

  // A área de trabalho é intencionalmente efêmera. Não carregamos jobs antigos
  // ao abrir/recarregar a página; apenas os vídeos adicionados nesta sessão aparecem.
  renderJobs();
  refreshUsage();
})();
