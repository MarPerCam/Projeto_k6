# Projeto: Orquestrador de Testes k6 + Análise com Gemini

Automatize um fluxo completo de teste de carga com k6, do CSV de URLs até a análise técnica em Markdown, validando métricas contra SLOs de mercado.

## 🔎 Visão geral

Este projeto:

Lê urls.csv (coluna url);

Gera scripts_k6/teste_carga.js (sem libs externas);

Executa k6 run e salva métricas em results_k6/results.csv;

Consolida p50/p90/p95/p99, RPS e taxa de erro;

Faz validação local por SLO (p95 ≤ 1000 ms, erros ≤ 1%);

Envia um resumo ao Gemini para parecer “como especialista em performance”;

Salva o parecer em results_k6/analysis_gemini.md.

O script já detecta automaticamente o formato novo do CSV do k6 (metric_name,timestamp,metric_value,...) e também o formato antigo (metric,timestamp,value,...).

## 📂 Estrutura de pastas
.
├─ orquestrar_k6.py
├─ urls.csv                # Entrada (coluna: url)
├─ scripts_k6/
│  └─ teste_carga.js      # Script k6 gerado automaticamente
└─ results_k6/
   ├─ results.csv          # Saída bruta do k6 (--out csv=...)
   └─ analysis_gemini.md   # Parecer do Gemini (Markdown)

## ✅ Pré-requisitos

Python 3.10+ (testado em 3.11)

k6 instalado e no PATH

Verifique com: k6 version

Conta/chave do Google Gemini (defina em GOOGLE_API_KEY)

Tornando o k6 disponível no PowerShell (Windows)

Abra o PowerShell como usuário (ou admin para todos) e rode:

# Ajuste o caminho conforme sua instalação (ex.: C:\Program Files\k6\bin)
$k6Path = "C:\Program Files\k6"
$curr = [Environment]::GetEnvironmentVariable("Path","User")
[Environment]::SetEnvironmentVariable("Path", $curr + ";" + $k6Path, "User")


Feche e reabra o terminal, então:

k6 version

## 🛠️ Instalação

No diretório do projeto:

pip install pandas google-generativeai


Defina a chave do Gemini (reabra o terminal após setx):

setx GOOGLE_API_KEY "sua-chave-aqui"

## ⚙️ Configuração
urls.csv

Crie um arquivo com cabeçalho url:

url
https://www.exemplo.com.br/
https://www.exemplo.com.br/produtos/
https://www.exemplo.com.br/contato/

Parâmetros padrão do teste

No orquestrar_k6.py:

K6_VUS = 10

K6_DURATION = '2m'

SLOs (validação local)

SLO_P95_MS = 1000.0 (p95 ≤ 1000 ms)

SLO_ERR_PCT = 1.0 (erros ≤ 1%)

Ajuste conforme seu contexto (B2C, B2B, mobile, páginas dinâmicas, etc.).

## ▶️ Como executar
python orquestrar_k6.py


Saídas:

Script k6: scripts_k6/teste_carga.js

Resultados brutos: results_k6/results.csv

Análise técnica (Markdown): results_k6/analysis_gemini.md

Abra o Markdown no editor de sua preferência.

## 🧪 O que é validado

Latência (ms): p50, p90, p95, p99 a partir de http_req_duration

Taxa de erro (%): média de http_req_failed (0/1) × 100

Throughput (RPS): sum(http_reqs) / janela_em_segundos

Janela efetiva: calculada pelo intervalo de timestamp do CSV

O README considera o formato novo do CSV do k6. Exemplo de linha:

metric_name,timestamp,metric_value,check,error,error_code,expected_response,group,method,name,proto,scenario,service,status,subproto,tls_version,url,extra_tags,metadata
http_req_duration,1755385410,277.480900,,,,true,,GET,https://www.blazedemo.com,HTTP/2.0,default,,200,,tls1.3,https://www.blazedemo.com,,

## 🧠 Parecer do Gemini

O orquestrador monta um resumo sintético (VUs, duração, amostra de URLs, RPS, latências, taxa de erro, resultado dos SLOs) e solicita ao Gemini:

Diagnóstico objetivo

Riscos ao usuário/negócio

Recomendações técnicas priorizadas

SLOs sugeridos (se necessário)

Saída em: results_k6/analysis_gemini.md.

A chave do Gemini é lida de GOOGLE_API_KEY. Não a deixe hardcoded no repositório.

## 🔧 Personalização rápida

Mudar carga: ajuste K6_VUS e K6_DURATION em orquestrar_k6.py.

SLOs: edite SLO_P95_MS e SLO_ERR_PCT.

Amostra maior de URLs no resumo: altere a função build_compact_summary_text.

Somente gerar o script: comente a chamada run_k6_test() no final do main().

Se desejar cenários com ramp-up, thresholds nativos no k6, ou por-URL, veja “Roadmap” abaixo.

## 🧯 Solução de problemas

k6 não encontrado no PowerShell

Garanta que o caminho do k6.exe está no PATH do usuário (ver seção de PATH acima).

Feche e reabra o terminal/VS Code.

CSV sem colunas esperadas

Este projeto suporta:

Novo: metric_name, timestamp, metric_value, ...

Antigo: metric, timestamp, value, ...

Se o CSV foi modificado por planilha/Excel, salve novamente sem mexer nos cabeçalhos.

Falha ao chamar o Gemini

Verifique GOOGLE_API_KEY.

Se não puder usar IA no momento, o CSV e o resumo local ainda estarão disponíveis.

## 🗺️ Roadmap (sugestões de evolução)

Quebra por endpoint (por-URL): p95/erros por name/url no CSV.

Cenários k6 avançados: ramping (stages), smoke & stress, arrival-rate (RPS constante).

Thresholds no k6: reprovar teste na origem com thresholds (ex.: http_req_duration{p(95)} < 1000).

Relatórios ricos: HTML/PNG com gráficos de latência, erro e RPS.

Execução distribuída: k6 cloud ou múltiplos nós on-prem.

## 📜 Boas práticas

Defina SLOs coerentes com o contexto de negócio (p95 no app crítico costuma ser 500–1000 ms; erro ≤ 0,1–1%).

Mantenha dados de teste previsíveis para comparações históricas.

Versione o urls.csv e o analysis_gemini.md para observar evolução entre execuções.

Use ambientes isolados para não impactar produção.
