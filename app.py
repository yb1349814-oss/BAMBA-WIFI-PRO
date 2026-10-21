import os, sqlite3, secrets, hashlib, hmac, csv, io
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, redirect, url_for, session, flash, render_template_string, send_file, abort

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE','0') == '1', PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
DB = os.environ.get('WIFICONTROL_DB', 'bamba_wifi_pro.db')

FEATURES = [
('▤','Tickets WiFi et codes d’accès','Générez des lots de codes WiFi, imprimez des vouchers personnalisés et suivez chaque vente : actif, utilisé, expiré. Import de vos anciens codes lors d’une migration.'),
('♙','Réseau de vendeurs et commissions','Confiez la vente à des vendeurs et sous-revendeurs. Les commissions sont calculées automatiquement, le stock et l’argent dû sont suivis.'),
('◉','Serveur RADIUS géré','Authentification RADIUS (FreeRADIUS) hébergée et administrée : validité, quotas de données, coupure à l’échéance, verrouillage 1 code = 1 téléphone.'),
('⌁','Routeurs MikroTik connectés en VPN','Reliez vos routeurs MikroTik par tunnel WireGuard, même derrière Starlink ou CGNAT. Provisionnement guidé, supervision et diagnostic à distance.'),
('↗','Paiement Mobile Money','Vos clients achètent leurs codes en ligne depuis le portail captif (/buy), et vos revendeurs rechargent leur solde par Mobile Money.'),
('▦','Comptabilité automatique','Ventes, versements, arriérés, rapports mensuels par site et par vendeur : la comptabilité de votre activité WiFi se tient toute seule.'),
('⌖','Multi-sites et roaming','Gérez plusieurs sites hotspot depuis un seul compte. Le roaming permet à un code acheté sur un site de fonctionner sur vos autres sites.'),
('▣','Portail captif personnalisable','Pages de connexion hotspot à vos couleurs, thèmes de vouchers et boutique en ligne intégrée pour vendre vos forfaits.')]
PLANS = [
('Découverte','4 000','1 site','3 vendeurs','1 routeur / site','100 connexions simultanées',['Admin seul','Paiement en ligne (Mobile Money)','Tickets Wi-Fi','Support standard']),
('Starter','8 000','3 sites','6 vendeurs','2 routeurs / site','200 connexions simultanées',['Membres d’équipe','Paiement en ligne (Mobile Money)','Import de codes (migration)','Support standard']),
('Pro','15 000','6 sites','12 vendeurs','5 routeurs / site','500 connexions simultanées',['Paiement en ligne (Mobile Money)','Import de codes (migration)','Réseau de revendeurs (B2B)','Roaming inter-sites','Voucher personnalisé']),
('Business','25 800','15 sites','35 vendeurs','10 routeurs / site','1 200 connexions simultanées',['Paiement en ligne (Mobile Money)','Import de codes (migration)','Réseau de revendeurs (B2B)','Roaming inter-sites','Voucher personnalisé','Réseau avancé (MAC/IP)']),
('Max','40 000','35 sites','80 vendeurs','15 routeurs / site','3 000 connexions simultanées',['Paiement en ligne (Mobile Money)','Import de codes (migration)','Réseau de revendeurs (B2B)','Roaming inter-sites','Voucher personnalisé','Réseau avancé (MAC/IP)','Support prioritaire'])]
FAQ = [
('Qu’est-ce que BAMBA WIFI PRO ?','BAMBA WIFI PRO est une plateforme SaaS de gestion de hotspots WiFi : génération et vente de tickets (codes WiFi), gestion des vendeurs et de leurs commissions, serveur RADIUS géré, supervision de routeurs MikroTik et comptabilité automatique.'),
('Comment fonctionne l’essai gratuit de 30 jours ?','Créez votre compte : vous profitez immédiatement de 30 jours gratuits avec toutes les fonctionnalités (équivalent du forfait Max), sans carte bancaire. À la fin de l’essai, vous choisissez le forfait adapté à votre réseau.'),
('Ai-je besoin de mon propre serveur RADIUS ?','Non. BAMBA WIFI PRO est conçu pour héberger et administrer le serveur RADIUS. La connexion effective nécessite la configuration du service RADIUS et du tunnel VPN.'),
('Quels routeurs sont compatibles ?','Tout routeur MikroTik (RouterOS v7) capable de faire du hotspot. La configuration doit être appliquée sur le routeur et testée sur le réseau.'),
('Fonctionne-t-il derrière Starlink ou sans IP publique ?','Oui, l’architecture prévue utilise un tunnel WireGuard sortant vers un hub VPN. Le hub VPN doit être déployé et configuré.'),
('Mes clients peuvent-ils acheter un code en ligne ?','Le portail captif peut proposer un achat de codes par Mobile Money. Pour encaisser réellement, configurez un fournisseur de paiement et ses identifiants.'),
('Puis-je migrer mes codes existants ?','Oui. L’import CSV permet de reprendre vos codes existants, après vérification des colonnes et des règles de migration.'),
('Combien coûte BAMBA WIFI PRO ?','Les forfaits démarrent à 4 000 FCFA par mois et vont jusqu’à 40 000 FCFA par mois. Tous les comptes commencent par 30 jours d’essai gratuit toutes fonctionnalités.')]

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, company TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL, trial_until TEXT NOT NULL, plan TEXT DEFAULT 'Max');
    CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, detail TEXT DEFAULT '', amount REAL DEFAULT 0, status TEXT DEFAULT 'Actif', created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));''')
    return c

def pw_hash(p): return hashlib.pbkdf2_hmac('sha256',p.encode(), b'bamba_wifi_pro-v1', 240000).hex()
def current_user():
    if not session.get('uid'): return None
    c=connect(); u=c.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone(); c.close(); return u

def login_required(f):
    @wraps(f)
    def wrap(*a,**kw):
        if not current_user(): return redirect(url_for('login', next=request.path))
        return f(*a,**kw)
    return wrap

BASE = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="theme-color" content="#245bff"><title>{{ title }} — BAMBA WIFI PRO</title><style>
:root{--blue:#245bff;--navy:#101828;--muted:#475467;--line:#e1e7f0;--green:#00a878;--bg:#fff}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font:16px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--navy);background:#fff}a{color:inherit;text-decoration:none}button,input,select{font:inherit}.wrap{width:min(1120px,calc(100% - 36px));margin:auto}.nav{height:auto;min-height:76px;display:flex;align-items:center;justify-content:space-between;gap:18px;border-bottom:1px solid var(--line);padding:14px 0}.brand{font-size:21px;font-weight:800;display:flex;align-items:center;gap:9px;white-space:nowrap}.logo{display:grid;place-items:center;width:34px;height:34px;color:#fff;border-radius:9px;background:linear-gradient(145deg,#c21fff,#245bff);font-size:20px;box-shadow:0 5px 12px #245bff30}.links{display:flex;align-items:center;gap:27px;color:#293445}.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:12px 18px;border-radius:12px;border:1px solid var(--line);font-weight:650;background:#fff;color:var(--navy);cursor:pointer}.btn.primary{color:white;background:var(--blue);border-color:var(--blue);box-shadow:0 7px 16px #245bff25}.btn.outline{border:2px solid var(--blue);color:var(--blue)}.hero{text-align:center;padding:94px 0 72px}.pill{display:inline-flex;border:1px solid #8de7c8;color:#00865d;border-radius:999px;padding:6px 15px;font-size:14px;font-weight:650}.hero h1{font-size:clamp(36px,5.2vw,58px);line-height:1.06;letter-spacing:-1.7px;max-width:780px;margin:24px auto}.hero p{font-size:clamp(17px,2vw,21px);color:#344054;max-width:850px;margin:0 auto 28px}.actions{display:flex;justify-content:center;gap:12px;flex-wrap:wrap}.signin{margin:22px auto 0}.trust{display:flex;justify-content:center;gap:28px;flex-wrap:wrap;color:#344054;margin-top:34px}.trust span:before{content:'✓';color:var(--green);font-weight:800;margin-right:9px}.section{padding:35px 0 70px}.section h2{text-align:center;font-size:clamp(27px,4vw,36px);letter-spacing:-.7px;line-height:1.2;margin:0 0 12px}.sub{text-align:center;color:#344054;max-width:790px;margin:0 auto 42px}.features{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}.feature,.plan,.panel{border:1px solid var(--line);border-radius:18px;padding:26px;background:#fff;box-shadow:0 2px 5px #10182805}.ficon{color:var(--blue);font-size:24px;margin-bottom:18px}.feature h3{font-size:18px;margin:0 0 9px}.feature p{margin:0;color:#344054}.plans{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;align-items:stretch}.plan h3{margin:0;font-size:21px}.price{font-size:30px;font-weight:800;margin:10px 0}.price small{font-size:14px;font-weight:500;color:var(--muted)}.plan ul{padding-left:20px;color:#344054;min-height:125px}.plan li{margin:6px 0}.plan .btn{width:100%;margin-top:10px}.plan.max{border:2px solid var(--blue);position:relative}.tag{font-size:12px;font-weight:750;color:var(--blue);margin-bottom:8px}.faq{max-width:850px;margin:auto}.faq details{border-bottom:1px solid var(--line);padding:18px 4px}.faq summary{font-weight:700;cursor:pointer}.faq p{color:#475467;margin-bottom:0}.footer{border-top:1px solid var(--line);padding:25px 0;color:#475467;font-size:14px}.footer .footrow{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap}.formwrap{min-height:calc(100vh - 80px);display:grid;place-items:center;padding:38px 0}.formcard{width:min(460px,100%);border:1px solid var(--line);border-radius:20px;padding:30px;box-shadow:0 12px 40px #1018280c}.formcard h1{margin:0 0 7px;font-size:29px}.muted{color:var(--muted)}label{display:block;font-weight:650;margin:16px 0 6px}input,select{width:100%;border:1px solid #cfd7e4;border-radius:10px;padding:12px 13px;background:white}input:focus,select:focus{outline:3px solid #245bff25;border-color:var(--blue)}.formcard .btn{width:100%;margin-top:20px}.notice{background:#eff6ff;color:#1947b8;padding:12px 14px;border-radius:10px;margin:12px 0}.error{background:#fff1f0;color:#b42318;padding:12px 14px;border-radius:10px;margin:12px 0}.dashhead{padding:28px 0 20px}.dashhead h1{margin:0;font-size:30px}.dashnav{display:flex;flex-direction:column;gap:9px;overflow:visible;padding:10px 0 20px}.dashnav a{display:block;width:100%;white-space:normal;border:1px solid var(--line);border-radius:10px;padding:12px 14px}.dashnav a.active{background:#eef3ff;color:var(--blue);border-color:#bdccff}.stats{display:grid;grid-template-columns:1fr;gap:14px}.stat{border:1px solid var(--line);border-radius:15px;padding:18px}.stat b{display:block;font-size:25px}.stat span{color:var(--muted);font-size:14px}.tablewrap{overflow:auto}table{width:100%;border-collapse:collapse;min-width:600px}th,td{text-align:left;padding:13px;border-bottom:1px solid var(--line)}th{font-size:13px;color:#475467}.rowform{display:grid;grid-template-columns:1fr;gap:9px;align-items:stretch;margin:15px 0 22px}.rowform label{margin-top:0;font-size:13px}.rowform .btn{height:46px}.empty{padding:28px;text-align:center;color:var(--muted)}.small{font-size:13px}.flash{padding:11px 14px;border-radius:10px;background:#effaf5;color:#067647;margin:10px 0}.danger{color:#b42318}.menu-toggle{display:none}
@media(min-width:900px){.plans{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:700px){.wrap{width:min(100% - 28px,540px)}.nav{align-items:flex-start;flex-wrap:wrap}.links{order:3;width:100%;gap:0;justify-content:space-between;font-size:14px;padding-top:6px}.links a{padding:7px 0}.nav .navbtn{font-size:13px;padding:9px 10px}.hero{padding:55px 0 44px}.hero h1{letter-spacing:-1px}.hero p{line-height:1.55}.trust{display:grid;gap:10px;justify-content:center;text-align:left}.section{padding:28px 0 45px}.sub{margin-bottom:26px}.features,.plans{grid-template-columns:1fr;gap:14px}.feature,.plan{padding:21px}.plan ul{min-height:0}.stats{grid-template-columns:1fr 1fr}.stat:last-child{grid-column:1/-1}.rowform{grid-template-columns:1fr 1fr}.rowform>div:last-child{grid-column:auto}.rowform .btn{width:100%}.formcard{padding:23px}.footer .footrow{display:grid;gap:12px}}

.logo-img {
  display: block;
  width: 76px;
  height: 76px;
  object-fit: contain;
  border-radius: 14px;
  margin: 0 auto 12px;
}
</style></head><body><header class="wrap nav"><a class="brand" href="{{ url_for('home') }}"><img class="logo-img" src="/static/bamba-logo.svg" alt="BAMBA"></a>{% if user %}<div class="links"><a href="{{ url_for('dashboard') }}">Tableau de bord</a><a href="{{ url_for('section',kind='tickets') }}">Tickets</a><a href="{{ url_for('section',kind='vendeurs') }}">Vendeurs</a><a href="{{ url_for('section',kind='sites') }}">Sites</a></div><a class="btn outline navbtn" href="{{ url_for('logout') }}">Se déconnecter</a>{% else %}<nav class="links"><a href="{{ url_for('home') }}#fonctionnalites">Fonctionnalités</a><a href="{{ url_for('home') }}#tarifs">Tarifs</a><a href="{{ url_for('home') }}#faq">FAQ</a></nav><div style="display:flex;gap:8px"><a class="btn outline navbtn" href="{{ url_for('login') }}">↪ Se connecter</a><a class="btn primary navbtn" href="{{ url_for('register') }}">Essai gratuit</a></div>{% endif %}</header><main class="wrap">{% with messages=get_flashed_messages() %}{% for m in messages %}<div class="flash">{{m}}</div>{% endfor %}{% endwith %}{{ body|safe }}</main><footer class="footer"><div class="wrap footrow"><span>© 2026 BAMBA WIFI PRO — Gestion de hotspots WiFi.</span><span><a href="{{ url_for('home') }}">Accueil</a>　·　<a href="{{ url_for('home') }}#fonctionnalites">Fonctionnalités</a>　·　<a href="{{ url_for('home') }}#tarifs">Tarifs</a>　·　<a href="{{ url_for('home') }}#faq">FAQ</a>　·　<a href="{{ url_for('login') }}">Connexion</a></span></div></footer></body></html>'''

def page(title, body, **kw): return render_template_string(BASE,title=title,body=body,user=current_user(),**kw)

@app.get('/')
def home():
    if current_user(): return redirect(url_for('dashboard'))
    f=''.join(f'<article class="feature"><div class="ficon">{ico}</div><h3>{title}</h3><p>{desc}</p></article>' for ico,title,desc in FEATURES)
    cards=''
    for i,p in enumerate(PLANS):
        name,price,sites,sellers,routers,conns,items=p
        tag='<div class="tag">LE PLUS COMPLET — OFFERT 30 JOURS</div>' if name=='Max' else ''
        cards+=f'<article class="plan {"max" if name=="Max" else ""}">{tag}<h3>{name}</h3><div class="price">{price} FCFA <small>/ mois</small></div><ul><li>{sites}</li><li>{sellers}</li><li>{routers}</li><li>{conns}</li>'+''.join(f'<li>{x}</li>' for x in items)+f'</ul><a class="btn {"primary" if name=="Max" else "outline"}" href="{url_for("register")}">Essayer 30 jours gratuits</a></article>'
    faqs=''.join(f'<details><summary>{q}</summary><p>{a}</p></details>' for q,a in FAQ)
    body=f'''<section class="hero"><div class="pill">✧　30 jours gratuits — toutes les fonctionnalités, sans carte bancaire</div><h1>Gérez votre réseau de<br> hotspots WiFi comme un pro</h1><p>Tickets WiFi, vendeurs et commissions, serveur RADIUS géré, routeurs MikroTik en VPN, paiement Mobile Money et comptabilité automatique — tout-en-un.</p><div class="actions"><a class="btn primary" href="{url_for('register')}">Essayer 30 jours gratuits</a><a class="btn" href="#tarifs">Voir les tarifs</a></div><div class="signin"><a class="btn outline" href="{url_for('login')}">↪　Déjà inscrit ? Se connecter</a></div><div class="trust"><span>Sans engagement</span><span>Installation guidée</span><span>Choix du forfait après l'essai</span></div></section><section class="section" id="fonctionnalites"><h2>Tout ce qu'il faut pour votre réseau WiFi</h2><p class="sub">De la génération des codes à la comptabilité, BAMBA WIFI PRO couvre toute la chaîne — sans serveur à installer.</p><div class="features">{f}</div></section><section class="section" id="tarifs"><h2>Tarifs BAMBA WIFI PRO</h2><p class="sub">Des forfaits mensuels simples, sans engagement, adaptés à la taille de votre réseau de hotspots. Prix en FCFA — et 30 jours d'essai gratuit toutes fonctionnalités pour commencer.</p><div class="plans">{cards}</div><p class="sub" style="margin-top:30px;margin-bottom:0">Tous les comptes démarrent avec 30 jours gratuits du forfait le plus complet, sans carte bancaire. Vous choisissez votre forfait à la fin de l'essai — <a style="color:var(--blue);font-weight:700" href="{url_for('register')}">créer mon compte</a>.</p></section><section class="section" id="faq"><h2>Questions fréquentes</h2><div class="faq">{faqs}</div></section>'''
    return page('Accueil',body)

@app.route('/inscription',methods=['GET','POST'])
def register():
    if current_user(): return redirect(url_for('dashboard'))
    error=''
    if request.method=='POST':
        name=request.form.get('name','').strip(); company=request.form.get('company','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        if not name or not company or not email or len(password)<10: error='Remplissez tous les champs et utilisez un mot de passe de 10 caractères minimum.'
        else:
            c=connect()
            try:
                now=datetime.utcnow(); cur=c.execute('INSERT INTO users(name,company,email,password_hash,created_at,trial_until) VALUES(?,?,?,?,?,?)',(name,company,email,pw_hash(password),now.isoformat(),(now+timedelta(days=30)).isoformat())); c.commit(); session.clear(); session['uid']=cur.lastrowid; session.permanent=True; c.close(); flash('Compte créé. Votre essai de 30 jours est activé.'); return redirect(url_for('dashboard'))
            except sqlite3.IntegrityError: error='Cette adresse e-mail est déjà utilisée.'
            finally: c.close()
    body=f'''<div class="formwrap"><form class="formcard" method="post"><a class="brand" href="/"><img class="logo-img" src="/static/bamba-logo.svg" alt="BAMBA"></a><h1 style="margin-top:22px">Enregistrer ma société</h1><p class="muted">Créez votre espace privé et commencez vos 30 jours gratuits.</p>{f'<div class="error">{error}</div>' if error else ''}<label>Nom complet</label><input name="name" autocomplete="name" required><label>Nom de la société</label><input name="company" autocomplete="organization" required><label>Adresse e-mail</label><input name="email" type="email" autocomplete="email" required><label>Mot de passe</label><input name="password" type="password" minlength="10" autocomplete="new-password" required><p class="small muted">10 caractères minimum. Aucun moyen de paiement demandé.</p><button class="btn primary" type="submit">Créer mon compte</button><p class="muted" style="text-align:center">Déjà inscrit ? <a style="color:var(--blue);font-weight:700" href="{url_for('login')}">Se connecter</a></p></form></div>'''
    return page('Inscription',body)

@app.route('/connexion',methods=['GET','POST'])
def login():
    if current_user(): return redirect(url_for('dashboard'))
    error=''
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password',''); c=connect(); u=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone(); c.close()
        if u and hmac.compare_digest(u['password_hash'],pw_hash(password)):
            session.clear(); session['uid']=u['id']; session.permanent=True; return redirect(url_for('dashboard'))
        error='Adresse e-mail ou mot de passe incorrect.'
    body=f'''<div class="formwrap"><form class="formcard" method="post"><a class="brand" href="/"><img class="logo-img" src="/static/bamba-logo.svg" alt="BAMBA"></a><h1 style="margin-top:22px">Connectez-vous à votre espace</h1><p class="muted">Votre réseau WiFi, au même endroit.</p>{f'<div class="error">{error}</div>' if error else ''}<label>Adresse e-mail</label><input name="email" type="email" autocomplete="username" required><label>Mot de passe</label><input name="password" type="password" autocomplete="current-password" required><button class="btn primary" type="submit">Se connecter</button><p class="muted" style="text-align:center">Pas encore de compte ? <a style="color:var(--blue);font-weight:700" href="{url_for('register')}">Enregistrer ma société</a></p><p class="small muted">Mot de passe oublié ? Contactez l’administrateur de votre déploiement pour réinitialiser votre accès.</p></form></div>'''
    return page('Connexion',body)

@app.get('/deconnexion')
def logout(): session.clear(); return redirect(url_for('home'))


def bamba_chart_data(c, user_id):
    from datetime import date, timedelta
    jours = [date.today() - timedelta(days=i) for i in range(6, -1, -1)]
    revenus = []
    activite = {k: 0 for k in ('tickets', 'vendeurs', 'sites', 'routeurs')}
    for jour in jours:
        debut = jour.isoformat()
        fin = (jour + timedelta(days=1)).isoformat()
        montant = c.execute(
            """SELECT COALESCE(SUM(amount), 0) FROM records
               WHERE user_id=? AND kind='paiements'
               AND created_at >= ? AND created_at < ?""",
            (user_id, debut, fin)
        ).fetchone()[0]
        revenus.append(round(float(montant or 0), 2))
    for kind in activite:
        activite[kind] = c.execute(
            "SELECT COUNT(*) FROM records WHERE user_id=? AND kind=?",
            (user_id, kind)
        ).fetchone()[0]
    return [j.strftime('%d/%m') for j in jours], revenus, activite


@app.get('/dashboard')
@login_required
def dashboard():
    u=current_user(); c=connect(); total={k:c.execute('SELECT COUNT(*) FROM records WHERE user_id=? AND kind=?',(u['id'],k)).fetchone()[0] for k in ['tickets','vendeurs','sites','routeurs']}; revenue=c.execute("SELECT COALESCE(SUM(amount),0) FROM records WHERE user_id=? AND kind='paiements'",(u['id'],)).fetchone()[0]; recent=c.execute('SELECT * FROM records WHERE user_id=? ORDER BY id DESC LIMIT 8',(u['id'],)).fetchall(); labels, revenus_jours, activite_jours = bamba_chart_data(c, u['id']); c.close()
    rows=''.join(f'<tr><td>{r["created_at"][:10]}</td><td>{r["kind"].capitalize()}</td><td>{r["name"]}</td><td>{r["detail"]}</td><td>{r["amount"]:,.0f} FCFA</td><td>{r["status"]}</td></tr>' for r in recent) or '<tr><td colspan="6" class="empty">Aucune donnée pour le moment. Ajoutez votre premier élément ci-dessous.</td></tr>'
    body=f'''<div class="dashhead"><p class="muted">Espace privé · {u['company']}</p><h1>Tableau de bord</h1><p class="muted">Bonjour {u['name']} — votre compte est isolé des autres sociétés.</p></div>{dashnav('')}<div class="stats"><div class="stat"><span>Tickets WiFi</span><b>{total['tickets']}</b></div><div class="stat"><span>Vendeurs</span><b>{total['vendeurs']}</b></div><div class="stat"><span>Sites hotspot</span><b>{total['sites']}</b></div><div class="stat"><span>Routeurs</span><b>{total['routeurs']}</b></div><div class="stat"><span>Paiements saisis</span><b>{revenue:,.0f}</b><span>FCFA</span></div><div class="stat"><span>Essai gratuit jusqu’au</span><b style="font-size:18px">{u['trial_until'][:10]}</b></div></div><section class="section"><h2 style="text-align:left;font-size:24px">Activité récente</h2><div class="panel tablewrap"><table><thead><tr><th>Date</th><th>Type</th><th>Nom</th><th>Détails</th><th>Montant</th><th>Statut</th></tr></thead><tbody>{rows}</tbody></table></div><p class="small muted">Les fonctions d’encaissement Mobile Money, RADIUS et VPN nécessitent la configuration de leurs fournisseurs et serveurs externes.</p></section>'''
    from flask import render_template_string
    graphe_html = render_template_string(
        '<section class="section"><h2>Revenus — 7 jours</h2>'
        '<div style="height:250px"><canvas id="revenusChart"></canvas></div>'
        '<h2>Activité par catégorie</h2>'
        '<div style="height:250px"><canvas id="activiteChart"></canvas></div></section>'
        '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>'
        '<script>if(typeof Chart!=="undefined"){'
        'new Chart(document.getElementById("revenusChart"),{type:"line",data:{labels:{{ labels|tojson }},datasets:[{label:"Revenus FCFA",data:{{ revenus|tojson }},borderColor:"#16a5ff",fill:false}]},options:{responsive:true,maintainAspectRatio:false}});'
        'new Chart(document.getElementById("activiteChart"),{type:"bar",data:{labels:["Tickets","Vendeurs","Sites","Routeurs"],datasets:[{data:{{ valeurs|tojson }},backgroundColor:["#16a5ff","#00c9a7","#7c6cff","#ffb547"]}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true}}}});}'
        '</script>',
        labels=labels, revenus=revenus_jours,
        valeurs=[activite_jours[k] for k in ('tickets','vendeurs','sites','routeurs')]
    )
    body = body.replace(
        '<section class="section"><h2 style="text-align:left;font-size:24px">Activité récente</h2>',
        graphe_html + '<section class="section"><h2 style="text-align:left;font-size:24px">Activité récente</h2>', 1)
    return page('Tableau de bord',body)

def dashnav(active):
    names=[('','Vue générale'),('tickets','Tickets'),('vendeurs','Vendeurs'),('sites','Sites'),('routeurs','Routeurs'),('paiements','Paiements'),('comptabilite','Comptabilité'),('revendeurs','Revendeurs'),('radius','RADIUS'),('vpn','VPN MikroTik')]
    return '<nav class="dashnav">'+''.join(f'<a class="{"active" if k==active else ""}" href="{url_for("dashboard") if not k else url_for("section",kind=k)}">{n}</a>' for k,n in names)+'</nav>'

KINDS={'tickets':('Ticket WiFi','Code / forfait','Vendre ou suivre les codes WiFi'), 'vendeurs':('Vendeur','Nom du vendeur','Suivre les vendeurs et leurs commissions'), 'sites':('Site hotspot','Ville / adresse','Organiser les sites de votre réseau'), 'routeurs':('Routeur','Modèle / IP / site','Inventorier les routeurs MikroTik'), 'paiements':('Paiement','Référence / client','Enregistrer un versement ou une vente'), 'revendeurs':('Revendeur','Nom / société','Suivre les partenaires B2B'), 'comptabilite':('Opération','Catégorie / note','Enregistrer les recettes et dépenses')}
@app.route('/espace/<kind>',methods=['GET','POST'])
@login_required
def section(kind):
    if kind not in KINDS and kind not in ('radius','vpn'): abort(404)
    u=current_user()
    if kind in ('radius','vpn'):
        title='Serveur RADIUS géré' if kind=='radius' else 'VPN MikroTik / WireGuard'
        desc=('État de préparation : la liaison à un serveur FreeRADIUS n’est pas configurée dans cette version. Il faut fournir un serveur, ses identifiants et la configuration réseau.' if kind=='radius' else 'État de préparation : aucun tunnel n’est créé automatiquement. Déployez un hub WireGuard puis configurez les clés et les routes de vos routeurs.')
        body=f'<div class="dashhead"><p class="muted">Espace privé · {u["company"]}</p><h1>{title}</h1></div>{dashnav(kind)}<div class="panel"><h2>{title}</h2><p>{desc}</p><div class="notice">Module préparatoire — la connexion réelle nécessite une infrastructure externe et des identifiants de service.</div><a class="btn" href="{url_for("dashboard")}">Retour au tableau de bord</a></div>'
        return page(title,body)
    label,placeholder,description=KINDS[kind]
    if request.method=='POST':
        name=request.form.get('name','').strip(); detail=request.form.get('detail','').strip(); amount=request.form.get('amount','0').strip(); status=request.form.get('status','Actif')
        try: amount=float(amount or 0)
        except ValueError: amount=0
        if name:
            c=connect(); c.execute('INSERT INTO records(user_id,kind,name,detail,amount,status,created_at) VALUES(?,?,?,?,?,?,?)',(u['id'],kind,name,detail,amount,status,datetime.utcnow().isoformat())); c.commit(); c.close(); flash(f'{label} ajouté.'); return redirect(url_for('section',kind=kind))
    c=connect(); rows=c.execute('SELECT * FROM records WHERE user_id=? AND kind=? ORDER BY id DESC',(u['id'],kind)).fetchall(); c.close()
    trs=''.join(f'<tr><td>{r["id"]}</td><td>{r["name"]}</td><td>{r["detail"]}</td><td>{r["amount"]:,.0f} FCFA</td><td>{r["status"]}</td><td><form method="post" action="{url_for("delete_record",rid=r["id"])}" onsubmit="return confirm(\'Supprimer cet élément ?\')"><button class="btn" type="submit">Supprimer</button></form></td></tr>' for r in rows) or '<tr><td colspan="6" class="empty">Aucun élément enregistré.</td></tr>'
    body=f'''<div class="dashhead"><p class="muted">Espace privé · {u['company']}</p><h1>{label}s</h1><p class="muted">{description}.</p></div>{dashnav(kind)}<section class="panel"><h2 style="margin-top:0">Ajouter : {label}</h2><form method="post" class="rowform"><div><label>Nom / code</label><input name="name" placeholder="{placeholder}" required></div><div><label>Détails</label><input name="detail" placeholder="Notes, site, téléphone…"></div><div><label>Montant (FCFA)</label><input name="amount" type="number" min="0" step="1" value="0"></div><div><label>Statut</label><select name="status"><option>Actif</option><option>En attente</option><option>Utilisé</option><option>Expiré</option><option>Payé</option><option>À régler</option></select></div><div><button class="btn primary" type="submit">Ajouter</button></div></form><div class="tablewrap"><table><thead><tr><th>ID</th><th>Nom / code</th><th>Détails</th><th>Montant</th><th>Statut</th><th>Action</th></tr></thead><tbody>{trs}</tbody></table></div></section>'''
    return page(label,body)

@app.post('/supprimer/<int:rid>')
@login_required
def delete_record(rid):
    u=current_user(); c=connect(); c.execute('DELETE FROM records WHERE id=? AND user_id=?',(rid,u['id'])); c.commit(); c.close(); flash('Élément supprimé si celui-ci appartenait à votre espace.'); return redirect(request.referrer or url_for('dashboard'))

@app.get('/sante')
def health(): return {'status':'ok','app':'BAMBA WIFI PRO'}

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT','5000')),debug=False)
