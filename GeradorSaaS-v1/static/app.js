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
  const generateAllBtn = document.getElementById('generateAllBtn');
  const downloadZipBtn = document.getElementById('downloadZipBtn');
  const usageCount = document.getElementById('usageCount');
  const generationModal = document.getElementById('generationModal');
  const generationModalTitle = document.getElementById('generationModalTitle');
  const generationModalMessage = document.getElementById('generationModalMessage');
  const generationModalStatus = document.getElementById('generationModalStatus');
  const generationModalIcon = document.getElementById('generationModalIcon');
  const generationModalAction = document.getElementById('generationModalAction');

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
    queued:'Na fila', importing:'Importando', analyzing:'Analisando', ready:'Pronto',
    rendering:'Gerando', done:'Concluído', error:'Erro'
  }[status] || status);

  function escapeHtml(value='') {
    return String(value).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
  }

  function frameStyle(job) {
    const w = Number(job.width || 0);
    const h = Number(job.height || 0);
    if (!w || !h) return '';

    // IMPORTANTE: o elemento que recebe a caixa de recorte precisa ter
    // exatamente a mesma proporção do frame analisado. Na primeira versão
    // SaaS a caixa era posicionada contra o card inteiro; em vídeos verticais
    // isso criava barras laterais e deslocava visualmente o crop.
    const maxPreviewHeight = 430;
    const widthAtMaxHeight = maxPreviewHeight * (w / h);
    return `aspect-ratio:${w}/${h};width:min(100%,${widthAtMaxHeight.toFixed(2)}px);`;
  }

  function cropStyle(job, crop) {
    if (!crop || !job.width || !job.height) return '';
    return `left:${crop.x/job.width*100}%;top:${crop.y/job.height*100}%;width:${crop.w/job.width*100}%;height:${crop.h/job.height*100}%;`;
  }

  function renderJobs() {
    const list = [...jobs.values()].sort((a,b) => (b.created_at || '').localeCompare(a.created_at || ''));
    jobsGrid.innerHTML = '';
    emptyState.classList.toggle('hidden', list.length > 0);

    list.forEach(job => {
      const d = ensureDraft(job);
      const card = document.createElement('article');
      card.className = 'job-card';
      card.dataset.jobId = job.id;
      const canEdit = ['ready','done','error'].includes(job.status) && !!job.has_frame;
      const canRender = canEdit;
      const hasResult = !!job.has_result;

      card.innerHTML = `
        <div class="job-head">
          <div class="job-name" title="${escapeHtml(job.original_name)}">${escapeHtml(job.original_name)}</div>
          <span class="status-chip ${escapeHtml(job.status)}">${escapeHtml(statusLabel(job.status))}</span>
        </div>
        <div class="job-body">
          ${job.has_frame ? `
            <div class="frame-wrap" style="${frameStyle(job)}">
              <img src="/api/jobs/${job.id}/frame?v=${encodeURIComponent(job.updated_at || '')}" alt="Frame">
              ${d.crop && job.width && job.height ? `<div class="crop-box" style="${cropStyle(job,d.crop)}"><div class="crop-handle"></div></div>` : ''}
              <span class="confidence">recorte ${Math.round((job.confidence || 0)*100)}%</span>
            </div>` : `<div class="frame-wrap placeholder-wrap"><div class="frame-placeholder">${job.status === 'error' ? 'Não foi possível preparar este vídeo.' : 'Preparando vídeo…'}</div></div>`}
          ${job.error ? `<div class="job-error">${escapeHtml(job.error)}</div>` : ''}
          ${hasResult ? `<video class="result-preview" controls preload="metadata" src="/api/jobs/${job.id}/preview?v=${encodeURIComponent(`${job.generation_count || 0}-${job.updated_at || ''}`)}"></video>` : ''}
          <textarea class="job-caption" placeholder="Chamada do vídeo (opcional)" ${canEdit?'':'disabled'}>${escapeHtml(d.caption)}</textarea>
          <div class="job-options">
            <label class="option-toggle" title="Remove tags e metadados embutidos do MP4 final">
              <input class="metadata-check" type="checkbox" ${d.removeMetadata?'checked':''}>
              <span>🧹 Remover metadados</span>
            </label>
            <label class="option-toggle" title="Aplica pequenas variações visuais: cor, grão, vinheta, zoom, crop leve e velocidade">
              <input class="extras-check" type="checkbox" ${d.extraEdits?'checked':''}>
              <span>✨ Edições extras</span>
            </label>
            <label class="option-toggle" title="Espelha somente o vídeo. Evite ativar quando houver texto visível dentro do vídeo">
              <input class="mirror-check" type="checkbox" ${d.mirrorVideo?'checked':''}>
              <span>↔️ Espelhar vídeo</span>
            </label>
            ${hasLogo ? `<label class="option-toggle"><input class="logo-check" type="checkbox" ${d.useLogo?'checked':''}><span>🏷️ Logo</span></label>` : ''}
          </div>
          <div class="option-hint">Edições extras: cor, grão, vinheta, zoom, crop leve e pequena variação de velocidade. O espelhamento é separado para não inverter textos do vídeo.</div>
          <div class="job-toolbar">
            <button class="icon-btn reread" type="button" ${job.has_frame?'':'disabled'}>Reler texto</button>
            <span class="spacer"></span>
            ${hasResult ? `<a class="icon-btn" href="/api/jobs/${job.id}/download?v=${encodeURIComponent(`${job.generation_count || 0}-${job.updated_at || ''}`)}">Baixar</a>` : ''}
            <button class="secondary generate-one" type="button" ${canRender?'':'disabled'}>${job.status === 'done' ? 'Gerar novamente' : 'Gerar vídeo'}</button>
            <button class="icon-btn danger delete-one" type="button">Excluir</button>
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
        // Usa a dimensão real exibida do frame. Isso evita diferença entre desktop,
        // celular, zoom do navegador e cards responsivos.
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
        ? 'As gerações foram concluídas. Os botões de download já estão disponíveis nos vídeos.'
        : 'A geração foi concluída. O botão de download já está disponível no vídeo.';
      if (generationModalStatus) generationModalStatus.textContent = `${done}/${tracked.length} concluído${tracked.length > 1 ? 's' : ''}.`;
      if (generationModalAction) generationModalAction.textContent = 'Fechar';
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
    generationModal.classList.remove('is-open');
    generationModal.setAttribute('aria-hidden', 'true');
  }

  generationModal?.querySelectorAll('[data-close-generation-modal]').forEach(el => el.addEventListener('click', hideGenerationModal));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') hideGenerationModal(); });

  async function refreshUsage() {
    try {
      const data = await api('/api/usage');
      if (usageCount) usageCount.textContent = `${data.used} / ${data.limit}`;
    } catch (_) {}
  }

  importBtn?.addEventListener('click', async () => {
    const urls = reelUrls.value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
    if (!urls.length) { importStatus.textContent = 'Cole pelo menos um link.'; return; }
    importBtn.disabled = true; importStatus.textContent = 'Adicionando à fila…';
    try {
      const data = await api('/api/jobs/import', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({urls})});
      data.jobs.forEach(j => jobs.set(j.id,j));
      renderJobs(); schedulePoll(1200);
      importStatus.textContent = data.errors?.length ? `${data.jobs.length} adicionados; ${data.errors.length} link(s) inválido(s).` : `${data.jobs.length} vídeo(s) adicionados.`;
      reelUrls.value = '';
    } catch(e) { importStatus.textContent = e.message; }
    finally { importBtn.disabled = false; }
  });

  videoFiles?.addEventListener('change', async () => {
    const files = [...videoFiles.files];
    if (!files.length) return;
    let ok=0;
    for (let i=0;i<files.length;i++) {
      uploadStatus.textContent = `Enviando ${i+1}/${files.length}…`;
      const fd = new FormData(); fd.append('video', files[i]);
      try {
        const job = await api('/api/jobs/upload', {method:'POST', body:fd});
        jobs.set(job.id,job); ok++; renderJobs();
      } catch(e) { uploadStatus.textContent = `Falha em ${files[i].name}: ${e.message}`; }
    }
    if (ok === files.length) uploadStatus.textContent = `${ok} vídeo(s) enviados.`;
    videoFiles.value=''; schedulePoll(1200);
  });

  async function reread(id) {
    const card = jobsGrid.querySelector(`[data-job-id="${id}"]`);
    const btn = card?.querySelector('.reread');
    if (btn) { btn.disabled=true; btn.textContent='Lendo…'; }
    try {
      const data = await api(`/api/jobs/${id}/caption`, {method:'POST'});
      const d = ensureDraft(jobs.get(id)); d.caption = data.text || ''; d.touchedCaption = true;
      renderJobs();
    } catch(e) { alert(e.message); if(btn){btn.disabled=false;btn.textContent='Reler texto';} }
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
    if (!targets.length) return alert('Não há vídeos prontos para gerar.');
    showGenerationModal(targets.map(j => j.id));
    generateAllBtn.disabled=true;
    let failed = 0;
    for (let i=0;i<targets.length;i++) {
      generateAllBtn.textContent=`Enfileirando ${i+1}/${targets.length}…`;
      const ok = await generate(targets[i].id, false);
      if (!ok) failed++;
    }
    generateAllBtn.textContent='Gerar todos prontos';
    generateAllBtn.disabled=false;
    if (!failed) updateGenerationModal();
    schedulePoll(1000);
  });

  downloadZipBtn?.addEventListener('click', async () => {
    const ids = [...jobs.values()].filter(j=>j.has_result).map(j=>j.id);
    if (!ids.length) return alert('Nenhum vídeo gerado para baixar.');
    downloadZipBtn.disabled=true;
    try {
      const response = await fetch('/api/jobs/zip',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({ids})});
      if (!response.ok) { const d=await response.json().catch(()=>({})); throw new Error(d.error||'Falha ao criar ZIP.'); }
      const blob=await response.blob(), url=URL.createObjectURL(blob), a=document.createElement('a');
      a.href=url;a.download='videos.zip';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2000);
    } catch(e){alert(e.message)} finally {downloadZipBtn.disabled=false;}
  });

  async function removeJob(id) {
    if (!confirm('Excluir este vídeo e seus arquivos?')) return;
    try { await api(`/api/jobs/${id}`,{method:'DELETE'}); jobs.delete(id); drafts.delete(id); renderJobs(); }
    catch(e){ alert(e.message); }
  }

  // A área de trabalho é intencionalmente efêmera. Não carregamos jobs antigos
  // ao abrir/recarregar a página; apenas os vídeos adicionados nesta sessão da tela
  // aparecem no grid. O backend mantém os jobs para fila, cota e limpeza.
  renderJobs();
  refreshUsage();
})();
