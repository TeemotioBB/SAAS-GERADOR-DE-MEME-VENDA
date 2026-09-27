# Correção v1.1 — recorte/preview

O detector e o analysis_worker continuam idênticos ao projeto pessoal original.

A falha estava no frontend: a caixa de crop era posicionada em relação ao contêiner do card, enquanto a imagem vertical podia ficar menor/centralizada por causa do `max-height`. Isso fazia o recorte parecer deslocado e, após ajuste manual, enviava coordenadas incorretas para a renderização.

Correção:
- preview agora sempre mantém exatamente a proporção `width/height` do vídeo;
- caixa de crop usa a mesma superfície geométrica da imagem;
- arraste/redimensionamento volta a converter pixels da tela para coordenadas do vídeo corretamente;
- detector/renderizador não tiveram a lógica de detecção alterada;
- requirements já usa `psycopg[binary]`, compatível com a URL PostgreSQL atual do projeto.
