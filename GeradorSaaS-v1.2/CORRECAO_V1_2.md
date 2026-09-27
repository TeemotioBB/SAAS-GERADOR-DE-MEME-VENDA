# Correção v1.2 — desktop x celular

## Causa
O backend não renderiza de forma diferente por dispositivo. Quando o celular mostrava a nova geração correta e o desktop continuava mostrando outra, havia dois problemas de consistência:

1. o resultado era sempre salvo na mesma chave `result.mp4`, permitindo cache do navegador/S3;
2. o crop ajustado pelo usuário era enviado ao worker, mas não era persistido em `job.crop`.

## Mudanças
- cada geração usa `result_vN.mp4`;
- preview e download recebem versão na URL;
- respostas de vídeo usam `no-store`;
- CSS/JS recebem `?v=1.2.0` para evitar JS antigo no desktop;
- crop é normalizado/clampado no servidor;
- crop usado na geração passa a ser salvo no job;
- arraste usa as dimensões reais exibidas do frame.

## Arquivos alterados
- `static/app.js`
- `templates/base.html`
- `templates/dashboard.html`
- `main.py`
- `tasks.py`
- `storage.py`

Depois do deploy, exclua o job usado nos testes antigos e importe o Reel novamente.
