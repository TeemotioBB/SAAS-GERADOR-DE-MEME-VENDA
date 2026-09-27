# Correção v1.5 — fluxo temporário e aviso de geração

## Mudanças

- O painel não busca mais automaticamente os jobs antigos ao abrir ou atualizar a página.
- Os vídeos adicionados continuam visíveis enquanto a página atual permanece aberta.
- Ao atualizar/recarregar a página, o grid volta vazio.
- Jobs/processamentos já enviados continuam existindo no backend; apenas deixam de ser mostrados naquela nova sessão visual.
- O polling consulta somente os jobs adicionados na sessão atual da tela.
- Foram adicionadas 3 etapas visuais: adicionar, revisar e gerar.
- Ao clicar em **Gerar vídeo** ou **Gerar todos prontos**, abre uma janela informando que a geração começou.
- Se a janela ficar aberta, ela muda para **Vídeo pronto!** quando o worker conclui, ou informa erro quando necessário.
- A janela pode ser fechada imediatamente com **Continuar usando**; a geração segue normalmente no worker.

## Arquivos alterados

- `static/app.js`
- `static/styles.css`
- `templates/base.html`
- `templates/dashboard.html`

Nenhuma alteração foi feita no detector, crop, FFmpeg, `meme_maker.py`, `render_worker.py` ou nas edições extras da v1.4.
