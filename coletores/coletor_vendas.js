/* ICONIQ | Coletor "Vendas · quadro mensal"  v1.0 (17/11/2026)
 * Reproduz o Excel IRPD: Extra Sales Report, List type Check-outs (1), Sales User "Sold by" (1), todas as estações e utilizadores,
 * extras RAP, FCI, CBORD, WUG, UPGR, FDW, ADD, PPW e RDW. Só leitura; não guarda dados de clientes (só totais por colaborador).
 * Corre num separador do WheelSys (iconiqfleet.wheelsys.io/ui/) com sessão iniciada.
 *
 * Uso: await ICQ_VENDAS({de:'2026-07', ate:'2026-11-16', lista:[["Amaral Lívia","LXAAPT"], ...]})
 *   de    = primeiro mês de check-out a ler (AAAA-MM)
 *   ate   = último dia de check-out a ler (AAAA-MM-DD, normalmente ontem)
 *   lista = colaboradores ativos e loja (config/vendas do dashboard), só para o resumo
 * Devolve um resumo (JSON) e deixa em window.ICQV.docs[AAAA-MM] o texto de cada documento da coleção "vendas" do dashboard:
 *   {v:1, u:[colaboradores], m:[meses da Check-in Date], k:[extras], a:"u.m.k.nº linhas.cêntimos ...", c:"u.m.nº contratos ...", ate}
 * idx[AAAA-MM] = [hash do conteúdo, comprimento do texto, checksum do texto, nº de linhas do relatório]
 */
window.ICQ_VENDAS = async function (opt) {
  const K = ['RAP', 'FCI', 'CBORD', 'WUG', 'UPGR', 'FDW', 'ADD', 'PPW', 'RDW'], KS = new Set(K);
  const F = (n, c, t, r, v, cap) => ({ FilterName: n, ControlName: c, FilterType: t, Required: r, Value: v, Caption: cap || '' });
  const rep = async range => {
    const body = { browser: 'extrasalesrpt', title: 'Extra Sales Report', filters: JSON.stringify([
      F('mtlisttype', 'rptmtlisttype', 'ftMemTypeSingle', true, '1', 'List type'),
      F('dddf#dt', 'rptdddfdt', 'ftDateRange', true, range, 'Date'),
      F('edstations', 'rptedstations', 'ftStation', false, null, 'Stations'),
      F('edextras', 'rptedextras', 'ftLookupMulti', false, '', 'Insurances & Options'),
      F('edusers', 'rptedusers', 'ftLookupMulti', false, '', 'Users'),
      F('mtsalesusertype', 'rptmtsalesusertype', 'ftMemTypeSingle', true, '1', 'Sales User')]) };
    const res = await fetch('/ui/reports/exreportpreview.aspx/GenerateReportData', { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(body) });
    if (res.status === 401 || res.redirected) throw new Error('sessão WheelSys expirada');
    if (!res.ok) throw new Error('Extra Sales Report HTTP ' + res.status);
    let j; try { j = await res.json(); } catch (e) { throw new Error('sessão WheelSys expirada (resposta sem dados)'); }
    if (String(j.d && j.d.success) !== 'true') throw new Error('Extra Sales Report: ' + (j.d && j.d.message));
    return JSON.parse(j.d.data || '[]');
  };
  const nz = x => String(x == null ? '' : x).replace(/\s+/g, ' ').trim() || '(sem colaborador)';
  const nzk = x => String(x).normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
  const h = s => { let x = 0; for (let i = 0; i < s.length; i++) x = (x * 31 + s.charCodeAt(i)) % 1000000007; return x; };
  const ate = opt.ate, mesRes = opt.mes || ate.slice(0, 7);
  const [y0, m0] = opt.de.split('-').map(Number), [y1, m1] = ate.split('-').map(Number);
  const lista = new Map((opt.lista || []).map(r => [nzk(r[0]), r[1]]));
  const out = { docs: {}, idx: {} }, tot = { LXAAPT: 0, OPTAPT: 0, FAOAPT: 0, fora: 0 }, por = {};
  for (let y = y0, m = m0; y < y1 || (y === y1 && m <= m1); m === 12 ? (y++, m = 1) : m++) {
    const key = `${y}-${String(m).padStart(2, '0')}`;
    const last = key === ate.slice(0, 7) ? ate : `${key}-${String(new Date(y, m, 0).getDate()).padStart(2, '0')}`;
    const rows = await rep(`${key}-01|${last}`);
    const u = [], ui = {}, a = new Map(), c = new Map();
    for (const r of rows) {
      const code = String(r.extra_code || '').toUpperCase(); if (!KS.has(code)) continue;
      const n = nz(r.employee_name); if (ui[n] == null) { ui[n] = u.length; u.push(n); }
      const ci = String(r.dateto || '').slice(0, 7), cents = Math.round((+r.revenue || 0) * 100);
      const k = ui[n] + '|' + ci + '|' + code, o = a.get(k) || [0, 0]; o[0]++; o[1] += cents; a.set(k, o);
      const ck = ui[n] + '|' + ci; if (!c.has(ck)) c.set(ck, new Set()); c.get(ck).add(r.rnt_docno);
      if (ci === mesRes) { const lj = lista.get(nzk(n)); if (lj && tot[lj] != null) { tot[lj] += cents; por[n] = (por[n] || 0) + cents; } else tot.fora += cents; }
    }
    const ms = [...new Set([...a.keys()].map(k => k.split('|')[1]))].sort(), mi = Object.fromEntries(ms.map((x, i) => [x, i]));
    const ki = Object.fromEntries(K.map((x, i) => [x, i]));
    const d = { v: 1, u, m: ms, k: K,
      a: [...a.entries()].map(([k, o]) => { const [i, ci, code] = k.split('|'); return [i, mi[ci], ki[code], o[0], o[1]].join('.'); }).join(' '),
      c: [...c.entries()].map(([k, s]) => { const [i, ci] = k.split('|'); return [i, mi[ci], s.size].join('.'); }).join(' '),
      ate: last };
    out.docs[key] = JSON.stringify(d);
    out.idx[key] = [h(JSON.stringify([d.u, d.m, d.k, d.a, d.c])), out.docs[key].length, h(out.docs[key]), rows.length];
  }
  const e = x => Math.round(x) / 100;
  out.resumo = { mes: mesRes, ate, portugal: e(tot.LXAAPT + tot.OPTAPT + tot.FAOAPT), lisboa: e(tot.LXAAPT), porto: e(tot.OPTAPT), faro: e(tot.FAOAPT),
    fora: e(tot.fora), top: Object.entries(por).sort((x, y) => y[1] - x[1]).slice(0, 5).map(([n, v]) => [n, e(v)]) };
  window.ICQV = out;
  return JSON.stringify({ idx: out.idx, resumo: out.resumo });
};
'coletor de vendas carregado';
