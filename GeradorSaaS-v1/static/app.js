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

  const jobs = new Map();
  const drafts = new Map();
  let pollTimer = null;

  function ensureDraft(job) {
    if (!drafts.has(job.id)) {
      drafts.set(job.id, {
        caption: job.last_caption || job.suggested_caption || '',
        crop: job.crop ? {...job.crop} : null,
        useLogo: defaultLogo,
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
      const canRender = canEdit && !!d.caption.trim();
      const hasResult = !!job.has_result;

      card.innerHTML = `
        <div class="job-head">
          <div class="job-name" title="${escapeHtml(job.original_name)}">${escapeHtml(job.original_name)}</div>
          <span class="status-chip ${escapeHtml(job.status)}">${escapeHtml(statusLabel(job.status))}</span>
        </div>
        <div class="job-body">
          ${job.has_frame ? `
            <div class="frame-wrap">
              <img src="/api/jobs/${job.id}/frame?v=${encodeURIComponent(job.updated_at || '')}" alt="Frame">
              ${d.crop && job.width && job.height ? `<div class="crop-box" style="${cropStyle(job,d.crop)}"><div class="crop-handle"></div></div>` : ''}
              <span class="confidence">recorte ${Math.round((job.confidence || 0)*100)}%</span>
            </div>` : `<div class="frame-wrap"><div class="frame-placeholder">${job.status === 'error' ? 'Não foi possível preparar este vídeo.' : 'Preparando vídeo…'}</div></div>`}
          ${job.error ? `<div class="job-error">${escapeHtml(job.error)}</div>` : ''}
          ${hasResult ? `<video class="result-preview" controls preload="metadata" src="/api/jobs/${job.id}/preview"></video>` : ''}
          <textarea class="job-caption" placeholder="Digite a chamada do vídeo" ${canEdit?'':'disabled'}>${escapeHtml(d.caption)}</textarea>
          <div class="job-toolbar">
            <button class="icon-btn reread" type="button" ${job.has_frame?'':'disabled'}>Reler texto</button>
            ${hasLogo ? `<label class="check-row logo-toggle"><input class="logo-check" type="checkbox" ${d.useLogo?'checked':''}><span>Logo</span></label>` : ''}
            <span class="spacer"></span>
            ${hasResult ? `<a class="icon-btn" href="/api/jobs/${job.id}/download">Baixar</a>` : ''}
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
      if (btn) btn.disabled = !draft.caption.trim() || !['ready','done','error'].includes(job.status);
    });
    card.querySelector('.logo-check')?.addEventListener('change', e => draft.useLogo = e.target.checked);
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
      const rect = wrap.getBoundingClientRect();
      const startX = event.clientX, startY = event.clientY;
      const start = {...draft.crop};
      const pointerId = event.pointerId;
      (resize ? handle : box).setPointerCapture?.(pointerId);

      const move = e => {
        const dx = (e.clientX - startX) / rect.width * job.width;
        const dy = (e.clientY - startY) / rect.height * job.height;
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

  async function refreshJobs() {
    try {
      const data = await api('/api/jobs');
      data.jobs.forEach(j => jobs.set(j.id,j));
      for (const id of [...jobs.keys()]) if (!data.jobs.find(j => j.id === id)) jobs.delete(id);
      renderJobs();
      const active = data.jobs.some(j => ['queued','importing','analyzing','rendering'].includes(j.status));
      if (active) schedulePoll(2200); else clearTimeout(pollTimer);
      refreshUsage();
    } catch (e) {
      console.error(e);
      schedulePoll(5000);
    }
  }

  function schedulePoll(ms=2500) {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(refreshJobs, ms);
  }

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

  async function generate(id) {
    const job = jobs.get(id), d = ensureDraft(job);
    if (!d.caption.trim()) return alert('Digite a legenda/chamada.');
    try {
      const data = await api(`/api/jobs/${id}/render`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({caption:d.caption,crop:d.crop,use_logo:d.useLogo})});
      jobs.set(id,data.job); renderJobs(); schedulePoll(1200);
    } catch(e) { alert(e.message); }
  }

  generateAllBtn?.addEventListener('click', async () => {
    const targets = [...jobs.values()].filter(j => j.status === 'ready' && ensureDraft(j).caption.trim());
    if (!targets.length) return alert('Não há vídeos prontos com legenda para gerar.');
    generateAllBtn.disabled=true;
    for (let i=0;i<targets.length;i++) {
      generateAllBtn.textContent=`Enfileirando ${i+1}/${targets.length}…`;
      try { await generate(targets[i].id); } catch(_) {}
    }
    generateAllBtn.textContent='Gerar todos prontos'; generateAllBtn.disabled=false; schedulePoll(1000);
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

  refreshJobs();
})();
