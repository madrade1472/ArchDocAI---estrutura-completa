# ArchDocAI

**Autor:** Marcus Andrade &nbsp;|&nbsp; [LinkedIn](https://www.linkedin.com/in/madrade) &nbsp;|&nbsp; [GitHub](https://github.com/madrade1472)

Documentação automática de arquitetura de software e dados com IA.
Conecte qualquer repositório Git, escolha seu LLM (Claude ou GPT) e receba um diagrama de arquitetura, um documento `.docx` e um PDF gerados automaticamente.

---

## Como funciona

1. Voce informa a URL do repositório Git
2. O sistema clona o projeto (shallow clone, sem precisar baixar o historico inteiro)
3. Um LLM de sua escolha (Claude ou GPT) analisa os arquivos e identifica as camadas da arquitetura
4. O sistema valida com voce se o entendimento esta correto
5. Sao gerados: diagrama PNG, documento Word e PDF com a documentacao tecnica completa

---

## Estrutura do Projeto (3 camadas)

```
src/
  ingestion/       Camada 1: le e entende o projeto
    scanner.py     Varre arquivos por extensao (SQL, Python, YAML, Terraform...)
    context.py     Monta o contexto para enviar ao LLM

  analysis/        Camada 2: analisa com LLM e gera o diagrama
    llm_client.py  Cliente LLM que funciona com OpenAI e Anthropic
    analyzer.py    Envia o contexto, recebe JSON estruturado da arquitetura
    diagram.py     Gera o diagrama visual (PNG) e markup Mermaid

  output/          Camada 3: gera os documentos finais
    docx_gen.py    Gera o arquivo .docx
    pdf_gen.py     Gera o PDF

web/
  app.py           API FastAPI (backend da interface web)
  templates/
    index.html     Interface web

cli.py             CLI principal (typer + rich)
```

---

## Requisitos

- Python 3.10 ou superior
- Git instalado
- Uma chave de API da OpenAI ou da Anthropic

---

## Configuracao Local via VS Code

### 1. Clonar o repositorio

Abra o terminal integrado do VS Code (`Ctrl + J`) e execute:

```bash
git clone https://github.com/madrade1472/ArchDocAI---estrutura-completa.git
cd ArchDocAI---estrutura-completa
```

### 2. Criar o ambiente virtual

```bash
python -m venv .venv
```

Ativar no Windows:
```bash
.venv\Scripts\activate
```

Ativar no Mac/Linux:
```bash
source .venv/bin/activate
```

O VS Code vai detectar o `.venv` automaticamente e perguntar se deseja usa-lo como interpretador. Clique em **Yes**.

Caso nao apareça a notificacao, pressione `Ctrl + Shift + P`, digite **Python: Select Interpreter** e escolha o `.venv`.

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar as variaveis de ambiente

Copie o arquivo de exemplo:

```bash
cp .env.example .env
```

Abra o `.env` no VS Code e preencha:

```env
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o
OUTPUT_LANGUAGE=pt
```

Para usar Claude (Anthropic), troque para:

```env
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
LLM_MODEL=claude-sonnet-4-6
```

### 5. Executar via CLI (linha de comando)

Analisar um projeto local:

```bash
python cli.py analyze ./caminho/do/projeto
```

Com opcoes:

```bash
python cli.py analyze ./meu-projeto --name "Nome do Projeto" --lang pt
```

Modo automatico sem perguntas de validacao:

```bash
python cli.py analyze ./meu-projeto --yes
```

Os arquivos gerados ficam na pasta `output/`.

---

## Configuracao da Interface Web

### 1. Subir o servidor

Com o ambiente virtual ativado, execute:

```bash
python cli.py serve
```

O servidor sobe em `http://localhost:8080`

Para usar uma porta diferente:

```bash
python cli.py serve --port 3000
```

### 2. Acessar a interface

Abra o navegador em:

```
http://localhost:8080
```

### 3. Usar a interface

1. Escolha o **provedor** (OpenAI ou Anthropic)
2. Informe o **modelo** (`gpt-4o`, `claude-sonnet-4-6`, etc.)
3. Cole sua **API Key**
4. Informe a **URL do repositorio Git** que deseja analisar
5. Informe a **branch** (opcional, padrao e `main`)
6. Clique em **Analisar Arquitetura**
7. Aguarde a analise (entre 30 e 60 segundos dependendo do projeto)
8. Valide o entendimento do AI respondendo as perguntas exibidas
9. Baixe o `.docx`, o PDF e o diagrama PNG

Para repositorios privados, use o formato com token na URL:

```
https://SEU_TOKEN@github.com/usuario/repositorio.git
```

---

## LLMs suportados

| Provedor  | Modelos                                         |
|-----------|-------------------------------------------------|
| OpenAI    | gpt-4o, gpt-4-turbo, gpt-3.5-turbo             |
| Anthropic | claude-opus-4-6, claude-sonnet-4-6              |
| Custom    | Qualquer modelo compativel com a API da OpenAI  |

---

## Branches

| Branch       | Descricao                                      |
|--------------|------------------------------------------------|
| main         | Versao estavel                                 |
| develop      | Integracao das features em desenvolvimento     |
| feat/web-ui  | Evolucoes da interface web                     |

---

## Saidas geradas

Todos os arquivos ficam na pasta `output/`:

| Arquivo                        | Descricao                        |
|--------------------------------|----------------------------------|
| `architecture.png`             | Diagrama visual em camadas       |
| `PROJETO_architecture.docx`    | Documentacao tecnica Word        |
| `PROJETO_architecture.pdf`     | Documentacao tecnica PDF         |
| `PROJETO_diagram.mmd`          | Markup Mermaid para edicao       |

---

## Licenca

Copyright (c) 2026 Marcus Andrade. Todos os direitos reservados.

Este projeto e proprietario. Visualizacao permitida para fins de portfolio.
Uso, copia, modificacao e distribuicao sao proibidos sem autorizacao expressa.
Veja o arquivo [LICENSE](LICENSE) para os termos completos.

**Autor:** Marcus Andrade
[linkedin.com/in/madrade](https://www.linkedin.com/in/madrade) | [github.com/madrade1472](https://github.com/madrade1472)
