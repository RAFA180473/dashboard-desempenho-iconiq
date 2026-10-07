#!/usr/bin/env python3
"""
Atualiza o Painel_ICONIQ_backup.xlsx sem o abrir com openpyxl (que apagaria a formatação condicional
e as fórmulas dinâmicas do Painel). Edita diretamente o XML de duas folhas:

  Base_Rentals        acrescenta os contratos com Check-in Date nos meses recolhidos (coluna P = Via Verde)
                      e alarga a tabela tbRentals
  Vendas_Colaborador  substitui o input posicional de Incremental Sales (coluna Q) por uma fórmula que procura
                      o valor pela chave Ano|Mês|Código|Colaborador numa tabela auxiliar (colunas Y:Z),
                      preenchida com o Incremental Sales Report do WheelSys de todos os meses recolhidos.
                      Assim os valores deixam de desalinhar quando entram colaboradores ou meses novos.

Uso: python atualizar_backup_xml.py --backup X.xlsx --dados saida/db --de 2026-08 --ate 2026-09 --saida Y.xlsx
"""
import argparse, glob, json, os, re, shutil, zipfile
from datetime import datetime
from xml.sax.saxutils import escape


def excel_serial(s):
    d = datetime.fromisoformat(str(s)[:19])
    return (d - datetime(1899, 12, 30)).total_seconds() / 86400


def cel(ref, v, style=None):
    st = f' s="{style}"' if style else ''
    if v is None or v == '':
        return ''
    if isinstance(v, (int, float)):
        return f'<c r="{ref}"{st}><v>{v}</v></c>'
    return f'<c r="{ref}"{st} t="inlineStr"><is><t xml:space="preserve">{escape(str(v))}</t></is></c>'


def norm(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--backup', required=True); ap.add_argument('--dados', required=True)
    ap.add_argument('--de', default='2026-08'); ap.add_argument('--ate', default='2026-09'); ap.add_argument('--saida', required=True)
    a = ap.parse_args()
    doc = lambda p: (lambda d: d.get('data', d))(json.load(open(p, encoding='utf-8')))

    linhas = []
    for p in sorted(glob.glob(os.path.join(a.dados, 'linhas', '*.json'))):
        d = doc(p)
        if a.de <= d['mes'] <= a.ate: linhas += d['r']
    meses = {os.path.basename(p)[:-5]: doc(p) for p in glob.glob(os.path.join(a.dados, 'meses', '*.json'))}

    z = zipfile.ZipFile(a.backup)
    files = {n: z.read(n) for n in z.namelist()}

    # ---- Base_Rentals (sheet3) ----
    s = files['xl/worksheets/sheet3.xml'].decode('utf-8')
    exist = set(re.findall(r'RNT-\d+', ''))  # placeholder (strings em sharedStrings)
    last = max(int(x) for x in re.findall(r'<row r="(\d+)"', s))
    linhas.sort(key=lambda r: str(r[1]))
    novas, n = [], last
    for r in linhas:
        n += 1
        vals = [excel_serial(r[0]), excel_serial(r[1]), r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[14], r[15] if len(r) > 15 else None]
        styles = ['1', '1', '2', None, None, '3', '3', '3', None, None, None, '2', None, None, None, '3']
        novas.append(f'<row r="{n}">' + ''.join(cel(f'{c}{n}', v, st) for c, v, st in zip('ABCDEFGHIJKLMNOP', vals, styles)) + '</row>')
    s = s.replace('</sheetData>', ''.join(novas) + '</sheetData>', 1)
    s = re.sub(r'<row r="1"([^>]*)>(.*?)</row>', lambda m: f'<row r="1"{m.group(1)}>{m.group(2)}{cel("P1", "Via Verde")}</row>' if 'r="P1"' not in m.group(2) else m.group(0), s, count=1)
    s = re.sub(r'<dimension ref="[^"]*"/>', f'<dimension ref="A1:P{n}"/>', s, count=1)
    s = s.replace('<col min="15" max="15" width="15.6328125" customWidth="1"/>', '<col min="15" max="15" width="15.6328125" customWidth="1"/><col min="16" max="16" width="13" customWidth="1"/>')
    files['xl/worksheets/sheet3.xml'] = s.encode('utf-8')
    t = files['xl/tables/table2.xml'].decode('utf-8')
    t = re.sub(r'ref="A1:O\d+"', f'ref="A1:O{n}"', t)
    files['xl/tables/table2.xml'] = t.encode('utf-8')
    print(f'Base_Rentals: +{len(linhas)} contratos (linhas {last + 1}–{n})')

    # ---- Vendas_Colaborador (sheet6): tabela auxiliar Y:Z e fórmula em Q ----
    inc = {}
    for k, d in meses.items():
        y, m = map(int, k.split('-'))
        for row in d.get('f', []):
            if len(row) > 9 and row[9]:
                key = f'{y}|{m}|{row[0]}|{norm(row[1])}'
                inc[key] = round(inc.get(key, 0) + row[9], 2)
    v = files['xl/worksheets/sheet6.xml'].decode('utf-8')
    def fq(m):
        r = m.group(1)
        return f'<c r="Q{r}"{m.group(2)}><f>IFERROR(_xlfn.XLOOKUP(TRIM(L{r}),$Y$2:$Y$5000,$Z$2:$Z$5000,0),0)</f></c>'
    v, nq = re.subn(r'<c r="Q(\d+)"((?: s="\d+")?)(?: t="\w+")?(?:/>|>.*?</c>)', lambda m: fq(m) if int(m.group(1)) > 1 else m.group(0), v)
    keys = sorted(inc)
    rows = {}
    rows[1] = cel('Y1', 'Chave (WheelSys)') + cel('Z1', 'Incremental Sales (WheelSys)')
    for i, k in enumerate(keys, start=2):
        rows[i] = cel(f'Y{i}', k) + cel(f'Z{i}', inc[k], '9')
    def colnum(ref):
        c = re.match(r'[A-Z]+', ref).group(0); n = 0
        for ch in c: n = n * 26 + ord(ch) - 64
        return n
    def addcells(m):
        r = int(m.group(1)); head, body = m.group(2), m.group(3)
        extra = rows.get(r, '')
        if 2 <= r <= 3000 and f'r="Q{r}"' not in body:
            extra += f'<c r="Q{r}" s="9"><f>IFERROR(_xlfn.XLOOKUP(TRIM(L{r}),$Y$2:$Y$5000,$Z$2:$Z$5000,0),0)</f></c>'
        if not extra: return m.group(0)
        cells = re.findall(r'<c r="[A-Z]+\d+"[^>]*?(?:/>|>.*?</c>)', body + extra, flags=re.S)
        cells.sort(key=lambda c: colnum(re.search(r'r="([A-Z]+)', c).group(1)))
        head = re.sub(r' spans="[^"]*"', '', head)
        return f'<row r="{r}"{head}>' + ''.join(cells) + '</row>'
    v = re.sub(r'<row r="(\d+)"([^>]*)>(.*?)</row>', addcells, v, flags=re.S)
    files['xl/worksheets/sheet6.xml'] = v.encode('utf-8')
    print(f'Vendas_Colaborador: {nq} células Q com fórmula; {len(keys)} chaves WheelSys em Y:Z')

    # ---- forçar recálculo completo e remover calcChain ----
    files.pop('xl/calcChain.xml', None)
    files['xl/_rels/workbook.xml.rels'] = re.sub(rb'<Relationship [^>]*calcChain[^>]*/>', b'', files['xl/_rels/workbook.xml.rels'])
    files['[Content_Types].xml'] = re.sub(rb'<Override [^>]*calcChain[^>]*/>', b'', files['[Content_Types].xml'])
    w = files['xl/workbook.xml'].decode('utf-8')
    w = re.sub(r'<calcPr([^>]*?)/>', lambda m: '<calcPr' + re.sub(r' fullCalcOnLoad="\w+"', '', m.group(1)) + ' fullCalcOnLoad="1"/>', w)
    files['xl/workbook.xml'] = w.encode('utf-8')

    with zipfile.ZipFile(a.saida, 'w', zipfile.ZIP_DEFLATED) as out:
        for name in z.namelist():
            if name in files: out.writestr(name, files[name])
    print('Gravado:', a.saida)


if __name__ == '__main__':
    main()
