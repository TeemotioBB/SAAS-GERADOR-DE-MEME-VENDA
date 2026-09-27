# Migração do projeto antigo

Esta versão deve ser publicada como um serviço novo primeiro, sem sobrescrever o projeto pessoal até você validar tudo.

## O que foi preservado

- detector de área do vídeo (`detector.py`);
- análise em subprocesso (`analysis_worker.py`);
- render em subprocesso (`render_worker.py`);
- template 1080x1920 e posicionamento calibrado;
- fontes e emojis;
- importação de Reels por link com `yt-dlp`;
- crop automático + correção manual;
- leitura de chamada por Claude;
- MP4 final e ZIP.

## O que foi removido

- busca automática de Reels baseada no seu perfil;
- `reels_collector.py`;
- agente local e heartbeat;
- chave `AUTOMACAO_TOKEN`;
- lógica PC online/offline;
- perfis pessoais hardcoded;
- opções expostas de anti-detecção/uniqueness.

## O que entrou

- usuários;
- autenticação;
- página/identidade por usuário;
- Postgres;
- Redis/RQ;
- S3/R2;
- isolamento dos arquivos;
- cotas;
- admin;
- rate limit;
- limpeza de mídia;
- segurança de sessão/CSRF.

## Primeira publicação

1. Suba este projeto em um novo repositório.
2. Crie Postgres e Redis.
3. Configure R2/S3.
4. Configure as variáveis de `.env.example`.
5. Suba um serviço web e um worker.
6. Registre sua própria conta usando o e-mail definido em `ADMIN_EMAIL`.
7. Configure uma página de teste.
8. Teste upload, link do Instagram, leitura da legenda, crop, geração, download e ZIP.
9. Só depois direcione clientes para essa versão.

## Pagamento

Ainda não existe cobrança automática. Para os primeiros clientes, você pode receber externamente e, no painel admin, alterar o limite mensal da conta.
