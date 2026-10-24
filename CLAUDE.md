# Huawei HiLink Opple Light (cloud) — contexte projet

Intégration Home Assistant non officielle pour piloter une lampe de bureau
**Opple Smart Desk Lamp** via le pont cloud MQTT de Huawei (le hub HiLink
local de ces lampes a été abandonné par Huawei ; seul le chemin cloud via
compte Huawei + MQTT reste fonctionnel). Reverse engineering de l'appli
Android officielle **Huawei AI Life / Smart Life 17.0.3.320** (APK décompilé
avec jadx, trafic capturé via PCAPdroid + export HAR DevTools).

Dépôt GitHub public : `teflux77/ha-opple-smart-desk-lamp`.

## Statut actuel (2026-10-24)

- ✅ Pilotage temps réel (on/off, luminosité, température de couleur) validé
  sur une lampe réelle via MQTT.
- ✅ Rafraîchissement automatique du token (`refresh_token`) validé.
- ✅ Récupération automatique des identifiants (`tools/auto_authorize.py`,
  Playwright) validée : capture le code OAuth sans copier-coller manuel,
  enchaîne token → userinfo → homes → devices, écrit le JSON prêt pour HA.
- ✅ Décision prise (2026-10-24) : le script d'identifiants (renommé
  `get_credentials.py`) vit **à l'intérieur** de
  `custom_components/huawei_hilink_cloud/` pour être livré automatiquement
  par HACS. L'écran "Ajouter l'intégration" (`config_flow.py` +
  `strings.json`/`translations/`) affiche directement le chemin exact et la
  marche à suivre — personne n'a besoin de revenir sur GitHub ni de
  connaître le reverse engineering. Alternative "tout dans HA, zéro script
  externe" explicitement écartée : embarquer un moteur de navigateur dans
  une intégration HACS casserait sur Home Assistant OS (pas de libs système
  installables). Voir la section "Pourquoi pas directement dans Home
  Assistant" du README pour l'explication complète.
- ⏳ Pas encore testé en conditions réelles dans une install HA complète
  (install fraîche + ajout d'intégration de bout en bout, avec le nouveau
  texte d'écran).
- 💭 Discuté mais pas fait : extraire la logique d'auth (échange de token,
  refresh, homes/devices) dans un module séparé `huawei_cloud_auth/`
  réutilisable par de futures intégrations d'autres appareils Huawei cloud
  (pas seulement les lampes Opple).

## Architecture

```
custom_components/huawei_hilink_cloud/
  __init__.py       setup/unload de l'entry, instancie HuaweiCloudMqttClient
  cloud_client.py    cœur framework-agnostic : refresh token OAuth,
                      connexion MQTT/TLS persistante, envoi de commandes,
                      dispatch des messages notify (ACK + deviceDataChanged)
  config_flow.py     flow "coller le JSON" en une étape (pas d'OAuth natif
                      HA — voir section "Pourquoi pas d'OAuth natif HA" ci-dessous)
  const.py           constantes du domaine, services MQTT (switch/brightness/cct/...)
  light.py           entité light HA, poussée en temps réel (should_poll=False)
  manifest.json
tools/
  auto_authorize.py  script LOCAL (PC de l'utilisateur, pas dans HA) : capture
                      le code OAuth via Chromium piloté (Playwright) et produit
                      le JSON {"account": {...}, "devices": [...]} à coller
                      dans le formulaire de configuration HA
```

## Endpoints Huawei confirmés (rétro-ingénierie APK, 2026-10-24)

Tous sur `https://smartlife-dre.things.dbankcloud.com` sauf mention contraire.
En-têtes obligatoires sur CHAQUE appel ci-dessous (un appel sans ces en-têtes
est rejeté avant même la validation du corps) :

```
Accept: application/json
Content-Type: application/json;charset=UTF-8
User-Agent: HuaweiSmartHome/17.0.3.320
x-appId: 10406921
x-appVersion: 17.0.3.320
x-language: zh-CN
x-ori-app-name: com.huawei.smarthome
x-phoneOs: Android
x-requestId: <uuid frais à chaque appel>
```

- `POST /smart-life/v2/hms-lite/token` — échange code→tokens.
  Corps : `{"appId": APP_ID, "code": urllib.parse.quote(one_time_code)}`
  (le code EST url-encodé avant d'être mis dans le JSON — particularité
  confirmée par la décompilation, pas une coquille).
- `POST /smart-life/v2/hms-lite/refreshToken` — endpoint **différent** de
  `/token`, pas un `grant_type` sur le même path (piège : la première
  intuition de "même URL + grantType=refresh_token" échoue silencieusement
  avec une erreur générique `"System error"`).
  Corps : `{"appId": APP_ID, "refresh_token": <brut, PAS url-encodé>}`.
  Source : classe `RefreshTokenEntity` (`@JSONField(name="refresh_token")`)
  + `mk1.refreshAccessToken()` dans l'APK décompilé.
- `POST /smart-life/v2/hms-lite/userinfo` — corps `{"access_token": ...}`,
  avec aussi `Authorization: Bearer <access_token>`. Réponse contient `userId`.
- `GET https://smarthome.hicloud.com/userApp/v1.2.0/homes` — liste des maisons
  (`Authorization: Bearer <access_token>`). Note : hôte **différent**
  (`smarthome.hicloud.com`, pas `smartlife-dre.things.dbankcloud.com`).
- `GET https://smarthome.hicloud.com/smart-life/v2/devices` — avec header
  `x-homeId: <homeId>`.
- `GET https://smarthome.hicloud.com/smart-life/v3/devices?homeId=<ids,séparés,par,virgule>`

MQTT (confirmé, lampe réelle) :
- broker `smartlife-dre.things.dbankcloud.com:8883`, TLS sans vérification de
  chaîne (le cert n'est validé que par pinning côté appli officielle, pas une
  CA publique).
- topic commande : `/smartHome/signaltrans/v2/categories/command`
- topic notify : `smarthome.notify.app.v1`
- enveloppe : `{"header": {method, accessToken, mode, requestId, from, to,
  timestamp}, "body": {...}}`

## Pourquoi pas d'OAuth natif HA (`config_entry_oauth2_flow`)

Contrainte découverte, pas un choix de facilité : le `redirect_uri` de
l'appli Huawei officielle (dont on réutilise le `client_id` extrait de
l'APK, `10406921`) est figé en dur sur `hms://redirect_url` — un schéma
custom-scheme qu'aucun navigateur desktop ne sait ouvrir. On ne peut pas le
remplacer par l'URL de callback de HA (`my.home-assistant.io/redirect/...`)
comme le font Spotify/Google, car Huawei valide le `redirect_uri` contre ce
qui est enregistré pour ce `client_id` côté serveur. En plus, leur page de
login CAS passe par des contrôles anti-bot (vérification de ticket,
empreinte navigateur `trustBrowser`/`chkRisk`) qui bloquent toute requête
HTTP automatisée sans vrai moteur de rendu JS.

Conséquence : un vrai navigateur (même piloté par Playwright) est
**nécessaire** pour passer ces contrôles, pas une solution de facilité. Et
le faire tourner *depuis HA lui-même* ne marcherait que si HA tournait sur
la machine où l'utilisateur est assis — dans la plupart des installs
(Raspberry Pi, NAS, VM dédiée), HA n'a pas d'écran. D'où le choix d'un
script local séparé (`tools/auto_authorize.py`), lancé une fois sur le PC
de l'utilisateur, qui produit un JSON à coller dans le formulaire HA.

## Prochaines étapes possibles

1. Test end-to-end dans une install HA réelle (ajout d'intégration via le
   JSON produit par `auto_authorize.py`, vérifier la persistance du
   `refresh_token` renouvelé dans le config_entry après restart HA).
2. Décider si on extrait la logique d'auth dans un module
   `huawei_cloud_auth/` partagé (généralisation à d'autres appareils cloud
   Huawei au-delà des lampes Opple) — discuté, pas encore fait.
3. Décider du mode de distribution : HACS (repo public, déjà le cas) vs
   copie manuelle de `custom_components/huawei_hilink_cloud/` dans
   l'install HA — pas de contrainte de confidentialité, repo déjà public.

## Précautions

Ne jamais afficher ni committer `access_token`, `refresh_token`, ou un code
d'autorisation OAuth en clair (ni dans le code, ni dans les messages, ni
dans des fichiers de debug versionnés). `tools/auto_authorize.py` écrit
uniquement le JSON de résultat final en local, jamais dans la sortie
console.
