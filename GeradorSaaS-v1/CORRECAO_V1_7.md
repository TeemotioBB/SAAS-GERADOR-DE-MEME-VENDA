# Correção v1.7 — preview preto no celular

- O vídeo final continua exatamente o mesmo.
- Ao terminar o render, o worker extrai um JPEG do primeiro frame do **vídeo final renderizado**.
- A interface usa esse JPEG como `poster` do elemento `<video>`.
- Isso evita o retângulo preto em Safari/iOS e outros navegadores mobile que não decodificam um frame do MP4 antes do primeiro play.
- `playsinline` foi adicionado ao preview.
- Para jobs antigos sem poster, o endpoint usa o frame de análise como fallback.
- Ao gerar novamente, excluir um job ou executar limpeza, o poster correspondente também é removido.

Não houve mudança no detector, crop, layout ou pipeline de renderização do MP4.
