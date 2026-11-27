"""Build the x2_dev internal development set (synthetic, team-written, NOT medically validated).
Quotes are extracted verbatim from index/tas_v6/metadata.sqlite (read-only) using start/end anchors."""
import json, re, sqlite3
from pathlib import Path

DB = '/Users/tim/Me/SFAR-datathon/index/tas_v6/metadata.sqlite'
OUT = Path(__file__).with_name('x2_dev.jsonl')
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)

def chunk(idx):
    cid, did, latest, ref, p = c.execute(
        'select chunk_id, doc_id, is_latest_edition, is_reference_section, payload_json from chunks where idx=?', (idx,)).fetchone()
    assert latest == 1 and ref == 0, idx
    d = json.loads(p)
    return cid, did, d['text'], d['doc_title']

def extract(text, start, end):
    i = text.index(start)
    j = text.index(end, i) + len(end)
    return text[i:j]

# (id, kind, question, reference_answer, partA=(idx,start,end,desc), partB=(idx,start,end,desc))
ITEMS = [
# ---------------- two_documents ----------------
("X2D-01", "two_documents",
 "Une patiente de 82 ans sous warfarine consulte aux urgences après une chute avec traumatisme crânien léger : dans quel délai faut-il obtenir le scanner cérébral, et si celui-ci montre une hémorragie intracrânienne, avec quels produits et à quelles doses faut-il antagoniser l'AVK ?",
 "Un traitement anticoagulant classe le TCL à risque élevé : la TDM cérébrale doit être réalisée idéalement dans l'heure suivant l'admission (RPP TC léger). En cas d'hémorragie intracrânienne sous AVK, il faut antagoniser si l'INR est > 1,2 : CCP selon l'INR et le RCP (25 UI/kg si l'INR n'est pas disponible rapidement) associés à 10 mg de vitamine K IV ou PO (RFE anticoagulation en urgence).",
 (14185, "Idéalement dans l'heure", "ou de lésion intracrânienne.", "délai de la TDM cérébrale chez un TCL à risque élevé (anticoagulé)"),
 (10693, "de l'antagoniser en urgence par l'administration de CCP", "associés à 10 mg de vitamine K (IV ou PO).", "antagonisation CCP (25 UI/kg si INR indisponible) + vitamine K 10 mg")),
("X2D-02", "two_documents",
 "Une parturiente présentant une pré-éclampsie sévère entre en travail avec un risque élevé de césarienne : faut-il anticiper la pose de l'analgésie périmédullaire, et doit-on lui administrer un remplissage vasculaire systématique ?",
 "Les experts suggèrent de proposer une analgésie périmédullaire précoce dans les populations à risque (risque maternel lié à une comorbidité, risque obstétrical dont risque de césarienne augmenté) (RFE analgésie obstétricale 2025, avis d'experts). En revanche, il n'est pas recommandé de réaliser un remplissage vasculaire systématique chez les femmes avec une pré-éclampsie sévère (RFE pré-éclampsie, GRADE 1-).",
 (7751, "analgésie périmédullaire précoce dans les populations à risque*", "un risque maternel (obésité, comorbidité...)", "APM précoce chez les populations à risque"),
 (17125, "Il n’est pas recommandé de réaliser un remplissage vasculaire", "morbidité maternelle et/ou néonatale.", "pas de remplissage vasculaire systématique dans la pré-éclampsie sévère")),
("X2D-03", "two_documents",
 "Un nourrisson ancien prématuré, âgé de 46 semaines post-conceptionnelles, doit être opéré d'une hernie inguinale : dans quel type de structure doit-il être pris en charge et quelle stratégie anesthésique privilégier pour limiter les complications postopératoires ?",
 "L'ancien prématuré de moins de 60 semaines d'âge post-conceptionnel est une population à risque majoré de complications cardio-respiratoires sévères : prise en charge suggérée dans un centre spécialisé (ou centre spécialisé à vocation régionale) (RPP organisation de l'anesthésie pédiatrique). Pour la cure de hernie inguinale avant 60 semaines post-conceptionnelles, les experts suggèrent de privilégier une stratégie incluant une anesthésie locorégionale (RFE ALR pédiatrique 2026).",
 (12561, "l'ancien prématuré de moins de 60 semaines", "soient pris en charge dans un centre spécialisé", "orientation vers un centre spécialisé"),
 (2506, "Chez l'ancien prématuré opéré d'une chirurgie de hernie inguinale", "afin de réduire le risque de complications postopératoires.", "stratégie incluant une ALR")),
("X2D-04", "two_documents",
 "En réanimation, un adulte atteint d'un SDRA sévère et très hypoxémique doit être intubé : quelle technique de préoxygénation utiliser, et une fois sous ventilation mécanique, quelle stratégie de positionnement est recommandée et pour quelle durée quotidienne ?",
 "Pour la préoxygénation du patient hypoxémique en réanimation, il faut probablement utiliser la VNI (RFE intubation-extubation en réanimation 2016, GRADE 2+). Une fois ventilé, le patient atteint de SDRA sévère doit être placé en décubitus ventral plus de 12 heures par jour (recommandations SDRA 2018, GRADE 1+).",
 (22013, "R4.1 - Il faut probablement utiliser la VNI", "hypoxémiques en réanimation.", "préoxygénation par VNI"),
 (19552, "Il est recommandé que les patients adultes atteints de SDRA sévère", "pendant plus de 12 heures par jour.", "décubitus ventral > 12 h/j")),
("X2D-05", "two_documents",
 "Un homme de 68 ans avec une hémoglobine à 11,5 g/dL est programmé pour une prothèse totale de genou : quelle stratégie préopératoire proposer pour réduire le risque transfusionnel lié à son anémie, et quelle température centrale maintenir en peropératoire pour limiter le saignement ?",
 "En cas d'anémie modérée (Hb entre 10 et 13 g/dL) avant chirurgie prothétique du membre inférieur, il est recommandé d'utiliser l'érythropoïétine en préopératoire, associée en début de traitement à un apport de fer (RFE RAC orthopédie lourde 2019). En peropératoire, il est probablement recommandé de maintenir une température centrale ≥ 36,5 °C pour diminuer les complications hémorragiques (RFE hypothermie 2018).",
 (16469, "Il est recommandé d'utiliser l'érythropoïétine en préopératoire", "pour diminuer le risque transfusionnel.", "EPO préopératoire si Hb 10-13 g/dL"),
 (18552, "Il est probablement recommandé de maintenir une T°C ≥ 36,5°C", "chez le patient anesthésié.", "cible de température ≥ 36,5 °C")),
("X2D-06", "two_documents",
 "Un patient diabétique de type 2 traité par dapagliflozine et par apixaban pour une fibrillation atriale, avec une fonction rénale normale, doit subir une colectomie programmée à risque hémorragique élevé : quand doit-il prendre la dernière dose de chacun de ces deux traitements ?",
 "L'inhibiteur de SGLT2 doit être pris pour la dernière fois 3 jours avant l'intervention en raison du risque d'acidocétose euglycémique (préconisations diabète périopératoire 2025). L'AOD doit être arrêté avec une dernière prise à J-3 pour une procédure à risque hémorragique élevé en l'absence d'insuffisance rénale (RFE anticoagulants pour procédure programmée 2026).",
 (6696, "Inhibiteurs SGLT2 | Intervention", "(risque acidocétose euglycémique)", "arrêt de l'iSGLT2 3 jours avant"),
 (4926, "et programmé pour une procédure à risque hémorragique élevé, il est proposé", "en l'absence d'insuffisance rénale *.", "dernière prise d'AOD à J-3")),
("X2D-07", "two_documents",
 "Un coronarien stable, traité au long cours par ticagrélor seul et par bisoprolol, doit être opéré d'une chirurgie à risque hémorragique intermédiaire : comment gérer l'antiagrégant plaquettaire avant l'intervention, et que faire du bêtabloquant en période périopératoire ?",
 "Sous anti-P2Y12 en monothérapie avant une chirurgie à risque intermédiaire, il est proposé de remplacer l'antiagrégant par de l'aspirine 75 à 100 mg/j, idéalement plus de sept jours avant la chirurgie (RFE AAP procédure programmée 2018). Le bêtabloquant prescrit pour l'insuffisance coronaire doit être poursuivi, la posologie étant ajustée pour une fréquence cardiaque préopératoire de 60 à 70/min sans hypotension (RFE coronarien en chirurgie non cardiaque 2010).",
 (18174, "Il est proposé que chez les patients traités par un anti-P2Y12 en monothérapie", "à la dose journalière 75 à 100 mg", "relais du P2Y12 par l'aspirine"),
 (26865, "Pour tout traitement par un bêtabloquant", "sans hypotension artérielle (GRADE 1+ Accord fort).", "poursuite du bêtabloquant, cible FC 60-70")),
("X2D-08", "two_documents",
 "Une femme de 87 ans est hospitalisée pour une fracture de l'extrémité supérieure du fémur : dans quel délai après l'admission faut-il l'opérer, et quelle thromboprophylaxie (molécule, durée) prescrire après la chirurgie ?",
 "La chirurgie d'une FESF doit être réalisée dans les 48 heures suivant l'admission pour réduire la mortalité (RFE anesthésie du sujet âgé 2017, GRADE 1+). Après la chirurgie, une thromboprophylaxie par anticoagulant (HBPM ou fondaparinux) est recommandée pendant 4 semaines (RFE prévention MTEV 2024, GRADE 1+).",
 (20283, "Il faut réaliser la chirurgie d'une FESF", "afin de réduire la mortalité postopératoire.", "chirurgie dans les 48 h"),
 (9000, "Une thromboprophylaxie par anticoagulant", "pendant 4 semaines après la chirurgie", "HBPM ou fondaparinux 4 semaines")),
# ---------------- two_sections ----------------
("X2D-09", "two_sections",
 "Chez un patient de réanimation de 70 kg en choc septique avec défaillance multiviscérale, sédaté par propofol 1 % à 200 mg/h : quelle cible énergétique maximale viser, et quel apport calorique non nutritionnel représente cette perfusion de propofol ?",
 "En état de choc/défaillance multiviscérale, les experts suggèrent de ne pas dépasser 10 kcal/kg/j (soit 700 kcal/j pour 70 kg). Le propofol 1 % à 200 mg/h (20 mL/h) apporte environ 22 kcal/h, soit 528 kcal/j, à intégrer dans le calcul des apports (RFE nutrition clinique 2026).",
 (2062, "Chez les patients en état de choc / défaillance multiviscérale, les experts suggèrent de ne pas dépasser une cible énergétique maximale", "pour diminuer la morbi-mortalité.", "cible énergétique max 10 kcal/kg/j"),
 (1995, "Solution glucosée : 1 L de G5%/j", "soit 528 kcal/j", "apport calorique du propofol 1 %")),
("X2D-10", "two_sections",
 "Un patient sous rivaroxaban pour une fibrillation atriale, sans insuffisance rénale, doit avoir une chirurgie avec pose d'un cathéter de péridurale pour l'analgésie : quand doit-il prendre sa dernière dose avant la ponction, et quand reprendre l'anticoagulation curative après la chirurgie ?",
 "Les procédures neuraxiales sont à risque hémorragique très élevé : les experts suggèrent une dernière prise d'AOD à J-5. La reprise d'une anticoagulation curative n'est pas indiquée tant que le cathéter de péridurale est en place et se fait au moins 24 h après son retrait (RFE anticoagulants pour procédure programmée 2026).",
 (4927, "programmé pour une procédure à risque hémorragique très élevé", "avec une dernière prise à J-5 *.", "dernière prise d'AOD à J-5 avant geste neuraxial"),
 (5337, "La reprise d'une anticoagulation curative", "au moins 24h après son retrait [1].", "reprise ≥ 24 h après retrait du cathéter")),
("X2D-11", "two_sections",
 "Une femme enceinte de 24 semaines d'aménorrhée doit avoir une anesthésie générale programmée pour une chirurgie non obstétricale : quel dispositif de contrôle des voies aériennes utiliser, et si survient une situation d'intubation impossible et d'oxygénation impossible malgré un dispositif supraglottique, quelle technique d'abord réaliser en première intention ?",
 "Après 16 SA, les experts suggèrent de ne pas utiliser de dispositif supraglottique mais l'intubation trachéale. En situation « cannot intubate, cannot oxygenate », y compris chez la femme enceinte, il est recommandé de réaliser en première intention une cricothyroïdotomie selon la technique SMS (scalpel, mandrin long béquillé, sonde) (RFE voies aériennes de l'adulte au bloc 2026).",
 (75, "Chez la femme enceinte après 16 semaines d'aménorrhée", "par rapport à l'intubation trachéale", "pas de DSG après 16 SA : intubation trachéale"),
 (106, "il est recommandé de réaliser en première intention une cricothyroïdotomie", "Sonde d'intubation)", "cricothyroïdotomie technique SMS")),
("X2D-12", "two_sections",
 "Un enfant de 4 ans doit être opéré d'une hernie inguinale sous anesthésie générale : quel bloc analgésique privilégier, et si l'on souhaite prolonger l'analgésie par de la dexaméthasone, par quelle voie et à quelle posologie l'administrer ?",
 "Pour la chirurgie par voie inguinale, les experts suggèrent de privilégier un bloc du carré des lombes, un bloc TAP postérieur ou un bloc ilio-inguinal ilio-hypogastrique. La dexaméthasone, adjuvant recommandé par voie intraveineuse (et non périneurale), est suggérée à 0,15 à 0,2 mg/kg, dose totale plafonnée à 10 mg (RFE ALR pédiatrique 2026).",
 (2415, "Chez l'enfant opéré d'une chirurgie par voie inguinale", "ilio inguinal ilio hypogastrique", "choix du bloc pour la voie inguinale"),
 (2351, "lorsque l’utilisation de dexaméthasone est retenue", "dose totale plafonnée à 10 mg)", "dexaméthasone IV 0,15-0,2 mg/kg, max 10 mg")),
("X2D-13", "two_sections",
 "Aux urgences, un adulte qui vient de manger doit bénéficier d'une réduction de luxation sous sédation procédurale : faut-il attendre la fin de la période de jeûne, et quels agents et posologies initiales utiliser pour la sédation ?",
 "Chez un patient non à jeun, les experts suggèrent de ne pas différer la sédation procédurale pour respecter le jeûne. Il est recommandé d'utiliser l'association kétamine-propofol, avec une posologie initiale de 0,5 mg/kg de kétamine et 0,5 mg/kg de propofol, titrée par paliers de 0,25 mg/kg (RFE sédation procédurale en médecine d'urgence 2026).",
 (3048, "Chez un patient non à jeun", "dans un objectif de sécurité.", "ne pas différer pour le jeûne"),
 (3111, "les experts suggèrent, pour l'association kétamine-propofol, d'utiliser une posologie initiale", "par palier de 0,25 mg/kg", "kétamine 0,5 + propofol 0,5 mg/kg")),
("X2D-14", "two_sections",
 "Un polytraumatisé en choc hémorragique, conscient et sans détresse respiratoire, est pris en charge en urgence hors bloc : l'état de choc justifie-t-il à lui seul l'intubation, et si une intubation devient nécessaire, comment évaluer le risque de collapsus et quel hypnotique éviter ?",
 "Il n'est probablement pas recommandé d'intuber sur la seule indication du choc hémorragique en l'absence d'autre indication formelle (neurologique, respiratoire). Si une intubation est nécessaire, il est probablement recommandé de calculer le shock index (seuil > 0,9 = risque de collapsus), et les experts suggèrent d'éviter le propofol chez ces patients à risque (RFE intubation hors bloc et hors réanimation 2025).",
 (8633, "Chez un patient en état de choc hémorragique, il n'est probablement pas recommandé", "en l'absence d'autres indications formelles (neurologique, respiratoire)", "pas d'intubation sur le seul choc"),
 (8689, "il est probablement recommandé de calculer la valeur du shock-index", "collapsus cardiovasculaire au cours de l'intubation.", "shock index > 0,9")),
("X2D-15", "two_sections",
 "Au cours d'une anesthésie générale, un adulte présente une réaction anaphylactique de grade III : quelle dose d'adrénaline intraveineuse administrer et à quel rythme, et quand prélever la tryptase pour documenter la réaction ?",
 "En grade III, les experts suggèrent une titration d'adrénaline IV de 100 à 200 µg chez l'adulte toutes les 2 minutes (perfusion continue si instabilité persistante après trois bolus). Il est recommandé au moins deux dosages de tryptase : le premier à la phase aiguë, entre 30 minutes et 2 heures après le début des symptômes, le second au moins 24 h après la résolution (RFE hypersensibilité immédiate périopératoire 2025).",
 (8244, "Dans les réactions de grade III, les experts suggèrent une titration d'adrénaline intraveineuse 100 à 200 µg chez l'adulte", "toutes les 2 minutes", "adrénaline 100-200 µg IV /2 min"),
 (8020, "Le 1er dosage à la phase aiguë", "la valeur du pic de tryptase", "tryptase entre 30 min et 2 h")),
("X2D-16", "two_sections",
 "Une parturiente traitée par HBPM à dose curative pendant sa grossesse est en travail et demande une analgésie : quel délai respecter depuis sa dernière injection avant la pose d'une analgésie périmédullaire, et quelle alternative médicamenteuse proposer si celle-ci est contre-indiquée ?",
 "La pose d'une analgésie périmédullaire doit avoir lieu au moins 24 h après la dernière injection d'HBPM à dose curative (12 h à dose prophylactique). En cas de contre-indication à l'APM, il est recommandé d'utiliser le rémifentanil IV en mode autocontrôlé (PCA), avec surveillance rapprochée et supplément d'oxygène (RFE analgésie obstétricale 2025).",
 (7745, "Il est recommandé que la pose d'une analgésie périmédullaire ait lieu", "d'HBPM à dose curative", "délai ≥ 24 h après HBPM curative"),
 (7795, "En cas de contre-indication à l'analgésie périmédullaire", "mode autocontrôlé", "PCA de rémifentanil")),
]

def words(s): return re.findall(r"\w+", s.lower())

def ngram_overlap(q, t, n=8):
    qw, tw = words(q), words(t)
    tg = {tuple(tw[i:i+n]) for i in range(len(tw)-n+1)}
    return any(tuple(qw[i:i+n]) in tg for i in range(len(qw)-n+1))

rows = []
BAD = []
for (iid, kind, q, ans, A, B) in ITEMS:
    parts = []
    for (idx, s, e, desc) in (A, B):
        cid, did, text, title = chunk(idx)
        quote = extract(text, s, e)
        nw = len(quote.split())
        if not 10 <= nw <= 40: print('LEN', iid, idx, nw, repr(quote)); BAD.append(iid)
        assert quote in text
        if ngram_overlap(q, text): print('OVERLAP', iid, idx); BAD.append(iid)
        parts.append(dict(idx=idx, cid=cid, did=did, quote=quote, title=title, desc=desc))
    a, b = parts
    if kind == 'two_documents':
        assert a['did'] != b['did'], iid
        gold = [a['did'], b['did']]
    else:
        assert a['did'] == b['did'] and abs(a['idx'] - b['idx']) >= 15, iid
        gold = [a['did']]
    rows.append({
        "id": iid, "suite": "x2_dev", "question": q, "question_type": "open", "provenance": "team_written",
        "reference_answer": ans,
        "gold_doc_ids": gold,
        "gold_passages": [{"doc_id": p['did'], "quote": p['quote']} for p in parts],
        "evidence": [{"evidence_id": f"e{k+1}", "doc_id": p['did'], "fragments": [p['quote']]} for k, p in enumerate(parts)],
        "evidence_sets": [{"set_id": "s1", "required_evidence_ids": ["e1", "e2"]}],
        "tags": [kind],
        "meta": {"chunk_ids": [a['cid'], b['cid']], "chunk_idx": [a['idx'], b['idx']],
                 "part_a": a['desc'], "part_b": b['desc'], "doc_titles": [a['title'], b['title']]},
    })

assert not BAD, BAD
with OUT.open('w', encoding='utf-8') as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(len(rows), 'items written to', OUT)
