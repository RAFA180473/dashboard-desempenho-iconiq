/* ICONIQ | Coletor WheelSys  v1
 * Corre dentro de um separador do WheelSys (iconiqfleet.wheelsys.io/ui/...) com sessão iniciada.
 * Usa os mesmos pedidos que os relatórios do ecrã (só leitura) e agrega por mês × estação × colaborador.
 * Não guarda dados pessoais de clientes (nomes, matrículas, emails): só totais.
 *
 * Uso: ICQ_RUN({de:'2025-01', ate:'2026-09', frota:true})
 *  - estado em window.ICQ.status ('a correr' | 'pronto' | 'erro: ...')
 *  - quando pronto, aparece no topo da página o botão "Copiar dados ICONIQ"
 */
(function () {
  const EP = '/ui/reports/exreportpreview.aspx/GenerateReportData';
  const EXCL = new Set(['VV', 'TOLLS', 'TOLL6']);           // obrigatório + portagens: fora das vendas opcionais
  const SIS = /^(account system)?$/i;                        // vendas online / sem colaborador
  const nome = s => String(s == null ? '' : s).replace(/\s+/g, ' ').trim() || '(sem colaborador)';
  const est = s => { s = String(s || '').toUpperCase().trim();
    if (['LXAAPT', 'OPTAPT', 'FAOAPT'].includes(s)) return s;
    s = s.toLowerCase();
    if (s.includes('lisb')) return 'LXAAPT'; if (s.includes('oport') || s.includes('porto')) return 'OPTAPT';
    if (s.includes('faro')) return 'FAOAPT'; return null; };
  const r2 = x => Math.round(x * 100) / 100;
  const F = (n, c, t, r, v, cap) => ({ FilterName: n, ControlName: c, FilterType: t, Required: r, Value: v, Caption: cap || '' });

  async function rep(browser, title, filters) {
    const body = { browser, title, filters: JSON.stringify(filters) };
    const res = await fetch(EP, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json; charset=utf-8' }, body: JSON.stringify(body) });
    if (res.status === 401 || res.redirected) throw new Error('sessão WheelSys expirada');
    if (!res.ok) throw new Error(browser + ' HTTP ' + res.status);
    const j = await res.json();
    if (String(j.d && j.d.success) !== 'true') throw new Error(browser + ': ' + (j.d && j.d.message));
    return JSON.parse(j.d.data || '[]');
  }
  // mode: '2' check-ins | '1' check-outs ; rent: '1' fechados | '3' todos
  const detalhado = (mode, range, rent) => rep('detailedrentalreport', 'Detailed Rentals Report', [
    F('mtdatemode', 'rptmtdatemode', 'ftMemTypeSingle', true, mode, 'Date selection'),
    F('dddf#dt', 'rptdddfdt', 'ftDateRange', true, range, 'Date Range'),
    F('mtstationmode', 'rptmtstationmode', 'ftMemTypeSingle', true, '2', ' Station selection'),
    F('edstations', 'rptedstations', 'ftStation', false, null, 'Stations'),
    F('groups', 'rptgroups', 'ftCarGroup', false, null, 'Groups'),
    F('rentmode', 'rptrentmode', 'ftMemTypeSingle', true, rent, 'Rentals'),
    F('edcouser', 'rptedcouser', 'ftLookupSingle', false, null, 'Check-out user'),
    F('edciuser', 'rptedciuser', 'ftLookupSingle', false, null, 'Check-in user'),
    F('agentid', 'rptagentid', 'ftBrowser', false, null, 'Agent'),
    F('corpid', 'rptcorpid', 'ftBrowser', false, null, 'Corporate'),
    F('brands', 'rptbrands', 'ftLookupSingle', false, null, 'Brand')]);
  // lista por Check-outs, utilizador = "Sold by"
  const extras = range => rep('extrasalesrpt', 'Extra Sales Report', [
    F('mtlisttype', 'rptmtlisttype', 'ftMemTypeSingle', true, '1', 'List type'),
    F('dddf#dt', 'rptdddfdt', 'ftDateRange', true, range, 'Date'),
    F('edstations', 'rptedstations', 'ftStation', false, null, 'Stations'),
    F('edextras', 'rptedextras', 'ftLookupMulti', false, '', 'Insurances & Options'),
    F('edusers', 'rptedusers', 'ftLookupMulti', false, '', 'Users'),
    F('mtsalesusertype', 'rptmtsalesusertype', 'ftMemTypeSingle', true, '1', 'Sales User')]);
  const incremental = range => rep('incrementalsalesrpt', 'Incremental Sales Report', [
    F('dddf#dt', 'rptdddfdt', 'ftDateRange', true, range, 'Date'),
    F('edstations', 'rptedstations', 'ftStation', false, null, 'Stations'),
    F('edextras', 'rptedextras', 'ftLookupMulti', false, '', 'Insurances & Options'),
    F('edusers', 'rptedusers', 'ftLookupMulti', false, '', 'Users'),
    F('includedesk', 'rptincludedesk', 'ftBoolean', false, false, 'Include additional desk-users')]);
  const frota = range => rep('fleetutilizationreport', 'Fleet Utilization Report', [
    F('dddf#dt', 'rptdddfdt', 'ftDateRange', true, range, 'Date basis'),
    F('edstations', 'rptedstations', 'ftStation', false, null, 'Stations'),
    F('edgroups', 'rptedgroups', 'ftCarGroup', false, null, 'Groups'),
    F('edownerships', 'rptedownerships', 'ftMemTypeMulti', false, '', 'Ownership'),
    F('edpooltypes', 'rptedpooltypes', 'ftMemTypeMulti', false, '', 'Pool type'),
    F('edstates', 'rptedstates', 'ftMemTypeMulti', false, '', 'States'),
    F('utiltype', 'rptutiltype', 'ftMemTypeSingle', true, '0', 'Utilization')]);

  // colunas da linha de factos (f)
  const M = ['turnover', 'net_rental', 'rental_days', 'abertos', 'fechados', 'danos', 'diretos', 'inc',
             'c_venda', 'r_extras', 'dias_abertos', 'vv', 'vv_ctr'];
  const IX = Object.fromEntries(M.map((m, i) => [m, i]));

  async function mes(y, m, opt) {
    const last = new Date(y, m, 0).getDate(), mm = String(m).padStart(2, '0');
    const range = `${y}-${mm}-01|${y}-${mm}-${last}`;
    const acc = new Map(), prod = new Map(), ctrl = {};
    const add = (e, c, k, v) => { if (!e) return; const key = e + '|' + nome(c);
      if (!acc.has(key)) acc.set(key, new Array(M.length).fill(0)); acc.get(key)[IX[k]] += v; };

    // 1) contratos fechados no mês (Check-in Date): receita, dias, fechados, danos, diretos
    const A = await detalhado('2', range, '1'); const vistos = new Set();
    for (const r of A) {
      if (vistos.has(r.radocno)) continue; vistos.add(r.radocno);
      const eo = est(r.stationfrom), ei = est(r.stationto);
      add(eo, r.user_from_name || r.user_from, 'turnover', +r.chargenet || 0);
      add(eo, r.user_from_name || r.user_from, 'net_rental', +r.chargesubdisc || 0);
      add(eo, r.user_from_name || r.user_from, 'rental_days', +r.duration || 0);
      const vv = (+r.charge_vv || 0) + (+r.charge_vv2 || 0);       // Via Verde faturada no contrato
      add(eo, r.user_from_name || r.user_from, 'vv', vv); if (vv > 0) add(eo, r.user_from_name || r.user_from, 'vv_ctr', 1);
      add(ei, r.user_to_name, 'fechados', 1);
      add(ei, r.user_to_name, 'danos', +r.chargedamage || 0);
      if (r.ratecode === 'DIRETOS' && !String(r.corporate_name || '').trim())
        add(eo, r.user_res_name, 'diretos', +r.chargesubdisc || 0);
    }
    ctrl.fechados = vistos.size;
    const linhas = opt.linhas ? [...new Map(A.map(r => [r.radocno, r])).values()].map(r => [
      r.datefrom, r.dateto, +r.duration || 0, r.stationfrom, r.stationto, +r.chargesubdisc || 0, +r.chargedamage || 0, +r.chargenet || 0,
      nome(r.user_from_name || r.user_from), nome(r.user_to_name), r.radocno, +r.accrued_days || 0, nome(r.user_res_name),
      String(r.corporate_name || '').trim() || null, r.ratecode, (+r.charge_vv || 0) + (+r.charge_vv2 || 0)]) : null;
    // índice contrato → colaborador do check-out (liga as respostas do Customer Verdict ao colaborador)
    const us = [], ui = {}, raIdx = [];
    for (const r of A) { const n = String(r.radocno || ''); if (!/^RNT-\d+$/.test(n)) continue;
      const u = nome(r.user_from_name || r.user_from); if (ui[u] == null) { ui[u] = us.length; us.push(u); }
      raIdx.push([+n.slice(4), ui[u]]); }
    // 2) contratos abertos no mês (Check-out Date, todos os estados)
    const B = await detalhado('1', range, '3'); const ab = new Set();
    for (const r of B) { if (ab.has(r.radocno)) continue; ab.add(r.radocno);
      add(est(r.stationfrom), r.user_from_name || r.user_from, 'abertos', 1);
      add(est(r.stationfrom), r.user_from_name || r.user_from, 'dias_abertos', +r.duration || 0); }
    ctrl.abertos = ab.size;
    // contratos abertos no mês e ainda em aluguer (estado RUN/PRE)
    const at = {}; for (const r of new Map(B.map(x => [x.radocno, x])).values()) {
      if (String(r.sstr || '').toUpperCase() === 'IN') continue;
      const k = est(r.stationfrom) + '|' + nome(r.user_from_name || r.user_from); at[k] = (at[k] || 0) + 1; }
    const ativ = Object.entries(at).filter(([k]) => !k.startsWith('null')).map(([k, v]) => [...k.split('|'), v]);
    // 3) extras opcionais vendidos ao balcão (Check-outs, Sold by). Estornos abatem; zero não é venda.
    const E = await extras(range); const g = new Map();
    for (const r of E) {
      const code = String(r.extra_code || '').toUpperCase(); if (EXCL.has(code)) continue;
      const k = r.rnt_docno + '|' + code;
      if (!g.has(k)) g.set(k, { rnt: r.rnt_docno, code, net: 0, best: 0, emp: '', est: est(r.stationfromname) });
      const o = g.get(k); const v = +r.revenue || 0; o.net += v;
      if (v > o.best) { o.best = v; o.emp = nome(r.employee_name); }
    }
    const vendaPor = new Map(); // est|colab -> Set(contratos)
    for (const o of g.values()) {
      if (o.net <= 0.005 || SIS.test(o.emp) || o.emp === '(sem colaborador)' || !o.est) continue;
      const key = o.est + '|' + o.emp;
      if (!vendaPor.has(key)) vendaPor.set(key, new Set()); vendaPor.get(key).add(o.rnt);
      add(o.est, o.emp, 'r_extras', o.net);
      const pk = key + '|' + o.code; const p = prod.get(pk) || [0, 0]; p[0] += 1; p[1] += o.net; prod.set(pk, p);
    }
    for (const [key, set] of vendaPor) { const [e, c] = key.split('|'); add(e, c, 'c_venda', set.size); }
    ctrl.linhas_extras = E.length;
    // 4) Incremental Sales (relatório WheelSys)
    const I = await incremental(range);
    for (const r of I) add(est(r.stationcode), r.employee, 'inc', +r.total || 0);
    // 5) frota e ocupação (opcional; relatório lento)
    let fl = null;
    if (opt.frota) { try { fl = agregaFrota(await frota(range), last); } catch (e) { ctrl.frota_erro = String(e.message || e); } }

    const f = [...acc.entries()].map(([k, v]) => { const [e, c] = k.split('|'); return [e, c, ...v.map(r2)]; });
    const p = [...prod.entries()].map(([k, v]) => { const [e, c, code] = k.split('|'); return [e, c, code, v[0], r2(v[1])]; });
    const ate = (() => { const d = new Date(); d.setDate(d.getDate() - 1); const lim = `${y}-${mm}-${String(last).padStart(2,'0')}`; const iso = d.toISOString().slice(0, 10); return iso < lim ? iso : lim; })();
    return { f, p, fl, ctrl, ate, ra: { u: us, r: raIdx }, linhas, ativ };
  }

  // Fleet Utilization Report: uma linha por viatura → frota média e dias em aluguer por estação
  function agregaFrota(rows, diasMes) {
    if (!rows.length) return [];
    const k = Object.keys(rows[0]);
    const pick = (...c) => c.find(x => k.includes(x));
    const kEst = pick('stationcode', 'homestation', 'station', 'stationname', 'currentstation');
    const kRent = pick('rentaldays', 'daysonrent', 'onrentdays', 'rented', 'rentdays');
    const kAvail = pick('avdays', 'availabledays', 'daysavailable', 'fleetdays', 'availdays', 'indays');
    const by = {};
    for (const r of rows) { const e = est(r[kEst]); if (!e) continue;
      by[e] = by[e] || [0, 0]; by[e][0] += +r[kAvail] || 0; by[e][1] += +r[kRent] || 0; }
    return Object.entries(by).map(([e, v]) => [e, r2(v[0] / diasMes), r2(v[1]), v[0] ? r2(v[1] / v[0]) : null]);
  }

  window.ICQ_RUN = async function (opt) {
    opt = Object.assign({ frota: true, linhas: false }, opt || {});
    const ICQ = window.ICQ = { status: 'a correr', feito: [], erros: [], result: null };
    const [y0, m0] = opt.de.split('-').map(Number), [y1, m1] = opt.ate.split('-').map(Number);
    const out = { v: 1, origem: 'wheelsys', gerado: new Date().toISOString().slice(0, 16), meses: {}, fechar: opt.fechar || [] };
    try {
      for (let y = y0, m = m0; y < y1 || (y === y1 && m <= m1); m === 12 ? (y++, m = 1) : m++) {
        const key = `${y}-${String(m).padStart(2, '0')}`; ICQ.status = 'a correr ' + key;
        out.meses[key] = await mes(y, m, opt); ICQ.feito.push(key);
      }
      ICQ.result = JSON.stringify(out); ICQ.status = 'pronto';
      botao(ICQ.result, ICQ.feito.length);
    } catch (e) { ICQ.status = 'erro: ' + (e.message || e); }
    return ICQ.status;
  };

  function botao(txt, n) {
    let b = document.getElementById('icq-copy');
    if (!b) { b = document.createElement('button'); b.id = 'icq-copy';
      b.style.cssText = 'position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:99999;padding:12px 22px;font:600 15px system-ui;background:#2a78d6;color:#fff;border:0;border-radius:8px;box-shadow:0 4px 18px rgba(0,0,0,.25);cursor:pointer';
      document.body.appendChild(b); }
    b.textContent = `Copiar dados ICONIQ (${n} meses, ${Math.round(txt.length / 1024)} KB)`;
    b.onclick = async () => {
      try { await navigator.clipboard.writeText(txt); b.textContent = 'Copiado ✓'; window.ICQ.copiado = true; }
      catch (e) { const t = document.createElement('textarea'); t.value = txt; document.body.appendChild(t); t.select();
        const ok = document.execCommand('copy'); t.remove(); b.textContent = ok ? 'Copiado ✓' : 'Falhou a cópia'; window.ICQ.copiado = ok; }
    };
  }
  return 'coletor carregado';
})();
