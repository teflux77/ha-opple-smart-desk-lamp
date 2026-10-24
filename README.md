# Huawei HiLink Opple Light (cloud) — intégration Home Assistant

Intégration non officielle pour piloter une lampe de bureau **Opple Smart Desk Lamp** (Huawei HiLink) depuis Home Assistant, via le pont cloud MQTT de Huawei (`smartlife-dre.things.dbankcloud.com`).

Projet de rétro-ingénierie personnel : le hub HiLink local de ces lampes a été abandonné par Huawei, seul le chemin cloud (compte Huawei + MQTT) reste fonctionnel.

## ⚠️ Statut

- Pilotage temps réel (on/off, luminosité, température de couleur) : validé sur une lampe réelle.
- Rafraîchissement automatique du token (refresh_token) : validé.
- Récupération automatique des identifiants (`account` + `devices`) via `get_credentials.py` (livré dans le dossier de l'intégration, le chemin exact s'affiche dans l'écran « Ajouter l'intégration ») : validée.

N'utilisez cette intégration que si vous êtes à l'aise pour bricoler : c'est un reverse engineering d'une API privée, non documentée et non garantie par Huawei.

## Installation via HACS (dépôt personnalisé)

1. Dans Home Assistant : **HACS → ⋮ (menu en haut à droite) → Dépôts personnalisés**.
2. Colle l'URL de ce dépôt GitHub, catégorie **Intégration**.
3. Recherche « Huawei HiLink Opple Light (cloud) » dans HACS et installe-la.
4. Redémarre Home Assistant.
5. **Paramètres → Appareils et services → Ajouter une intégration → Huawei HiLink (cloud)**.
6. Colle le JSON de configuration (voir ci-dessous).

## Obtenir les identifiants

Tout est automatisé par `get_credentials.py`, **livré avec l'intégration**
(installé par HACS dans `<dossier de config HA>/custom_components/
huawei_hilink_cloud/get_credentials.py`) — l'écran « Ajouter l'intégration »
dans Home Assistant affiche ce chemin exact et la marche à suivre, inutile
de revenir sur GitHub ni de connaître le détail du reverse engineering.

1. Une seule fois, sur un ordinateur **avec un navigateur** (pas forcément
   celui qui héberge Home Assistant — un NAS ou un Raspberry Pi en headless
   n'a pas d'écran) : installe Playwright et son Chromium.

   ```bash
   pip install playwright
   playwright install chromium
   ```

2. Copie `get_credentials.py` depuis le dossier de l'intégration sur cet
   ordinateur (Samba, SSH, l'add-on Terminal/File editor...), puis lance-le :

   ```bash
   python3 get_credentials.py
   ```

3. Une fenêtre Chromium **visible** s'ouvre sur la page officielle `oauth-login1.cloud.huawei.com`. Connecte-toi avec ton compte Huawei et autorise l'accès, comme dans l'appli officielle.
4. Le script intercepte automatiquement la redirection `hms://redirect_url?code=...` au moment où le navigateur tente de l'ouvrir (il ne sait pas gérer ce protocole, mais la tentative est capturée avant d'échouer) — aucune action de ta part, aucun copier-coller.
5. Il enchaîne seul l'échange du code, la résolution de ton compte et la récupération de tes maisons/appareils, puis écrit `ha_credentials.json` dans le dossier courant.
6. Colle le **contenu** de ce fichier dans le formulaire de configuration de Home Assistant — jamais ailleurs.

Le script n'affiche jamais `access_token`/`refresh_token`/`code` à l'écran, seulement un résumé (nombre d'appareils trouvés, durée de validité du token).

### Pourquoi pas directement dans Home Assistant ?

On y a pensé — mais empaqueter un vrai moteur de navigateur (nécessaire
pour passer les contrôles anti-bot de Huawei) à l'intérieur d'une
intégration installée par HACS casserait chez la plupart des utilisateurs :
une intégration ne peut installer que des paquets Python (`pip install`),
jamais les bibliothèques système dont Chromium a besoin, et Home Assistant
OS (l'install la plus courante) ne permet pas d'en ajouter. D'où le choix
d'un script livré avec l'intégration mais exécuté à part, sur un ordinateur
qui a un vrai navigateur.

### Pourquoi un Chromium piloté plutôt qu'un simple lien à ouvrir ?

Le `redirect_uri` de l'application Huawei officielle (`hms://redirect_url`) est un schéma d'URL personnalisé que seule l'appli mobile sait gérer. Sur un PC, aucun copier-coller manuel ne permet de récupérer cette redirection de façon fiable (DevTools/export réseau fonctionne mais reste fragile et peu reproductible). Piloter un vrai navigateur et intercepter la tentative de navigation au niveau protocole est la méthode utilisée par le projet de référence [`0xlic/ha-huawei-hilink-opple`](https://github.com/0xlic/ha-huawei-hilink-opple) — on la reprend ici, adaptée pour conserver `access_token`/`refresh_token` (nécessaires au pont cloud MQTT, contrairement à leur usage en contrôle local).

## Licence

MIT — voir `LICENSE`. Projet non affilié à Huawei ni à Opple.
