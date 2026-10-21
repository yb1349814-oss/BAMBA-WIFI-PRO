# BAMBA WIFI PRO

Application Flask avec interface adaptée au mobile. Le tableau de bord et les pages de gestion disposent désormais d'une navigation, de cartes de statistiques et de formulaires empilés verticalement. Les pages publiques, les textes, les couleurs, les tarifs et les fonctionnalités sont conservés.

## Lancer localement

```bash
pip install -r requirements.txt
python app.py
```

Pour un déploiement réel, définir `SECRET_KEY` et utiliser un stockage persistant pour la base SQLite. Les intégrations réelles Mobile Money, RADIUS et WireGuard doivent être configurées séparément.
