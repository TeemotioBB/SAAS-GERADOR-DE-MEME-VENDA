# Correção v1.3 — opções de geração

Adiciona controles por vídeo sem alterar o detector/crop calibrado:

- **Remover metadados**: ligado por padrão; controla a limpeza de tags/metadata e a limpeza profunda final.
- **Edições extras**: desligado por padrão; aplica crop leve, ajuste de cor, grão, vinheta, zoom e pequena variação de velocidade.
- **Espelhar vídeo**: desligado por padrão e totalmente separado de Edições extras, para evitar inverter textos que já façam parte do vídeo.
- **Logo** continua independente.

O espelhamento atua somente no conteúdo de vídeo antes de ele entrar no template. Nome, @, legenda e logo do template não são espelhados.

Arquivos alterados: `main.py`, `tasks.py`, `meme_maker.py`, `static/app.js`, `static/styles.css`, `templates/base.html`, `templates/dashboard.html`.
