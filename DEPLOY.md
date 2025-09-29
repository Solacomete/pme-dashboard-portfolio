# Déploiement – Streamlit Cloud (gratuit)

## Pré-requis
- Un compte GitHub
- Ce dossier poussé sur un dépôt GitHub

## Étapes rapides
1. **Créer le dépôt GitHub**  
   - Sur GitHub → New → *pme-dashboard-demo*  
   - Uploade tous les fichiers de ce dossier (ou `git push` depuis ta machine)

2. **Secrets & thème**
   - Dans le dépôt, crée `/.streamlit/secrets.toml` à partir de `secrets.toml.example` :
     ```toml
     BUSINESS_NAME = "Boulangerie Démo"
     APP_PASSWORD = "ton_mot_de_passe"    # optionnel
     DEMO_MODE = "true"                    # "true" pour désactiver les exports publics
     ```

3. **Déployer**
   - Va sur https://share.streamlit.io
   - *New app* → sélectionne ton repo/branche → *Deploy*
   - Tu reçois une **URL publique** (protégée si `APP_PASSWORD` défini)

## Notes
- Pour enlever le mot de passe, supprime `APP_PASSWORD` des secrets.
- Pour une instance client, mets `DEMO_MODE = "false"` (autorise l’export CSV).
- Le thème est défini dans `/.streamlit/config.toml`. Modifie les couleurs si besoin.
