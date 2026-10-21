from pathlib import Path
from datetime import datetime
import shutil

p = Path("app.py")
s = p.read_text(encoding="utf-8")

if 'id="revenusChart"' in s or 'id="activiteChart"' in s:
    print("Graphiques déjà présents.")
    raise SystemExit(0)

old = "recent=c.execute('SELECT * FROM records WHERE user_id=? ORDER BY id DESC LIMIT 8',(u['id'],)).fetchall(); c.close()"
new = "recent=c.execute('SELECT * FROM records WHERE user_id=? ORDER BY id DESC LIMIT 8',(u['id'],)).fetchall(); labels, revenus_jours, activite_jours = bamba_chart_data(c, u['id']); c.close()"

if s.count(old) != 1:
    raise SystemExit("Repère du calcul introuvable : fichier non modifié.")

old_return = "    return page('Tableau de bord',body)"
if s.count(old_return) != 1:
    raise SystemExit("Repère du retour introuvable : fichier non modifié.")

marker = '<section class="section"><h2 style="text-align:left;font-size:24px">Activité récente</h2>'
if s.count(marker) != 1:
    raise SystemExit("Section Activité récente introuvable : fichier non modifié.")

# Construire le HTML à partir de chaînes simples, sans guillemets triples imbriqués.
lines = [
"    from flask import render_template_string",
"    graphe_html = render_template_string(",
"        '<section class=\"section\"><h2>Revenus — 7 jours</h2>'",
"        '<div style=\"height:250px\"><canvas id=\"revenusChart\"></canvas></div>'",
"        '<h2>Activité par catégorie</h2>'",
"        '<div style=\"height:250px\"><canvas id=\"activiteChart\"></canvas></div></section>'",
"        '<script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script>'",
"        '<script>if(typeof Chart!==\"undefined\"){'",
"        'new Chart(document.getElementById(\"revenusChart\"),{type:\"line\",data:{labels:{{ labels|tojson }},datasets:[{label:\"Revenus FCFA\",data:{{ revenus|tojson }},borderColor:\"#16a5ff\",fill:false}]},options:{responsive:true,maintainAspectRatio:false}});'",
"        'new Chart(document.getElementById(\"activiteChart\"),{type:\"bar\",data:{labels:[\"Tickets\",\"Vendeurs\",\"Sites\",\"Routeurs\"],datasets:[{data:{{ valeurs|tojson }},backgroundColor:[\"#16a5ff\",\"#00c9a7\",\"#7c6cff\",\"#ffb547\"]}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}});}'",
"        '</script>',",
"        labels=labels, revenus=revenus_jours,",
"        valeurs=[activite_jours[k] for k in ('tickets','vendeurs','sites','routeurs')]",
"    )",
"    body = body.replace(",
"        '<section class=\"section\"><h2 style=\"text-align:left;font-size:24px\">Activité récente</h2>',",
"        graphe_html + '<section class=\"section\"><h2 style=\"text-align:left;font-size:24px\">Activité récente</h2>', 1)",
]
insertion = "\n".join(lines) + "\n"

s = s.replace(old, new, 1)
s = s.replace(old_return, insertion + old_return, 1)

compile(s, str(p), "exec")
backup = p.with_name("app.py.avant_graphes_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
shutil.copy2(p, backup)

try:
    p.write_text(s, encoding="utf-8")
    compile(p.read_text(encoding="utf-8"), str(p), "exec")
except Exception:
    shutil.copy2(backup, p)
    raise

print("Graphiques ajoutés.")
print("Syntaxe Python : OK")
print("Sauvegarde :", backup.name)
print("Revenus :", 'id="revenusChart"' in s)
print("Activité :", 'id="activiteChart"' in s)
