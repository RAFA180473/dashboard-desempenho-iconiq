#!/usr/bin/env python3
"""
ICONIQ | AutoUnion — atualização automática do Painel de Performance
=====================================================================

Lê as exportações do WheelSys (ou o Painel_ICONIQ_backup.xlsx), aplica as
regras definidas no Manual Técnico do Painel e no trabalho ISCTE (out/2026),
e gera:

  saida/dados_dashboard.json   dados agregados para o dashboard
  saida/Dashboard_ICONIQ.html  dashboard pronto a abrir/publicar
  saida/validacao.xlsx         controlos de qualidade e reconciliação

Uso:
  python atualizar_painel.py                # usa a pasta ./entrada
  python atualizar_painel.py --entrada X    # outra pasta

Estrutura da pasta de entrada (tudo opcional exceto uma fonte de rentals):
  entrada/Painel_ICONIQ_backup*.xlsx   Base_Rentals, Fleet, OCS_Mensal,
                                       Vendas_Colaborador (input L:Q)
  entrada/rentals/*.xlsx|*.csv         exportações WheelSys de rentals
                                       (mesmas 15 colunas do Base_Rentals);
                                       juntam-se ao backup, sem duplicar
                                       contratos (Agr. No)
  entrada/extras/*.xlsx                Extra Sales Reports (WheelSys)
  entrada/exclusoes.csv                coluna "Agr. No" com contratos a
                                       excluir (ex.: os 45 do trabalho)
"""
from __future__ import annotations

import argparse
import calendar
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------- convenções
ESTACOES = {"LXAAPT": "Lisboa", "OPTAPT": "Porto", "FAOAPT": "Faro"}
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
COLS_RENTALS = ["Check-out Date", "Check-in Date", "Days", "Check-out station",
                "Check-in station", "Net Rental", "Damages", "Net",
                "Check-out User", "Check-in User", "Agr. No", "Accrued days",
                "Booking User", "Corporate", "Rate code"]
SEM_COLAB = "(sem colaborador)"
# Utilizadores de sistema: não são colaboradores de balcão
UTILIZADORES_SISTEMA = {"account system"}

AQUI = Path(__file__).resolve().parent


def norm_nome(x) -> str:
    """Remove espaços a mais ('Vasconcelos  Rui', 'Farola Bruno ')."""
    if pd.isna(x):
        return SEM_COLAB
    s = re.sub(r"\s+", " ", str(x)).strip()
    return s or SEM_COLAB


def norm_texto_vazio(x) -> str:
    """Corporate vazio deve ser realmente vazio (manual, secção 10)."""
    if pd.isna(x):
        return ""
    return str(x).strip()


class Log:
    def __init__(self):
        self.linhas: list[dict] = []

    def add(self, controlo, resultado, estado="OK", detalhe=""):
        self.linhas.append({"Controlo": controlo, "Resultado": resultado,
                            "Estado": estado, "Detalhe": detalhe})
        marca = {"OK": "✓", "AVISO": "!", "ERRO": "✗"}.get(estado, "-")
        print(f"  [{marca}] {controlo}: {resultado} {detalhe}")


# ---------------------------------------------------------------- leitura
def ler_backup(pasta: Path):
    ficheiros = sorted(pasta.glob("Painel_ICONIQ_backup*.xlsx"))
    return ficheiros[-1] if ficheiros else None


def ler_rentals(pasta: Path, backup: Path | None, log: Log) -> pd.DataFrame:
    partes = []
    if backup:
        b = pd.read_excel(backup, sheet_name="Base_Rentals")
        b["_fonte"] = backup.name
        partes.append(b)
    for f in sorted((pasta / "rentals").glob("*")):
        if f.suffix.lower() in (".xlsx", ".xls"):
            d = pd.read_excel(f)
        elif f.suffix.lower() == ".csv":
            d = pd.read_csv(f, sep=None, engine="python")
        else:
            continue
        d["_fonte"] = f.name
        partes.append(d)
    if not partes:
        sys.exit("Nenhuma fonte de rentals encontrada na pasta de entrada.")

    for p in partes:
        falta = [c for c in COLS_RENTALS if c not in p.columns]
        if falta:
            sys.exit(f"Fonte {p['_fonte'].iat[0]} sem colunas: {falta}")

    r = pd.concat([p[COLS_RENTALS + ["_fonte"]] for p in partes], ignore_index=True)
    log.add("Linhas de rentals lidas", len(r), detalhe=f"{len(partes)} fonte(s)")

    for c in ["Check-out Date", "Check-in Date"]:
        r[c] = pd.to_datetime(r[c], errors="coerce", dayfirst=True)
    for c in ["Days", "Net Rental", "Damages", "Net", "Accrued days"]:
        r[c] = pd.to_numeric(r[c], errors="coerce").fillna(0)
    datas_invalidas = r["Check-in Date"].isna().sum() + r["Check-out Date"].isna().sum()
    log.add("Datas inválidas", int(datas_invalidas),
            "OK" if datas_invalidas == 0 else "AVISO")

    for c in ["Check-out User", "Check-in User", "Booking User"]:
        r[c] = r[c].map(norm_nome)
    for c in ["Check-out station", "Check-in station", "Agr. No", "Rate code"]:
        r[c] = r[c].astype(str).str.strip()
    r["Corporate"] = r["Corporate"].map(norm_texto_vazio)

    # contratos repetidos: o mais recente (última fonte) prevalece
    antes = len(r)
    r = r.drop_duplicates(subset="Agr. No", keep="last")
    dup = antes - len(r)
    log.add("Contratos duplicados removidos (Agr. No)", dup,
            "OK" if dup == 0 else "AVISO",
            "o Excel original conta estes contratos 2 vezes" if dup else "")

    fora = ~r["Check-out station"].isin(ESTACOES) | ~r["Check-in station"].isin(ESTACOES)
    log.add("Linhas com estação desconhecida", int(fora.sum()),
            "OK" if fora.sum() == 0 else "AVISO")
    return r


def aplicar_exclusoes(r: pd.DataFrame, pasta: Path, log: Log) -> pd.DataFrame:
    f = pasta / "exclusoes.csv"
    if not f.exists():
        log.add("Exclusões autorizadas", 0, "AVISO",
                "exclusoes.csv não encontrado — nenhum contrato excluído")
        return r
    ex = pd.read_csv(f, sep=None, engine="python")
    ids = set(ex.iloc[:, 0].astype(str).str.strip())
    n = r["Agr. No"].isin(ids).sum()
    log.add("Exclusões autorizadas", int(n), detalhe=f"{len(ids)} IDs na lista")
    return r[~r["Agr. No"].isin(ids)]


def ler_fleet(backup, pasta: Path, log: Log) -> pd.DataFrame:
    f = pasta / "fleet.xlsx"
    if f.exists():
        fl = pd.read_excel(f)
    elif backup:
        fl = pd.read_excel(backup, sheet_name="Fleet")
    else:
        log.add("Fleet", "sem dados", "AVISO")
        return pd.DataFrame(columns=["ano", "mes", "est", "frota", "dias_aluguer", "util"])
    fl = fl.rename(columns={"Ano": "ano", "Mês Nº": "mes", "Estação": "est",
                            "Fleet Units": "frota", "On Rent Days": "dias_aluguer",
                            "Utilization Rate": "util"})
    # Portugal é recalculado como soma das estações (evita duplicação e a
    # inconsistência de abril/2025 identificada no trabalho)
    fl = fl[fl["est"].isin(ESTACOES)].copy()
    fl = fl[(fl["frota"].fillna(0) > 0)]
    fl["dias_mes"] = [calendar.monthrange(int(a), int(m))[1] for a, m in zip(fl.ano, fl.mes)]
    fl["frota_dias"] = fl["frota"] * fl["dias_mes"]
    log.add("Linhas de frota válidas", len(fl))
    return fl[["ano", "mes", "est", "frota", "dias_aluguer", "util", "frota_dias"]]


def ler_ocs(backup, pasta: Path, log: Log) -> pd.DataFrame:
    f = pasta / "ocs.xlsx"
    if f.exists():
        o = pd.read_excel(f)
    elif backup:
        o = pd.read_excel(backup, sheet_name="OCS_Mensal")
    else:
        return pd.DataFrame()
    o = o.rename(columns={"Ano": "ano", "Mês Nº": "mes", "Código": "est",
                          "Booking Score": "bk", "Nº Reviews Booking": "bk_n",
                          "Google Score": "gg", "Nº Reviews Google": "gg_n"})
    o = o.dropna(subset=["bk", "gg"], how="all")
    log.add("Meses×estação com avaliações OCS", len(o))
    return o[["ano", "mes", "est", "bk", "bk_n", "gg", "gg_n"]]


def ler_incremental(backup, pasta: Path, log: Log) -> pd.DataFrame:
    """Input manual de Incremental Sales (tbInputVendas, Vendas_Colaborador!L:Q).
    A chave 'Ano|Mês|Código|Colaborador' é a fonte de verdade (algumas linhas
    não têm as colunas auxiliares preenchidas)."""
    f = pasta / "incremental_sales.xlsx"
    if f.exists():
        v = pd.read_excel(f)
    elif backup:
        v = pd.read_excel(backup, sheet_name="Vendas_Colaborador", usecols="L:Q")
    else:
        return pd.DataFrame(columns=["ano", "mes", "est", "colab", "inc"])
    v.columns = ["chave", "a", "m", "c", "colab", "inc"][: len(v.columns)]
    v = v.dropna(subset=["chave"])
    partes = v["chave"].astype(str).str.split("|", n=3, expand=True)
    out = pd.DataFrame({
        "ano": pd.to_numeric(partes[0], errors="coerce"),
        "mes": pd.to_numeric(partes[1], errors="coerce"),
        "est": partes[2].str.strip(),
        "colab": partes[3].map(norm_nome),
        "inc": pd.to_numeric(v["inc"], errors="coerce").fillna(0),
    }).dropna(subset=["ano", "mes"])
    out = out.groupby(["ano", "mes", "est", "colab"], as_index=False)["inc"].sum()
    log.add("Linhas de Incremental Sales (input)", len(out),
            detalhe=f"total {out['inc'].sum():,.2f} €")
    return out


# ---------------------------------------------------------------- extras
def ler_extras(pasta: Path, log: Log):
    """Extra Sales Reports do WheelSys. Regras (trabalho ISCTE, secção 5):
    - só VV é obrigatório → fora do mérito comercial
    - valor positivo com Employee = venda de balcão; zero não é venda
    - estornos abatem; venda totalmente estornada deixa de contar
    - FCI tratado como pacote; FDW zero não é venda
    - ausência de linha ≠ cliente não comprou
    Implementação concluída quando as colunas do relatório forem confirmadas.
    """
    ficheiros = sorted((pasta / "extras").glob("*.xlsx"))
    if not ficheiros:
        log.add("Extra Sales Reports", 0, "AVISO",
                "sem ficheiros em entrada/extras — separador Extras sem dados")
        return None
    return None  # preenchido no passo seguinte


# ---------------------------------------------------------------- agregação
def agrega(df, data_col, est_col, user_col, medidas: dict) -> pd.DataFrame:
    g = df.assign(ano=df[data_col].dt.year, mes=df[data_col].dt.month,
                  est=df[est_col], colab=df[user_col])
    return g.groupby(["ano", "mes", "est", "colab"], as_index=False).agg(**medidas)


def construir_factos(r: pd.DataFrame, inc: pd.DataFrame) -> pd.DataFrame:
    # Receita, Net Rental e Rental Days: mês da Check-in Date, Check-out
    # station, colaborador = Check-out User (manual secções 1, 6.4, 8)
    rec = agrega(r, "Check-in Date", "Check-out station", "Check-out User", {
        "turnover": ("Net", "sum"), "net_rental": ("Net Rental", "sum"),
        "rental_days": ("Days", "sum")})
    # Contratos abertos: Check-out Date + Check-out station + Check-out User
    ab = agrega(r, "Check-out Date", "Check-out station", "Check-out User", {
        "abertos": ("Agr. No", "count")})
    # Contratos fechados e danos: Check-in Date + Check-in station + Check-in User
    fe = agrega(r, "Check-in Date", "Check-in station", "Check-in User", {
        "fechados": ("Agr. No", "count"), "danos": ("Damages", "sum")})
    # Diretos: Net Rental, Booking User, Rate code DIRETOS, Corporate vazio,
    # Check-in Date, Check-out station (manual secção 8)
    d = r[(r["Rate code"] == "DIRETOS") & (r["Corporate"] == "")]
    di = agrega(d, "Check-in Date", "Check-out station", "Booking User", {
        "diretos": ("Net Rental", "sum")})

    chaves = ["ano", "mes", "est", "colab"]
    f = rec
    for t in (ab, fe, di, inc):
        f = f.merge(t, on=chaves, how="outer")
    num = ["turnover", "net_rental", "rental_days", "abertos", "fechados",
           "danos", "diretos", "inc"]
    f[num] = f[num].fillna(0)
    f = f[f["est"].isin(ESTACOES)]
    f["ano"] = f["ano"].astype(int)
    f["mes"] = f["mes"].astype(int)
    return f.sort_values(chaves).reset_index(drop=True)


# ---------------------------------------------------------------- saída
def para_json(f, fleet, ocs, extras, meta) -> dict:
    colabs = sorted(c for c in f["colab"].unique())
    est = list(ESTACOES)
    ci = {c: i for i, c in enumerate(colabs)}
    ei = {e: i for i, e in enumerate(est)}
    medidas = ["turnover", "net_rental", "rental_days", "abertos", "fechados",
               "danos", "diretos", "inc"]
    linhas = []
    for row in f.itertuples(index=False):
        linhas.append([row.ano, row.mes, ei[row.est], ci[row.colab]] +
                      [round(float(getattr(row, m)), 2) for m in medidas])
    return {
        "meta": meta,
        "estacoes": [{"cod": e, "nome": ESTACOES[e]} for e in est],
        "meses": MESES,
        "colaboradores": colabs,
        "sistema": [c for c in colabs if c.lower() in UTILIZADORES_SISTEMA or c == SEM_COLAB],
        "campos": ["ano", "mes", "est", "colab"] + medidas,
        "factos": linhas,
        "frota": [[int(x.ano), int(x.mes), ei[x.est], float(x.frota),
                   float(x.dias_aluguer or 0), float(x.frota_dias),
                   None if pd.isna(x.util) else float(x.util)]
                  for x in fleet.itertuples(index=False)],
        "ocs": [[int(x.ano), int(x.mes), ei[x.est], float(x.bk or 0), float(x.bk_n or 0),
                 float(x.gg or 0), float(x.gg_n or 0)]
                for x in ocs.fillna(0).itertuples(index=False)] if len(ocs) else [],
        "extras": extras,
    }


def reconciliar(r, f, log: Log):
    """Somas por mês antes e depois da agregação têm de coincidir."""
    m = r.assign(ano=r["Check-in Date"].dt.year, mes=r["Check-in Date"].dt.month)
    a = m.groupby(["ano", "mes"])[["Net", "Net Rental", "Days"]].sum()
    b = f.groupby(["ano", "mes"])[["turnover", "net_rental", "rental_days"]].sum()
    j = a.join(b, how="outer").fillna(0)
    dif = (j["Net"] - j["turnover"]).abs().max() + (j["Days"] - j["rental_days"]).abs().max()
    log.add("Reconciliação receita/dias (fonte vs agregado)",
            f"diferença máx. {dif:.4f}", "OK" if dif < 0.01 else "ERRO")
    return j.reset_index()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default=str(AQUI / "entrada"))
    ap.add_argument("--saida", default=str(AQUI / "saida"))
    a = ap.parse_args()
    pasta, saida = Path(a.entrada), Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    log = Log()

    print("ICONIQ | atualização do painel")
    backup = ler_backup(pasta)
    r = ler_rentals(pasta, backup, log)
    r = aplicar_exclusoes(r, pasta, log)
    fleet = ler_fleet(backup, pasta, log)
    ocs = ler_ocs(backup, pasta, log)
    inc = ler_incremental(backup, pasta, log)
    extras = ler_extras(pasta, log)

    f = construir_factos(r, inc)
    rec = reconciliar(r, f, log)

    sem_rd = f[(f["inc"] > 0) & (f["rental_days"] == 0)]
    log.add("Incremental Sales sem Rental Days do colaborador", len(sem_rd),
            "OK" if sem_rd.empty else "AVISO",
            "; ".join(f"{x.ano}/{x.mes} {x.est} {x.colab}" for x in sem_rd.head(8).itertuples()))

    ult = r["Check-in Date"].max()
    meta = {"gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "dados_ate": ult.strftime("%Y-%m-%d"),
            "contratos": int(len(r)),
            "fontes": sorted(r["_fonte"].unique().tolist())}
    dados = para_json(f, fleet, ocs, extras, meta)

    (saida / "dados_dashboard.json").write_text(
        json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    modelo = AQUI / "modelo" / "dashboard_template.html"
    if modelo.exists():
        html = modelo.read_text(encoding="utf-8").replace(
            "/*__DADOS__*/null", json.dumps(dados, ensure_ascii=False, separators=(",", ":")))
        (saida / "Dashboard_ICONIQ.html").write_text(html, encoding="utf-8")
        log.add("Dashboard gerado", "saida/Dashboard_ICONIQ.html")

    with pd.ExcelWriter(saida / "validacao.xlsx") as xw:
        pd.DataFrame(log.linhas).to_excel(xw, sheet_name="Controlos", index=False)
        rec.to_excel(xw, sheet_name="Reconciliação_mensal", index=False)
        f.to_excel(xw, sheet_name="Factos_colaborador", index=False)
        fleet.to_excel(xw, sheet_name="Frota", index=False)
    print(f"Concluído: dados até {meta['dados_ate']}, {meta['contratos']} contratos.")


if __name__ == "__main__":
    main()
