"""Demo chatbot page served at `/` by `interfaces/api.py`.

Plain HTML, CSS and JavaScript, no external resource (works offline). Each question is answered
independently through `/api/query/stream` (the evaluated single-turn pipeline); the page keeps the
previous turns on screen only. Example questions were written for the demo, one per specialty;
they come from no evaluation set (tests/test_no_benchmark_leakage.py scans this module).
"""

DEMO_HTML = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RAG-SFAR — prototype de recherche</title>
<style>
  :root { --bg:#f6f7f9; --card:#fff; --text:#16202e; --muted:#5b6675; --line:#d8dde5;
          --accent:#0b5cad; --ok:#1d7a3a; --warn:#9a5b00; --warnbg:#fff4e0; --bad:#b3261e; --badbg:#fdecea; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
         background:var(--bg); color:var(--text); font-size:18px; line-height:1.5; }
  header { background:#fff; border-bottom:1px solid var(--line); padding:12px 16px; }
  .wrap { max-width:980px; margin:0 auto; padding:0 16px; }
  h1 { font-size:1.35rem; margin:0; }
  .sub { color:var(--muted); font-size:.95rem; }
  .disclaimer { background:var(--warnbg); border:1px solid #f0c36d; color:#5a3b00; border-radius:8px;
                padding:10px 14px; margin:12px 0; font-size:.95rem; }
  .genline { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:6px; font-size:.95rem; }
  .dot { width:12px; height:12px; border-radius:50%; display:inline-block; background:#999; }
  .dot.ok { background:var(--ok); } .dot.bad { background:var(--bad); } .dot.unknown { background:#c9a400; }
  button { font:inherit; border-radius:8px; border:1px solid var(--accent); background:var(--accent); color:#fff;
           padding:8px 14px; cursor:pointer; }
  button.alt { background:#fff; color:var(--accent); }
  button:disabled { opacity:.5; cursor:default; }
  details.settings { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:8px 14px; margin:10px 0; }
  details.settings summary { cursor:pointer; font-weight:600; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:10px 16px; margin-top:10px; }
  @media (max-width:700px) { .grid { grid-template-columns:1fr; } body { font-size:16px; } }
  label { display:block; font-size:.9rem; color:var(--muted); }
  input[type=text], input[type=password], input[type=number], textarea {
    font:inherit; width:100%; padding:8px 10px; border:1px solid var(--line); border-radius:8px; background:#fff; color:var(--text); }
  .examples { display:flex; flex-wrap:wrap; gap:8px; margin:10px 0; }
  .examples button { background:#fff; color:var(--text); border-color:var(--line); font-size:.9rem; padding:6px 12px; text-align:left; }
  .examples button:hover { border-color:var(--accent); }
  .turn { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin:14px 0; }
  .q { font-weight:700; margin-bottom:6px; }
  .meta { color:var(--muted); font-size:.85rem; margin-bottom:8px; }
  .status { color:var(--accent); font-style:italic; }
  .answer { white-space:pre-wrap; word-wrap:break-word; }
  .notice { border-radius:8px; padding:8px 12px; margin:8px 0; font-size:.95rem; }
  .notice.warn { background:var(--warnbg); border:1px solid #f0c36d; }
  .notice.bad { background:var(--badbg); border:1px solid #f1aaa4; }
  .notice.info { background:#eaf2fb; border:1px solid #b6d0ee; }
  a.cite { color:var(--accent); font-weight:700; text-decoration:none; border-bottom:1px dotted var(--accent); }
  a.cite.missing { color:var(--bad); border-color:var(--bad); }
  h3 { font-size:1rem; margin:14px 0 6px; }
  .src { border:1px solid var(--line); border-radius:8px; padding:8px 12px; margin:6px 0; background:#fbfcfd; }
  .src.hl { outline:3px solid #f0c36d; }
  .src .t { font-weight:600; }
  .src .s { color:var(--muted); font-size:.88rem; }
  .badge { display:inline-block; font-size:.78rem; border-radius:999px; padding:1px 8px; border:1px solid var(--line); margin-right:4px; }
  .badge.cur { color:var(--ok); border-color:var(--ok); } .badge.old { color:var(--bad); border-color:var(--bad); }
  .src pre { white-space:pre-wrap; word-wrap:break-word; font-family:inherit; font-size:.92rem; background:#fff;
             border:1px solid var(--line); border-radius:6px; padding:8px; max-height:420px; overflow:auto; }
  .ask { position:sticky; bottom:0; background:var(--bg); padding:10px 0 14px; border-top:1px solid var(--line); }
  .ask .row { display:flex; gap:8px; margin-top:8px; flex-wrap:wrap; }
  .small { font-size:.85rem; color:var(--muted); }
</style>
</head>
<body>
<header><div class="wrap">
  <h1>RAG-SFAR — interroger les recommandations de la SFAR</h1>
  <div class="sub">Prototype de recherche, Datathon SFAR 2026</div>
  <div class="genline"><span id="gdot" class="dot unknown"></span><span id="gtext">Générateur : chargement…</span>
    <span class="small" id="idxtext"></span></div>
</div></header>
<div class="wrap">
  <div class="disclaimer"><strong>Prototype de recherche.</strong> Les réponses sont générées automatiquement à partir
    d'extraits des recommandations SFAR et peuvent être fausses ou incomplètes. Elles ne remplacent ni la lecture de la
    recommandation originale ni le jugement clinique. Vérifiez chaque affirmation dans le passage cité.</div>

  <details class="settings" id="settingsBox">
    <summary>Réglages du générateur (point d'accès compatible OpenAI)</summary>
    <div id="lockNote" class="notice info" style="display:none">Réglages verrouillés par le déploiement (valeurs fixées par les variables d'environnement).</div>
    <div class="grid">
      <div><label for="sBase">URL de base (se termine en général par /v1)</label><input type="text" id="sBase" placeholder="https://…/v1"></div>
      <div><label for="sModel">Modèle (nom exact listé par le point d'accès)</label><input type="text" id="sModel" list="modelList"><datalist id="modelList"></datalist></div>
      <div><label for="sKey">Clé d'API (facultative, gardée en mémoire du serveur uniquement)</label><input type="password" id="sKey" autocomplete="off"></div>
      <div><label for="sThink"><input type="checkbox" id="sThink" checked> Envoyer <code>enable_thinking=false</code> (réflexion Qwen désactivée, comme évalué)</label></div>
      <div><label for="sMax">Tokens max (vide = profil évalué)</label><input type="number" id="sMax" min="16" max="32768"></div>
      <div><label for="sTemp">Température (vide = profil évalué)</label><input type="number" id="sTemp" min="0" max="2" step="0.1"></div>
    </div>
    <div class="row" style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
      <button class="alt" id="btnTest" type="button">Tester la connexion</button>
      <button id="btnApply" type="button">Appliquer</button>
    </div>
    <div id="settingsMsg" class="small" style="margin-top:6px"></div>
    <div id="profileNote" class="small" style="margin-top:6px"></div>
  </details>

  <div class="small">Exemples (rédigés pour la démonstration) :</div>
  <div class="examples" id="examples"></div>

  <div id="conv"></div>

  <div class="ask">
    <label for="q">Question (en français). Chaque question est traitée indépendamment, sans mémoire des précédentes.</label>
    <textarea id="q" rows="2" placeholder="Ex. : Quelle conduite à tenir pour … ?"></textarea>
    <div class="row" style="align-items:center">
      <label for="sRob" style="display:inline">Robustesse aux fautes et abréviations :</label>
      <select id="sRob" style="font:inherit;padding:6px;border-radius:8px;border:1px solid var(--line);max-width:100%">
        <option value="none">aucune (configuration évaluée)</option>
        <option value="lexical">lexicale (sans modèle)</option>
        <option value="normalize">normalisation par le modèle</option>
        <option value="both">les deux</option>
      </select>
    </div>
    <div class="row">
      <button id="btnAsk" type="button">Répondre</button>
      <button id="btnPassages" class="alt" type="button">Passages seuls (sans modèle de langage)</button>
    </div>
  </div>
</div>
<script>
const EXAMPLES = [
  ["Voies aériennes", "Comment préoxygéner un adulte avant l'induction d'une anesthésie générale au bloc opératoire ?"],
  ["Diabète", "Faut-il interrompre un inhibiteur de SGLT2 avant une chirurgie programmée, et combien de temps avant ?"],
  ["Obstétrique", "Que faire si la patiente ressent une douleur pendant une césarienne réalisée sous anesthésie périmédullaire ?"],
  ["Pédiatrie", "Quels blocs périphériques sont proposés pour l'analgésie d'une chirurgie du pénis chez l'enfant ?"],
  ["Réanimation", "Quel soluté de remplissage vasculaire privilégier en première intention chez un patient en situation critique ?"],
  ["Allergie", "Quels dosages biologiques réaliser après une suspicion de réaction d'hypersensibilité immédiate peropératoire ?"],
  ["Hors périmètre", "Quel traitement de fond proposer pour une migraine chronique de l'adulte en médecine de ville ?"],
];
const $ = id => document.getElementById(id);
let turnNo = 0, busy = false, locked = false, robInit = false, genAvailable = false;

function esc(s) { return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

async function refreshGenerator() {
  try {
    const g = await (await fetch('/api/generator')).json();
    locked = !!g.locked; genAvailable = !!g.available;
    if (!robInit && g.robustness) { $('sRob').value = g.robustness.default; robInit = true; }
    const st = g.last_status?.state || 'unknown';
    $('gdot').className = 'dot ' + (!g.available ? 'bad' : st === 'ok' ? 'ok' : st === 'error' ? 'bad' : 'unknown');
    let txt = 'Générateur : ';
    if (!g.available) txt += 'aucun (passages seuls)';
    else {
      txt += '<strong>' + esc(g.model) + '</strong>';
      if (g.base_url) txt += ' via ' + esc(g.base_url);
      if (st === 'error') txt += ' — injoignable au dernier essai (' + esc(g.last_status.error) + ')';
      else if (st === 'ok') txt += ' — a répondu';
      else txt += ' — non encore sollicité';
    }
    $('gtext').innerHTML = txt;
    const s = g.settings;
    if (s) {
      $('sBase').value = s.base_url; $('sModel').value = s.model;
      $('sKey').value = ''; $('sKey').placeholder = s.api_key_set ? '•••••• (clé en mémoire, laisser vide pour la garder)' : 'aucune';
      $('sMax').value = s.max_tokens_override ?? ''; $('sTemp').value = s.temperature_override ?? '';
      $('sThink').checked = s.send_thinking_flag;
    }
    for (const id of ['sBase','sModel','sKey','sMax','sTemp','sThink','btnApply']) $(id).disabled = locked;
    $('lockNote').style.display = locked ? '' : 'none';
    const p = g.profile_call_options || {};
    $('profileNote').textContent = `Profil servi : ${p.profile} (mode ${p.open_mode}) — appel évalué : max_tokens=${p.max_tokens}, température=${p.temperature}, enable_thinking=${p.enable_thinking}. Seul le transport change avec ces réglages ; le prompt reste celui du profil évalué.`;
  } catch (e) { $('gtext').textContent = 'Générateur : état inconnu (serveur injoignable ?)'; }
}

async function loadHealth() {
  try {
    const h = await (await fetch('/api/health')).json();
    $('idxtext').textContent = `• ${h.num_documents} documents, ${h.num_chunks} passages indexés • recherche ${h.retrieval_config}`;
  } catch (e) {}
}

$('btnTest').onclick = async () => {
  $('settingsMsg').textContent = 'Test en cours…';
  const body = locked ? {} : { base_url: $('sBase').value.trim(), api_key: $('sKey').value || null };
  try {
    const r = await (await fetch('/api/generator/test', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) })).json();
    if (r.ok) {
      $('modelList').innerHTML = r.models.map(m => `<option value="${esc(m)}">`).join('');
      $('settingsMsg').textContent = `Connexion réussie. Modèles listés : ${r.models.join(', ') || '(aucun)'}`;
      if (!locked && r.models.length && !r.models.includes($('sModel').value)) $('sModel').value = r.models[0];
    } else $('settingsMsg').textContent = 'Échec de la connexion : ' + r.error;
  } catch (e) { $('settingsMsg').textContent = 'Échec : ' + e; }
};

$('btnApply').onclick = async () => {
  const keyVal = $('sKey').value;
  const body = {
    base_url: $('sBase').value.trim(), model: $('sModel').value.trim(),
    api_key: keyVal ? keyVal : null,
    max_tokens_override: $('sMax').value ? parseInt($('sMax').value, 10) : null,
    temperature_override: $('sTemp').value !== '' ? parseFloat($('sTemp').value) : null,
    send_thinking_flag: $('sThink').checked,
  };
  const r = await fetch('/api/generator/settings', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
  $('sKey').value = '';
  if (r.ok) $('settingsMsg').textContent = 'Réglages appliqués (prochaine question).';
  else { let d = ''; try { d = (await r.json()).detail; } catch (e) {} $('settingsMsg').textContent = 'Refusé : ' + (typeof d === 'string' ? d : 'paramètres invalides'); }
  refreshGenerator();
};

function renderAnswer(text, t, nSources) {
  let h = esc(text);
  h = h.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>').replace(/^#{1,6}\s*(.+)$/gm, '<strong>$1</strong>');
  h = h.replace(/\[([^\[\]\n]*?S\d+[^\[\]\n]*?)\]/g, (m, inner) =>
    '[' + inner.replace(/S(\d+)/g, (mm, n) => {
      const ok = +n >= 1 && +n <= nSources;
      return `<a href="#" class="cite${ok ? '' : ' missing'}" data-t="${t}" data-n="${n}" title="${ok ? 'Voir la source' : 'Source inexistante'}">S${n}</a>`;
    }) + ']');
  return h;
}
function citedNumbers(text) {
  const out = new Set();
  for (const m of String(text).matchAll(/\[([^\[\]\n]*?S\d+[^\[\]\n]*?)\]/g)) for (const n of m[1].matchAll(/S(\d+)/g)) out.add(+n[1]);
  return out;
}
function sourceCard(rc, n, t) {
  const c = rc.chunk;
  const year = c.effective_year || '?';
  const ed = c.is_latest_edition ? `<span class="badge cur">en vigueur</span>` : `<span class="badge old">édition antérieure${c.superseded_by ? ' (remplacée)' : ''}</span>`;
  const grade = (c.grade_levels || []).length ? ` • ${esc(c.grade_levels.slice(0, 3).join(', '))}` : '';
  const link = c.landing_url ? ` • <a href="${esc(c.landing_url)}" target="_blank" rel="noopener">page SFAR</a>` : '';
  return `<div class="src" id="t${t}-S${n}">
    <div class="t">[S${n}] ${esc(c.doc_title)}</div>
    <div class="s">${esc(c.doc_type)} ${esc(year)}${c.version_label ? ' (' + esc(c.version_label) + ')' : ''} ${ed}${grade}${link}</div>
    <div class="s">Section : ${esc(c.section_path || 'non précisée')}</div>
    <details><summary>Voir le passage</summary><pre>${esc(c.text)}</pre></details>
  </div>`;
}
function renderSources(el, chunks, t, cited) {
  if (!chunks.length) { el.innerHTML = '<div class="notice warn">Aucun passage retrouvé.</div>'; return; }
  if (cited) {
    const citedIdx = [...cited].filter(n => n >= 1 && n <= chunks.length).sort((a, b) => a - b);
    const others = chunks.map((_, i) => i + 1).filter(n => !cited.has(n));
    let h = `<h3>Sources citées dans la réponse (${citedIdx.length})</h3>` + (citedIdx.map(n => sourceCard(chunks[n - 1], n, t)).join('') || '<div class="small">Aucune.</div>');
    if (others.length) h += `<details><summary class="small">Autres passages fournis au modèle (${others.length})</summary>${others.map(n => sourceCard(chunks[n - 1], n, t)).join('')}</details>`;
    el.innerHTML = h;
  } else {
    el.innerHTML = `<h3>Passages retrouvés, par rang (${chunks.length})</h3>` + chunks.map((rc, i) => sourceCard(rc, i + 1, t)).join('');
  }
}

document.addEventListener('click', e => {
  const a = e.target.closest('a.cite'); if (!a) return;
  e.preventDefault();
  const card = document.getElementById(`t${a.dataset.t}-S${a.dataset.n}`); if (!card) return;
  const d = card.parentElement.closest('details'); if (d) d.open = true;
  card.querySelector('details').open = true;
  card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  card.classList.add('hl'); setTimeout(() => card.classList.remove('hl'), 2500);
});

async function ask(question, passagesOnly) {
  question = question.trim(); if (!question || busy) return;
  busy = true; $('btnAsk').disabled = $('btnPassages').disabled = true;
  const t = ++turnNo;
  const div = document.createElement('div'); div.className = 'turn';
  div.innerHTML = `<div class="q">${esc(question)}</div>
    <div class="meta">${passagesOnly ? 'Mode passages seuls (aucun modèle de langage)' : 'Mode réponse générée'}</div>
    <div class="status">Recherche dans les recommandations…</div>
    <div class="notices"></div><div class="answer"></div><div class="sources"></div>`;
  $('conv').appendChild(div); div.scrollIntoView({ behavior: 'smooth', block: 'start' });
  const st = div.querySelector('.status'), ans = div.querySelector('.answer'), notes = div.querySelector('.notices'), srcs = div.querySelector('.sources');
  let chunks = [], text = '', failed = false, model = '';
  try {
    const res = await fetch('/api/query/stream', { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ query: question, retrieval_only: passagesOnly, robustness: $('sRob').value }) });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = '';
    while (true) {
      const { value, done } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      const blocks = buf.split('\n\n'); buf = blocks.pop();
      for (const b of blocks) {
        const line = b.trim(); if (!line.startsWith('data:')) continue;
        const ev = JSON.parse(line.slice(5));
        if (ev.type === 'retrieval') {
          chunks = ev.retrieved_chunks || []; model = ev.model_used;
          if (passagesOnly || model === 'retrieval_only') {
            st.textContent = ''; renderSources(srcs, chunks, t, null);
            if (!passagesOnly) notes.innerHTML += '<div class="notice bad">Aucun générateur configuré : affichage des passages seuls.</div>';
          } else st.textContent = `${chunks.length} passages retrouvés. Rédaction par ${model}…`;
        } else if (ev.type === 'variant') {
          let h = `<div class="notice info">Variante : <strong>${esc(ev.label)}</strong>${ev.used !== 'none' ? ' — option mesurée sur questions de développement seulement, hors évaluation' : ''}.`;
          if (ev.unavailable) h += ` ${esc(ev.unavailable)}`;
          const rw = ev.rewrite;
          if (rw) {
            if (rw.used) h += `<br>Question normalisée par le modèle (recherchée en plus de la question d'origine) : <em>${esc(rw.normalized_question)}</em> (${rw.n_added} passages ajoutés)`;
            else if (rw.error) h += `<br>Normalisation indisponible (${esc(rw.error)}) : recherche avec la question d'origine seule.`;
            else h += '<br>Le modèle n\'a pas modifié la question.';
          }
          notes.innerHTML += h + '</div>';
        } else if (ev.type === 'token') {
          if (passagesOnly || model === 'retrieval_only') continue;
          text += ev.text; ans.textContent = text;
        } else if (ev.type === 'generator_error' || ev.type === 'error') {
          failed = true; st.textContent = '';
          if (ev.type === 'error') notes.innerHTML += `<div class="notice bad">Erreur du serveur : ${esc(ev.message)}</div>`;
          else {
            notes.innerHTML += `<div class="notice bad">Générateur injoignable ou en erreur (${esc(ev.message)}). ${ev.partial ? 'Réponse interrompue, à ne pas utiliser. ' : ''}Affichage des passages seuls.</div>`;
            ans.textContent = ''; renderSources(srcs, chunks, t, null);
          }
        } else if (ev.type === 'done') {
          st.textContent = '';
          if (failed || passagesOnly || model === 'retrieval_only') continue;
          const final = ev.answer || text;
          ans.innerHTML = renderAnswer(final, t, chunks.length);
          const v = ev.verification || {};
          const warns = v.warnings || [];
          if (v.is_abstention) notes.innerHTML += '<div class="notice info">Le système s\'abstient : les passages retrouvés ne permettent pas de répondre.</div>';
          if (warns.length) notes.innerHTML += `<div class="notice warn"><strong>Alerte du contrôle automatique :</strong><br>${warns.map(esc).join('<br>')}</div>`;
          if ((v.invalid_citations || []).length) notes.innerHTML += `<div class="notice warn">Citations sans source correspondante : ${esc(v.invalid_citations.join(', '))}</div>`;
          if (!citedNumbers(final).size && !v.is_abstention) notes.innerHTML += '<div class="notice warn">Réponse sans citation [Sx] : non sourcée, à vérifier.</div>';
          const lat = ev.latency_ms || {};
          div.querySelector('.meta').textContent = `Réponse générée par ${ev.model_used || model} • recherche ${Math.round(lat.total_retrieval_ms || 0)} ms • total ${((lat.total_ms || 0) / 1000).toFixed(1)} s`;
          renderSources(srcs, chunks, t, citedNumbers(final));
        }
      }
    }
  } catch (e) {
    st.textContent = ''; notes.innerHTML += `<div class="notice bad">Erreur : ${esc(e.message || e)}</div>`;
  } finally {
    busy = false; $('btnAsk').disabled = $('btnPassages').disabled = false;
    if (!passagesOnly) refreshGenerator();
  }
}

$('examples').innerHTML = EXAMPLES.map(([lab, q], i) => `<button type="button" data-i="${i}" title="${esc(q)}">${esc(lab)} : ${esc(q)}</button>`).join('');
$('examples').onclick = e => { const b = e.target.closest('button'); if (!b) return; $('q').value = EXAMPLES[+b.dataset.i][1]; ask($('q').value, false); };
$('btnAsk').onclick = () => ask($('q').value, false);
$('btnPassages').onclick = () => ask($('q').value, true);
$('q').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask($('q').value, false); } });
refreshGenerator(); loadHealth();
</script>
</body>
</html>
"""
