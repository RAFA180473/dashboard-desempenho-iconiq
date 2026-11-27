#!/usr/bin/env python3
"""Gera o site público (GitHub Pages) a partir do dashboard privado "Desempenho ICONIQ".

O site é uma cópia só de leitura do dashboard: a mesma página, com uma pequena camada
(window.claude) que lê site/data/db.json em vez da base de dados do artifact e recusa gravações.

  python3 -I gerar_site.py dados  --db <pasta> --out site/data/db.json --agora AAAA-MM-DDTHH:MM [--atual db.json]
  python3 -I gerar_site.py pagina --html <página do artifact> --out site/index.html

<pasta> = out_dir das leituras ArtifactData list das coleções meses, vendas, avaliacoes, alertas,
config e estado (um ficheiro <coleção>/<id>.json por documento).
"""
import argparse, glob, json, os, sys

COLECOES = ['meses', 'vendas', 'avaliacoes', 'alertas']
DOCS = ['config/avaliacao', 'config/avaliacoes', 'config/extras', 'config/equipa', 'config/vendas', 'estado/recolha']

SHIM = r"""<script>
/* Site público: cópia só de leitura do dashboard privado. Lê data/db.json; não grava. */
(function(){
  var P=null;
  function load(){ if(!P) P=fetch('data/db.json?v='+Date.now(),{cache:'no-store'}).then(function(r){ if(!r.ok) throw Object.assign(new Error('HTTP '+r.status),{code:'HTTP '+r.status}); return r.json(); }); return P; }
  function snap(id,d){ return {id:id,exists:d!=null,data:function(){return d;}}; }
  function ro(){ return Promise.reject(Object.assign(new Error('site só de leitura'),{code:'site só de leitura: altere no dashboard privado'})); }
  var db={
    doc:function(p){ var i=p.lastIndexOf('/'), id=p.slice(i+1);
      return {onSnapshot:function(ok,err){ load().then(function(j){ var c=p.slice(0,i), d=(j.doc&&j.doc[p]); if(d==null&&j.col&&j.col[c]) d=j.col[c][id]; ok(snap(id,d==null?null:d)); }).catch(function(e){ if(err) err(e); }); return function(){}; },
              get:function(){ return load().then(function(j){ var d=j.doc&&j.doc[p]; return snap(id,d==null?null:d); }); }, set:ro, update:ro, delete:ro}; },
    collection:function(c){ return {onSnapshot:function(ok,err){ load().then(function(j){ var o=(j.col&&j.col[c])||{}; ok({docs:Object.keys(o).sort().map(function(k){return snap(k,o[k]);})}); }).catch(function(e){ if(err) err(e); }); return function(){}; }}; }
  };
  var user={can:function(){return Promise.resolve(false);},id:function(){return Promise.resolve(null);}};
  window.claude={use:function(n){ return Promise.resolve(n==='db'?db:n==='user'?user:null); }};
  load().then(function(j){ document.addEventListener('DOMContentLoaded',aviso); if(document.readyState!=='loading') aviso();
    function aviso(){ if(document.getElementById('roAviso')) return; var f=document.querySelector('footer')||document.body, d=document.createElement('div'); d.id='roAviso'; d.className='note';
      d.textContent='Cópia só de leitura do dashboard Desempenho ICONIQ, gerada a '+String(j.gerado||'').replace('T',' ')+'. As análises e avaliações são preenchidas no dashboard privado.'; f.appendChild(d); } }).catch(function(){});
})();
</script>
"""

def le(p):
    with open(p, encoding='utf-8') as f: return json.load(f)

def dados(a):
    col = {}
    for c in COLECOES:
        col[c] = {os.path.basename(f)[:-5]: le(f) for f in sorted(glob.glob(os.path.join(a.db, c, '*.json')))}
    doc = {}
    for p in DOCS:
        f = os.path.join(a.db, p + '.json')
        if os.path.exists(f): doc[p] = le(f)
    # o link do formulário de autoavaliação não vai para o site público (qualquer pessoa o poderia preencher)
    if 'config/avaliacao' in doc: doc['config/avaliacao'] = {k: v for k, v in doc['config/avaliacao'].items() if k != 'formUrl'}
    if len(col['meses']) < 22: sys.exit('ERRO: menos de 22 meses lidos (%d); nada gravado' % len(col['meses']))
    for k, d in col['meses'].items():
        if not isinstance(d.get('f'), list): sys.exit('ERRO: mês %s sem a lista f; nada gravado' % k)
    if not col['vendas']: sys.exit('ERRO: coleção vendas vazia; nada gravado')
    novo = {'gerado': a.agora, 'col': col, 'doc': doc}
    if a.atual and os.path.exists(a.atual):
        ant = le(a.atual)
        falta = [c + '/' + k for c in ('meses', 'vendas') for k in ant.get('col', {}).get(c, {}) if k not in col[c]]
        if falta: sys.exit('ERRO: desapareceriam do site: %s; nada gravado' % ', '.join(falta))
        if {k: v for k, v in ant.items() if k != 'gerado'} == {k: v for k, v in novo.items() if k != 'gerado'}:
            print('IGUAL'); return
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f: json.dump(novo, f, separators=(',', ':'), ensure_ascii=False)
    ult = sorted(col['meses'])[-1]
    print('MUDOU', json.dumps({'bytes': os.path.getsize(a.out), 'meses': len(col['meses']), 'ultimo': ult, 'ate': col['meses'][ult].get('ate'),
                               'vendas': len(col['vendas']), 'avaliacoes': len(col['avaliacoes']), 'alertas': len(col['alertas'])}))

def pagina(a):
    t = open(a.html, encoding='utf-8').read()
    i = t.find('<!DOCTYPE html>'); j = t.find('</html>', i)
    if i < 0 or j < 0: sys.exit('ERRO: página do artifact não reconhecida')
    t = t[i:j + 7] + '\n'
    if 'window.claude.use' not in t or t.count('<head>') != 1: sys.exit('ERRO: página do artifact mudou de estrutura')
    t = t.replace('<head>', '<head>\n' + SHIM, 1)
    t = t.replace('Dados de RH: esta vista existe só no painel privado.', 'No site público esta vista é só de consulta; as avaliações são lançadas no dashboard privado.')
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f: f.write(t)
    print('PAGINA', os.path.getsize(a.out))

ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest='cmd', required=True)
d = sp.add_parser('dados'); d.add_argument('--db', required=True); d.add_argument('--out', required=True); d.add_argument('--agora', required=True); d.add_argument('--atual')
p = sp.add_parser('pagina'); p.add_argument('--html', required=True); p.add_argument('--out', required=True)
a = ap.parse_args(); (dados if a.cmd == 'dados' else pagina)(a)
