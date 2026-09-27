# ClipFrame SaaS v1

Versão SaaS do seu gerador original. Esta edição foi reorganizada para múltiplos clientes e **não contém a busca automática de Reels pelo seu perfil/algoritmo**.

## Fluxo comercial desta versão

1. Usuário cria uma conta.
2. Configura **nome da página, @, avatar e logo opcional**.
3. Cola um ou vários links de Reels **ou envia vídeos do computador/celular**.
4. O backend baixa/recebe o vídeo, detecta automaticamente o recorte e tenta ler a chamada do frame com Claude.
5. O usuário pode corrigir o recorte e o texto.
6. O sistema renderiza usando **o mesmo layout fixo e calibrado para todos os clientes**.
7. O usuário baixa o MP4 ou um ZIP.

Não existe editor livre de posição/fonte/template nesta versão. Isso é intencional.

## O que mudou em relação ao projeto antigo

- cadastro, login e logout;
- senhas com hash;
- CSRF e cookies seguros;
- rotas de arquivo protegidas por usuário;
- cada job possui `user_id` e um usuário não consegue abrir job de outro;
- identidade da página saiu de `PERFIS` hardcoded e passou para o banco;
- o layout visual continua fixo;
- Postgres para contas, jobs, status e uso;
- Redis + RQ para tarefas que continuam mesmo se o navegador fechar;
- storage local em desenvolvimento e S3/R2 em produção;
- render continua isolado em subprocesso para devolver RAM ao sistema;
- limite mensal por conta;
- painel admin para liberar/bloquear usuários e alterar limite;
- rate limit;
- importação em lote por links;
- upload manual como fallback independente do Instagram;
- ZIP sem montar todos os vídeos simultaneamente em RAM;
- links S3/R2 assinados para preview/download;
- comando de limpeza de mídia antiga;
- páginas iniciais de Termos e Privacidade;
- removidos: coletor automático de Reels, aba “Minha aba de Reels”, chave de agente, agente local e dependência do seu feed pessoal.

## Pagamento

**Não há integração de pagamento nesta versão**, conforme solicitado.

Enquanto isso, use o painel `/admin` para controlar manualmente o limite de cada cliente. Exemplo:

- teste: 3 vídeos/mês;
- cliente pago manualmente: 100 vídeos/mês;
- conta suspensa: desmarcar `Ativa`.

Quando você integrar cobrança, basta o webhook do provedor atualizar `monthly_limit`, `plan_name` e/ou `account_active`. O restante do SaaS já está separado por usuário.

## Arquitetura de produção recomendada

```text
Navegador
   |
   v
WEB / Flask (Railway)
   |------ Postgres
   |------ Redis / RQ ------ Worker (Railway)
   |                           |
   +--------- S3 / R2 <--------+
                               |
                          FFmpeg/OpenCV
```

O web não precisa renderizar o vídeo. Ele cria o job e o worker executa a tarefa.

## Serviços para criar no Railway

### 1. PostgreSQL

Adicione um PostgreSQL e exponha `DATABASE_URL` para web e worker.

### 2. Redis

Adicione Redis e exponha `REDIS_URL` para web e worker.

### 3. Serviço Web

Mesmo repositório. O `Procfile` já contém o comando web. Você também pode usar:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT --worker-class gthread --workers 2 --threads 4 --timeout 120
```

### 4. Serviço Worker

Crie outro serviço a partir do mesmo repositório e use:

```bash
python worker.py
```

Web e worker devem receber as mesmas variáveis de banco, Redis, S3/R2, Instagram e Claude.

## Storage: use R2/S3 em produção

Quando web e worker são serviços separados, eles **não devem depender do mesmo `/tmp`**. Configure um bucket S3-compatible (Cloudflare R2, AWS S3 etc.):

```env
S3_BUCKET=seu-bucket
S3_ENDPOINT=https://SEU_ACCOUNT_ID.r2.cloudflarestorage.com
S3_REGION=auto
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
```

Sem `S3_BUCKET`, o código usa `instance/storage/`, adequado para desenvolvimento ou um único serviço.

## Variáveis de ambiente

Copie `.env.example` como referência.

Obrigatórias em produção:

```env
SECRET_KEY=uma-chave-longa-e-aleatoria
DATABASE_URL=...
REDIS_URL=...
ADMIN_EMAIL=seu@email.com
SESSION_COOKIE_SECURE=1
```

Para gerar uma `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Administrador

Defina `ADMIN_EMAIL` antes de registrar sua conta. A conta com esse e-mail será promovida para admin automaticamente.

Também existe:

```bash
flask --app app set-admin email@dominio.com
```

## Instagram

A importação por link continua usando `yt-dlp` e aceita apenas URLs de Instagram compatíveis.

Em datacenter, o Instagram pode bloquear downloads anônimos. Nesse caso configure:

```env
INSTAGRAM_COOKIES_B64=...
```

Esse mecanismo pode precisar de manutenção ao longo do tempo. Por isso o SaaS mantém **upload manual** como alternativa permanente.

A busca automática baseada no seu próprio perfil foi removida completamente.

## Claude / leitura de texto

```env
CLAUDE_API_KEY=...
AUTO_READ_CAPTION=1
```

Se `AUTO_READ_CAPTION=0`, o cliente ainda pode escrever a chamada manualmente. Sem chave, o botão de releitura automática informa que o recurso não está configurado.

## Limite de uso

```env
MONTHLY_VIDEO_LIMIT=3
```

Esse valor é aplicado a novas contas. `3` funciona como teste inicial; depois do pagamento manual você pode aumentar a conta para 100 (ou o valor do plano) pelo admin.

A contagem aumenta apenas quando uma renderização termina com sucesso.

## Retenção e limpeza

O cliente pode apagar jobs pelo painel. Para limpeza periódica:

```bash
flask --app app cleanup-media --days 7
```

Você pode executar esse comando em um cron/scheduler diário. Também é recomendável configurar lifecycle/retention no bucket.

## Desenvolvimento local

Sem Postgres, o app usa SQLite. Sem S3, usa storage local. Sem Redis, as tarefas caem para threads locais.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Abra `http://127.0.0.1:5000`.

Para simular execução síncrona de tarefas em desenvolvimento:

```env
TASKS_EAGER=1
```

## FFmpeg

`nixpacks.toml` pede `ffmpeg` no Railway. Localmente, `ffmpeg` e `ffprobe` precisam estar no PATH.

## Segurança implementada

- arquivos e jobs sempre conferem `user_id`;
- senha não é armazenada em texto puro;
- CSRF nos POST/DELETE do navegador;
- session cookie HTTPOnly/SameSite;
- HSTS quando HTTPS;
- rate limits nas rotas caras;
- URL de Instagram validada contra domínios aceitos;
- limites de upload;
- nome de arquivo sanitizado;
- storage privado e URL temporária assinada para download remoto;
- configuração visual do cliente enviada apenas ao processo de render daquele job.

## Antes de abrir vendas publicamente

O código está estruturado como **MVP SaaS comercial**, mas ainda há tarefas empresariais que código sozinho não resolve:

1. revisar Termos de Uso e Política de Privacidade com profissional adequado;
2. definir empresa/CNPJ, suporte, política de cancelamento e retenção;
3. configurar domínio, e-mail de suporte e monitoramento;
4. testar custos reais de CPU, Claude, storage e tráfego para decidir a cota do plano de R$ 49,90;
5. depois integrar pagamento recorrente.

Também deixe claro que o usuário deve possuir direito ou autorização para reutilizar o conteúdo que importa.
