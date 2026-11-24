# Rota Vital – Emissão de Guias (Atividade Individual 1: Serverless)

Disciplina de **Infraestrutura de Software** — CESAR School (2026.2).

## Caminho escolhido

**Caminho A (AWS SAM CLI local, sem conta AWS)**, executando a função Lambda em Python 3.12 localmente com Docker Desktop e Git Bash no Windows.

Ambiente verificado na execução:
- Docker `29.9.3` (Docker Desktop ativo)
- AWS SAM CLI `1.174.0`
- Python `3.12.10`

---

## Como rodar

1. Abra o **Docker Desktop** e confirme que o engine está rodando.
2. Abra o **Git Bash** na pasta do projeto (`rota-vital-guias`).
3. No Git Bash no Windows, defina o atalho abaixo para chamar o `sam` sem problemas de aspas do `sam.cmd`:

```bash
sam() { "/c/Program Files/Amazon/AWSSAMCLI/runtime/python.exe" -m samcli "$@"; }
```

4. Faça o build da função:

```bash
sam build
```

5. **Invocação local com evento** (`events/pedido.json`):

```bash
time sam local invoke -e events/pedido.json
```

6. **API local via HTTP**:
   - Sem reutilizar containers (padrão, após comentar `warm_containers` no `samconfig.toml`):
     ```bash
     sam local start-api
     ```
   - Reutilizando o container entre chamadas:
     ```bash
     sam local start-api --warm-containers LAZY
     ```

   Em outro terminal Git Bash, faça as requisições:

   ```bash
   # Criação normal de guia (retorna 201)
   curl -X POST http://127.0.0.1:3000/guias \
     -H "Content-Type: application/json" \
     -d '{"requisicaoId":"R-002","hospital":"H-Caruaru"}'

   # Teste de validação sem requisicaoId (retorna 400)
   curl -X POST http://127.0.0.1:3000/guias \
     -H "Content-Type: application/json" \
     -d '{}'

   # Teste de tempo limite (dorme 5s)
   curl -X POST http://127.0.0.1:3000/guias \
     -H "Content-Type: application/json" \
     -d '{"requisicaoId":"R-003","demorar":true}'
   ```

> **Nota sobre o `Timeout`:** os testes de limite de tempo foram feitos primeiro com `Timeout: 3` (gerando erro) e depois com `Timeout: 10` (após `sam build`, retornando 201). O arquivo `template.yaml` foi mantido com `Timeout: 10`.

---

## Respostas às 5 perguntas

### 1. Por que a primeira invocação demorou mais que a segunda? O que acontece na fase Init?

No meu teste com `sam local invoke -e events/pedido.json`, a primeira invocação levou `36,677 s` (`Duration: 51,00 ms`) e a segunda levou `6,425 s` (`Duration: 61,53 ms`). A primeira demorou bem mais porque o SAM ainda precisou baixar e montar a imagem Docker do Python 3.12 (`Local image was not found` → `Building image`). Na segunda a imagem já estava salva (`Local image is up-to-date`), mas ainda levou `6,425 s` porque o `sam local invoke` cria um container novo a cada execução. Por isso também o campo `invocacaoNesteAmbiente` saiu como `1` nas duas vezes. Repeti o teste depois, com a imagem já baixada, e as duas invocações levaram cerca de 7 s cada (7,687 s e 7,004 s), com `invocacaoNesteAmbiente` = 1 nas duas.

Na fase **Init** (o *cold start*), o Lambda prepara o ambiente antes de rodar a função: carrega o código, sobe o runtime Python e executa o que fica fora do `lambda_handler` (os `import` e o `contador = 0`). Vale notar que o `Init Duration: 0,03 ms` que apareceu no emulador local **não** representa o cold start real da AWS, onde esse tempo costuma ser bem maior (centenas de milissegundos). Quando o ambiente é reaproveitado, a fase Init não roda de novo — no meu teste com `--warm-containers LAZY`, o `Duration` caiu de `48,02 ms` na 1ª chamada para `1,25 ms` e `1,09 ms` nas seguintes.

---

### 2. O que o campo `invocacaoNesteAmbiente` mostrou com e sem `--warm-containers`? O que isso diz sobre guardar estado numa variável global da função?

Eu fiz 3 chamadas `POST /guias` com `{"requisicaoId":"R-002","hospital":"H-Caruaru"}` nos dois modos e obtive estes resultados:

| Chamada | Sem `--warm-containers` | Com `--warm-containers LAZY` |
|---|---|---|
| 1ª | `invocacaoNesteAmbiente: 1` (`Duration: 51,46 ms`, container `a8a6bff3c41d…`) | `invocacaoNesteAmbiente: 1` (`Duration: 48,02 ms`, container `c25cf79747df…`) |
| 2ª | `invocacaoNesteAmbiente: 1` (`Duration: 49,53 ms`, container `514b2930101d…`) | `invocacaoNesteAmbiente: 2` (`Duration: 1,25 ms`, mesmo container) |
| 3ª | `invocacaoNesteAmbiente: 1` (`Duration: 46,62 ms`, container `6577aaf3b6e6…`) | `invocacaoNesteAmbiente: 3` (`Duration: 1,09 ms`, mesmo container) |

Sem `--warm-containers`, cada chamada criou um container novo e o contador sempre voltou para `1` (`1, 1, 1`). Com `--warm-containers LAZY`, o mesmo container continuou vivo e o contador subiu (`1, 2, 3`).

Com isso eu percebi que **não dá para confiar em variável global para guardar estado** da aplicação. O container pode ser destruído a qualquer hora (zerando tudo) ou podem existir vários containers rodando ao mesmo tempo, cada um com um valor diferente na memória. O que precisa ficar salvo de verdade tem que ir para fora da função, como um banco de dados ou cache.

---

### 3. O que aconteceu com `demorar = true`? Qual é o tempo máximo de uma execução no Lambda e o que fazer com um trabalho mais longo?

No meu teste enviando `{"requisicaoId":"R-003","demorar":true}` (que faz `time.sleep(5)`), com `Timeout: 3` a função foi cortada aos 3 segundos e devolveu **HTTP 502** (`{"message":"Internal server error"}`, tempo total do `curl`: `10,097 s`), com as mensagens `Function 'HelloWorldFunction' timed out after 3 seconds` e `Invalid lambda response received` no terminal. Esse retorno 502 com `"Invalid lambda response"` é comportamento do emulador local; na AWS real, o erro de tempo limite fica registrado nos logs do CloudWatch como `"Task timed out after 3.00 seconds"`. Depois eu mudei para `Timeout: 10`, rodei `sam build` e repeti a chamada: aí a função terminou em `Duration: 5063,38 ms` (tempo total do `curl`: `8,734 s`) e retornou **HTTP 201** com `"guia": "G-R-003"`.

O tempo máximo de uma execução no AWS Lambda é de **15 minutos** (900 segundos). Se um trabalho demorar mais que isso, o caminho é dividir a tarefa em etapas menores (usando uma fila como o SQS ou um fluxo no AWS Step Functions) ou rodar esse processo fora do Lambda, em um container ou servidor comum (como ECS/Fargate ou uma máquina virtual).

---

### 4. Com os preços de `us-east-1` (US$ 0,20 por milhão de requisições e US$ 0,0000166667 por GB-s), quanto custa um milhão de execuções desta função com 128 MB e 100 ms?

Fazendo a conta passo a passo (sem contar o Free Tier):

1. **Requisições:** `1.000.000 × (US$ 0,20 / 1.000.000) = US$ 0,20`
2. **Computação (GB-s):**
   - Memória em GB: `128 MB / 1024 = 0,125 GB`
   - Tempo em segundos: `100 ms = 0,1 s`
   - Por execução: `0,125 GB × 0,1 s = 0,0125 GB-s`
   - Em 1 milhão de execuções: `0,0125 GB-s × 1.000.000 = 12.500 GB-s`
   - Custo de computação: `12.500 × US$ 0,0000166667 = US$ 0,20833375 ≈ US$ 0,2083`
3. **Total:** `US$ 0,20 + US$ 0,2083 = US$ 0,4083` → **cerca de US$ 0,41**.

---

### 5. Em que parte do Rota Vital uma função assim faria sentido, e em qual não faria?

No Rota Vital, uma função assim **faz sentido** para tarefas rápidas e pontuais disparadas por um evento ou pedido HTTP, como emitir a guia de transporte quando um hospital solicita bolsas de sangue, validar os dados da requisição ou enviar um aviso de saída e entrega.

Já onde **não faz sentido** é em partes que precisam ficar conectadas o tempo todo ou manter estado constante, como o rastreamento contínuo da localização e da temperatura das bolsas durante o trajeto em tempo real. Para esse caso, um servidor ou container rodando direto funciona melhor.

---

## Observações

1. **Body do evento em base64 (`SAM CLI 1.174.0`):** o comando `sam local generate-event apigateway aws-proxy` nessa versão gera o campo `body` codificado em base64 com `"isBase64Encoded": true`. Por isso a função em `hello_world/app.py` verifica `event.get("isBase64Encoded")` e decodifica com `base64.b64decode(...)` antes do `json.loads`. O arquivo `events/pedido.json` foi mantido exatamente como o comando gerou.
2. **`warm_containers = "EAGER"` no `samconfig.toml`:** o `sam init` gera o `samconfig.toml` com `warm_containers = "EAGER"` nas seções `local_start_api` e `local_start_lambda`, o que fazia o `sam local start-api` sem flag já reutilizar o container (contador 1, 2, 3 na primeira tentativa). Comentei essas duas linhas para que o comando sem flag siga o comportamento padrão (um container por requisição) e o experimento com `--warm-containers LAZY` reflita a diferença real.

---

## Evidências

Prints salvos na pasta `evidencias/`:

- `evidencias/01-ambiente.png` — versões instaladas do Docker, SAM CLI e Python 3.12.
- `evidencias/02-template.png` — `template.yaml` mostrando `Path: /guias`, `Method: post` e `Timeout`.
- `evidencias/03-app-py.png` — código da função em `hello_world/app.py`.
- `evidencias/04a-evento-e-build.png` — geração de `events/pedido.json` e resultado do `sam build`.
- `evidencias/04a-pedido-json.png` — arquivo `events/pedido.json` mostrando o `body` em base64 e `isBase64Encoded: true`.
- `evidencias/04b-invoke-1-e-2.png` — duas execuções seguidas de `sam local invoke -e events/pedido.json` com seus tempos.
- `evidencias/05a-start-api-sem-warm.png` — 3 chamadas `curl` em `sam local start-api` sem flag (`invocacaoNesteAmbiente` = 1, 1, 1).
- `evidencias/05b-start-api-warm-lazy.png` — 3 chamadas `curl` com `--warm-containers LAZY` (`invocacaoNesteAmbiente` = 1, 2, 3).
- `evidencias/06a-timeout-3s.png` — erro HTTP 502 e log de timeout ao enviar `demorar: true` com `Timeout: 3`.
- `evidencias/06b-timeout-10s.png` — resposta HTTP 201 (`G-R-003`) ao repetir o teste com `Timeout: 10`.

Vídeo: https://drive.google.com/file/d/1AejuGC60L0Da-afT6DCyFPD1M1EAHiiG/view?usp=sharing

---

## Uso de IA

- **Ferramenta:** Antigravity (com os modelos Claude Sonnet 5.5, Claude Opus 5.5 e Gemini 4 Neon).
- **Finalidade:** usei a IA como apoio na configuração do SAM CLI local, na escrita do código em `hello_world/app.py`, nos experimentos e na redação inicial do texto.
- **Como validei:** eu mesmo instalei o Docker, o SAM CLI e o Python 3.12, ativei a virtualização na BIOS, rodei os comandos, conferi todas as saídas reais, tirei os prints e gravei o vídeo. Também revisei o código linha por linha para conseguir explicá-lo em sala, e as respostas deste README foram revisadas e reescritas por mim.
