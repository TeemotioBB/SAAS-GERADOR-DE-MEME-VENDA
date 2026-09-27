# Correção v1.4

- A chamada do vídeo é lida automaticamente após importação/upload sempre que `CLAUDE_API_KEY` estiver configurada no **Worker**.
- Falha na leitura automática não bloqueia mais o job: o vídeo fica pronto com campo de chamada vazio.
- A chamada agora é opcional no frontend e no backend.
- Vídeo sem chamada gera normalmente.
- Sem chamada, o template não reserva uma linha vazia: mantém cabeçalho da página, respiro e vídeo.
- `Reler texto` continua disponível como tentativa manual.
- Recorte, edições extras, espelhamento e remoção de metadados da v1.3 foram preservados.

## Railway

Para leitura automática, confirme que a mesma chave existe no **Web e no Worker**:

```env
CLAUDE_API_KEY=sua_chave
```

O Web usa a chave no botão **Reler texto**; o Worker usa a chave na leitura automática durante a análise.
