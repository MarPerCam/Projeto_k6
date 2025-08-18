# orquestrar_k6.py
import os
import sys
import json
import pandas as pd
import subprocess
import google.generativeai as genai
from textwrap import dedent
from pathlib import Path

# ===== Configurações =====
CSV_PATH = 'urls.csv'
SCRIPT_FOLDER = Path('scripts_k6')
RESULTS_FOLDER = Path('results_k6')
K6_SCRIPT_PATH = SCRIPT_FOLDER / 'teste_carga.js'
RESULTS_FILE = RESULTS_FOLDER / 'results.csv'
ANALYSIS_FILE = RESULTS_FOLDER / 'analysis_gemini.md'

# Parâmetros do teste (expostos para o prompt do Gemini)
K6_VUS = 100
K6_DURATION = '2m'

# SLOs (validação local)
SLO_P95_MS = 1000.0   # p95 deve ser <= 1000 ms
SLO_ERR_PCT = 1.0     # taxa de erro deve ser <= 1%

# API Gemini via variável de ambiente
API_KEY = 'AIzaSyBuyH3zYRhjO6V9OfPxaRoArJI3wGY8Iz0'

# ===== Utilidades =====
def ensure_dirs():
    SCRIPT_FOLDER.mkdir(parents=True, exist_ok=True)
    RESULTS_FOLDER.mkdir(parents=True, exist_ok=True)

def read_urls_from_csv(file_path: str) -> list:
    """Lê as URLs de um arquivo CSV que possua uma coluna chamada 'url'."""
    try:
        df = pd.read_csv(file_path, encoding='utf-8-sig')
    except FileNotFoundError:
        print(f"Erro: O arquivo {file_path} não foi encontrado.")
        return []
    except Exception as e:
        print(f"Erro lendo {file_path}: {e}")
        return []

    if 'url' not in df.columns:
        print("Erro: o CSV deve conter uma coluna chamada 'url'.")
        return []

    urls = [str(u).strip() for u in df['url'].dropna().tolist() if str(u).strip()]
    # remove duplicados preservando ordem
    seen, dedup = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            dedup.append(u)
    return dedup

def k6_script_from_urls(urls: list, vus: int = K6_VUS, duration: str = K6_DURATION) -> str:
    """Gera um script k6 simples em JS, com URLs embutidas."""
    urls_js = json.dumps(urls, ensure_ascii=False, indent=2)
    code = f"""
    import http from 'k6/http';
    import {{ check, sleep }} from 'k6';

    export const options = {{
      vus: {vus},
      duration: '{duration}',
    }};

    const urls = {urls_js};

    export default function () {{
      const url = urls[Math.floor(Math.random() * urls.length)];
      const res = http.get(url);

      check(res, {{
        'status is 200': (r) => r.status === 200,
      }});

      sleep(1);
    }}
    """
    return dedent(code).strip() + "\n"

def save_script(script_content: str, file_path: Path):
    file_path.write_text(script_content, encoding='utf-8')
    print(f"Script k6 salvo em: {file_path}")

def run_k6_test():
    """Executa o script k6 e salva os resultados em CSV."""
    print("Executando teste de carga com k6...")
    try:
        subprocess.run(
            ['k6', 'run', str(K6_SCRIPT_PATH), '--out', f'csv={RESULTS_FILE}'],
            check=True
        )
        print(f"Teste concluído. Resultados salvos em: {RESULTS_FILE}")
    except FileNotFoundError:
        print("Erro: k6 não encontrado. Certifique-se de que está instalado e no PATH.")
        sys.exit(3)
    except subprocess.CalledProcessError as e:
        print(f"Erro ao executar o k6: {e}")
        sys.exit(4)

# ===== Pós-processamento & Validação =====
def _normalize_k6_csv(path: Path) -> pd.DataFrame:
    """
    Normaliza o CSV do k6 para colunas padronizadas: metric, timestamp (datetime), value (float).
    Suporta:
      - Formato novo: metric_name, timestamp, metric_value, ...
      - Formato antigo: metric, timestamp, value, ...
    """
    df = pd.read_csv(path)
    cols = set(df.columns.str.lower())

    if {'metric_name', 'timestamp', 'metric_value'}.issubset(cols):
        # Formato novo (como o seu exemplo)
        # mapeia para nomes comuns
        df = df.rename(columns={
            'metric_name': 'metric',
            'metric_value': 'value'
        })
        # timestamp parece vir em epoch seconds (ex.: 1755385410)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', errors='coerce')
    elif {'metric', 'timestamp', 'value'}.issubset(cols):
        # Formato antigo
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    else:
        raise ValueError(
            f"CSV do k6 em formato inesperado. Colunas encontradas: {df.columns.tolist()}"
        )

    # mantém apenas colunas úteis
    df = df[['metric', 'timestamp', 'value']].copy()
    # normaliza tipos
    df['metric'] = df['metric'].astype(str)
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    df = df.dropna(subset=['timestamp', 'value'])
    return df

def summarize_k6_csv(csv_path: Path) -> dict:
    """
    Calcula métricas-chave:
      - http_req_duration (ms): p50/p90/p95/p99
      - http_req_failed: taxa de erro (%)
      - http_reqs: total e RPS
    """
    df = _normalize_k6_csv(csv_path)

    # Duração efetiva (em segundos) com base nos timestamps
    test_seconds = max(1.0, (df['timestamp'].max() - df['timestamp'].min()).total_seconds())

    # Latência em ms
    dur = df.loc[df['metric'] == 'http_req_duration', 'value'].astype(float)
    p50 = float(dur.quantile(0.50)) if not dur.empty else None
    p90 = float(dur.quantile(0.90)) if not dur.empty else None
    p95 = float(dur.quantile(0.95)) if not dur.empty else None
    p99 = float(dur.quantile(0.99)) if not dur.empty else None

    # Taxa de erro (%)
    fail = df.loc[df['metric'] == 'http_req_failed', 'value'].astype(float)
    error_rate = float(fail.mean() * 100.0) if not fail.empty else 0.0

    # Throughput
    reqs = df.loc[df['metric'] == 'http_reqs', 'value'].astype(float)
    total_reqs = int(reqs.sum()) if not reqs.empty else 0
    rps = float(total_reqs / test_seconds) if test_seconds > 0 else 0.0

    summary = {
        "test_window_seconds": round(test_seconds, 2),
        "total_requests": total_reqs,
        "rps": round(rps, 2),
        "latency_ms": {
            "p50": None if p50 is None else round(p50, 2),
            "p90": None if p90 is None else round(p90, 2),
            "p95": None if p95 is None else round(p95, 2),
            "p99": None if p99 is None else round(p99, 2),
        },
        "error_rate_percent": round(error_rate, 4),
    }
    return summary

def local_validation(summary: dict) -> dict:
    """Aplica SLOs locais e retorna pass/fail com motivos."""
    p95 = summary['latency_ms']['p95']
    err = summary['error_rate_percent']
    reasons = []
    status = "PASS"

    if p95 is None:
        reasons.append("p95 indisponível no CSV.")
    elif p95 > SLO_P95_MS:
        status = "FAIL"
        reasons.append(f"p95 {p95} ms > SLO {SLO_P95_MS} ms")

    if err is None:
        reasons.append("taxa de erro indisponível.")
    elif err > SLO_ERR_PCT:
        status = "FAIL"
        reasons.append(f"erros {err}% > SLO {SLO_ERR_PCT}%")

    return {"status": status, "reasons": reasons}

def build_compact_summary_text(summary: dict, urls: list, validation: dict) -> str:
    """Resumo curto para o Gemini (e também para salvar no MD)."""
    return dedent(f"""
    Contexto do teste (k6):
    - VUs: {K6_VUS}
    - Duração configurada: {K6_DURATION}
    - Janela efetiva (CSV): {summary.get('test_window_seconds')} s
    - URLs-alvo (amostra): {urls[:3]}{' ...' if len(urls) > 3 else ''}

    Métricas principais:
    - Requisições totais: {summary.get('total_requests')}
    - RPS médio: {summary.get('rps')} req/s
    - Latência (ms): p50={summary['latency_ms'].get('p50')}, p90={summary['latency_ms'].get('p90')}, p95={summary['latency_ms'].get('p95')}, p99={summary['latency_ms'].get('p99')}
    - Taxa de erro: {summary.get('error_rate_percent')}%

    Validação local (SLOs):
    - SLO p95 <= {SLO_P95_MS} ms; SLO erros <= {SLO_ERR_PCT}%
    - Resultado: {validation['status']} | Motivos: {', '.join(validation['reasons']) if validation['reasons'] else '—'}
    """).strip()

def analyze_with_gemini(summary_text: str) -> str:
    """Envia o resumo ao Gemini pedindo análise como especialista de performance."""
    if not API_KEY:
        raise RuntimeError("Defina a variável de ambiente GOOGLE_API_KEY para usar o Gemini.")

    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')

    prompt = dedent(f"""
    Você é um especialista em testes de performance. Analise o resumo abaixo de um teste k6.
    Valide tempos de resposta (especialmente p95) e taxa de erros contra práticas comuns de mercado.
    Escreva:
    - Diagnóstico objetivo (1-2 parágrafos)
    - Riscos ao usuário/negócio
    - Recomendações técnicas priorizadas (curtas e práticas)
    - SLOs sugeridos (p95 e taxa de erro) se os atuais estiverem desalinhados

    Resumo:
    {summary_text}
    """).strip()

    resp = model.generate_content(prompt)
    return (resp.text or "Sem resposta do modelo.").strip()

def save_markdown(text: str, path: Path):
    path.write_text(text, encoding='utf-8')
    print(f"Análise do Gemini salva em: {path}")

# ===== Execução principal =====
def main():
    ensure_dirs()
    urls = read_urls_from_csv(CSV_PATH)

    if not urls:
        print("Nenhuma URL encontrada. Verifique o CSV.")
        sys.exit(1)

    print(f"URLs lidas do CSV ({len(urls)}): {urls}")

    script = k6_script_from_urls(urls, vus=K6_VUS, duration=K6_DURATION)
    save_script(script, K6_SCRIPT_PATH)

    run_k6_test()

    # Pós-processamento e análise
    try:
        summary = summarize_k6_csv(RESULTS_FILE)
        validation = local_validation(summary)
        summary_text = build_compact_summary_text(summary, urls, validation)
        analysis = analyze_with_gemini(summary_text)
        md = (
            "# Análise automática (Gemini)\n\n"
            "## Resumo sintetizado\n\n"
            "```\n" + summary_text + "\n```\n\n"
            "## Parecer do especialista (IA)\n\n" + analysis + "\n"
        )
        save_markdown(md, ANALYSIS_FILE)
        print("Pipeline completo: script gerado, k6 executado, resultados analisados e validados.")
    except Exception as e:
        print(f"[Aviso] Falha ao analisar com Gemini ou processar CSV: {e}")
        print("O teste foi executado; o CSV está disponível para análise manual.")

if __name__ == "__main__":
    main()
