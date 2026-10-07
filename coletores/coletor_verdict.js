/* ICONIQ | Coletor Customer Verdict  v1
 * Corre num separador de https://dashboard.customer-verdict.com/autounion/export com sessão iniciada.
 * Pede o CSV de respostas (o mesmo do botão Download) sem o gravar em disco, e agrega por mês × estação.
 * Não guarda dados pessoais: nomes, emails e comentários são descartados; fica só a contagem e as notas.
 * Mês = mês da Survey Completed Date (igual ao dashboard do Customer Verdict). Estação = Checkout Branch Code.
 * Uso: await ICV_RUN({de:'2025-01-01', ate:'2026-10-07'})  → window.ICV.status 'pronto' e botão "Copiar dados Verdict".
 * Linha verR (uma por resposta, sem nomes/emails/comentários): [nº do contrato RNT, estação, recomendação, reserva,
 *   levantamento, estado do carro, limpeza, devolução]  (notas 0-10; null = sem resposta)
 */
(function () {
  function parse(t) { const rows = []; let row = [], f = '', q = false;
    for (let i = 0; i < t.length; i++) { const c = t[i];
      if (q) { if (c == '"') { if (t[i + 1] == '"') { f += '"'; i++; } else q = false; } else f += c; }
      else { if (c == '"') q = true; else if (c == ',') { row.push(f); f = ''; } else if (c == '\n') { row.push(f); rows.push(row); row = []; f = ''; } else if (c != '\r') f += c; } }
    if (f || row.length) { row.push(f); rows.push(row); } return rows; }
  const EST = { LXAAPT: 1, OPTAPT: 1, FAOAPT: 1 };
  const ITENS = ['Reservation Process', 'Pickup process', 'Vehicle condition', 'Vehicle cleanliness', 'Return process'];
  window.ICV_RUN = async function (opt) {
    const ICV = window.ICV = { status: 'a correr' };
    try {
      const body = new URLSearchParams({ 'start-date': opt.de, 'end-date': opt.ate });
      const r = await fetch('/autounion/export/download', { method: 'POST', body, credentials: 'same-origin' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const t = await r.text(); if (/<html/i.test(t.slice(0, 200))) throw new Error('sessão Customer Verdict expirada');
      const R = parse(t), H = R[0].map(h => h.replace(/^﻿/, '').trim()), D = R.slice(1).filter(x => x.length > 10);
      const ix = n => H.indexOf(n), iRec = ix('Recommend AutoUnion'), iDate = ix('Survey Completed Date'), iBr = ix('Checkout Branch Code');
      const iIt = ITENS.map(ix); if (iRec < 0 || iDate < 0 || iBr < 0) throw new Error('colunas do CSV mudaram');
      const iRA = ix('RA Number'), nb = v => { const f = parseFloat(v); return isNaN(f) ? null : f; };
      const out = { v: 1, origem: 'customer-verdict', gerado: new Date().toISOString().slice(0, 16), meses: {} }; let usadas = 0;
      for (const x of D) {
        const est = String(x[iBr]).replace(/^'/, '').split('-').pop().trim(); if (!EST[est]) continue;
        const k = String(x[iDate]).slice(0, 7); if (!/^\d{4}-\d{2}$/.test(k)) continue;
        const ra = /^RNT-\d+$/.test(x[iRA]) ? +x[iRA].slice(4) : null;
        (out.meses[k] = out.meses[k] || { verR: [] }).verR.push([ra, est, nb(x[iRec]), ...iIt.map(j => nb(x[j]))]); usadas++;
      }
      const meses = out.meses;
      ICV.out = out; ICV.result = JSON.stringify(out); ICV.status = 'pronto'; ICV.respostas = usadas;
      let b = document.getElementById('icv-copy');
      if (!b) { b = document.createElement('button'); b.id = 'icv-copy';
        b.style.cssText = 'position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:99999;padding:12px 22px;font:600 15px system-ui;background:#2a78d6;color:#fff;border:0;border-radius:8px;cursor:pointer';
        document.body.appendChild(b); }
      b.textContent = `Copiar dados Verdict (${Object.keys(meses).length} meses, ${usadas} respostas)`;
      b.onclick = async () => { try { await navigator.clipboard.writeText(ICV.result); b.textContent = 'Copiado ✓'; ICV.copiado = true; }
        catch (e) { const ta = document.createElement('textarea'); ta.value = ICV.result; document.body.appendChild(ta); ta.select();
          ICV.copiado = document.execCommand('copy'); ta.remove(); b.textContent = ICV.copiado ? 'Copiado ✓' : 'Falhou a cópia'; } };
    } catch (e) { ICV.status = 'erro: ' + (e.message || e); }
    return ICV.status;
  };
  return 'coletor Verdict carregado';
})();
