# v1.6 — Redesign de experiência e interface

Esta versão parte da v1.5 estável e altera somente a camada de interface/experiência. O motor de recorte, renderização, FFmpeg, leitura de texto, storage, fila, opções de edição e backend não foram alterados.

## Dashboard
- navegação desktop mais limpa e navegação inferior fixa no mobile;
- cabeçalho com uso mensal e barra de progresso;
- etapas 1 → 2 → 3 com estado visual dinâmico;
- importação por link e upload reunidos em uma única área com abas;
- drag & drop para upload no desktop;
- feedback de carregamento/erro/sucesso mais claro;
- rolagem automática para a área de revisão após adicionar conteúdo;
- lista de trabalhos em uma coluna no desktop, com preview à esquerda e controles à direita;
- cards empilhados e botões grandes no mobile;
- chamada, opções e ações agrupadas por contexto;
- avisos temporários (toasts) no lugar de parte dos alerts;
- modal de geração refinado e adaptado para bottom-sheet no mobile.

## Minha página
- preview da identidade separado do formulário;
- campos agrupados em informações e arquivos;
- estado visual de avatar/logo/template;
- melhor organização no celular.

## Login / cadastro
- layout desktop em duas áreas com explicação do produto;
- versão mobile limpa e direta;
- campos e botões maiores para toque.

## Importante
Nenhum arquivo Python do motor foi modificado nesta versão. Portanto, detector, crop, render, metadados, edições extras e espelhamento permanecem iguais à v1.5.
