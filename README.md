# Huawei HiLink Opple Light (cloud) — intégration Home Assistant

Intégration non officielle pour piloter une lampe de bureau **Opple Smart Desk Lamp** (Huawei HiLink) depuis Home Assistant, via le pont cloud MQTT de Huawei (`smartlife-dre.things.dbankcloud.com`).

Projet de rétro-ingénierie personnel : le hub HiLink local de ces lampes a été abandonné par Huawei, seul le chemin cloud (compte Huawei + MQTT) reste fonctionnel.

## ⚠️ Statut

- Pilotage temps réel (on/off, luminosité, température de couleur) : validé sur une lampe réelle.
- Rafraîchissement automatique du token (refresh_token) : validé.
- Récupération des identifiants (`account` + `devices`) nécessaires au paramétrage : **en cours**. Le script `tools/get_account_token.py` effectue le login OAuth et affiche le `access_token`/`refresh_token`, mais ne produit pas encore directement le JSON combiné (`account` + `devices`) attendu par l'assistant de configuration — il faut repérer `user_id` dans la réponse et lister les devices à la main pour l'instant.

N'utilisez cette intégration que si vous êtes à l'aise pour bricoler : c'est un reverse engineering d'une API privée, non documentée et non garantie par Huawei.

## Installation via HACS (dépôt personnalisé)

1. Dans Home Assistant : **HACS → ⋮ (menu en haut à droite) → Dépôts personnalisés**.
2. Colle l'URL de ce dépôt GitHub, catégorie **Intégration**.
3. Recherche « Huawei HiLink Opple Light (cloud) » dans HACS et installe-la.
4. Redémarre Home Assistant.
5. **Paramètres → Appareils et services → Ajouter une intégration → Huawei HiLink (cloud)**.
6. Colle le JSON de configuration (voir ci-dessous).

## Obtenir les identifiants

1. Lance `tools/get_account_token.py --start-authorization` sur ta machine (jamais dans Home Assistant lui-même).
2. Ouvre l'URL affichée, connecte-toi avec ton compte Huawei, autorise l'accès.
3. Colle l'URL de callback `hms://redirect_url?...` quand demandé.
4. Le script affiche la réponse complète du serveur (`access_token`, `refresh_token`, etc.) — **ne la colle jamais ailleurs que dans le formulaire de configuration de Home Assistant**.
5. Construis le JSON attendu par l'assistant de configuration :

   ```json
   {
     "account": {
       "access_token": "...",
       "refresh_token": "...",
       "user_id": "...",
       "expires_at": 1761310000.0
     },
     "devices": [
       {"device_id": "...", "name": "Bureau", "model": "Opple H002"}
     ]
   }
   ```

   `expires_at` = timestamp Unix actuel + `expires_in` (en secondes) renvoyé par le serveur.

## Licence

MIT — voir `LICENSE`. Projet non affilié à Huawei ni à Opple.
