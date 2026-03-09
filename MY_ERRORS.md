# ERREURS À NE PAS RÉPÉTER

## 2026-03-05 - Erreur de comptage des mails envoyés

**Problème :** J'ai compté 11 mails de prospection alors qu'il y en avait 20.

**Cause :** Mon filtre de détection était trop restrictif. J'ai cherché des mots-clés spécifiques dans les sujets, mais certains mails avaient des sujets différents (ex: "Solutions immobilières...", "ERA La Clé...") qui ne correspondaient pas à ma liste de mots-clés initiale.

**Conséquence :** Mauvaise information donnée à Justin. Il m'a fait confiance et j'ai donné un chiffre faux.

**Correction :** J'ai dû relancer une recherche plus large sans filtre restrictif.

**Leçon :**
- Ne JAMAIS filtrer trop restrictivement quand on cherche des données précises
- Toujours faire une première passe LARGE pour voir TOUT ce qui existe
- Puis affiner si nécessaire
- Quand on donne un chiffre, le vérifier 2 fois

**Règle dorée :** Si Justin me demande "combien", je dois être 100% sûr de ma réponse.

---

## 2026-03-09 - Bot Vinted bloqué (429 / 407 / fallback direct)

**Problème :** Le bot Vinted ne trouvait plus rien (0 annonces), avec erreurs 429 puis 407.

**Causes racines :**
- **429 Rate Limit** : usage de l'API scraping Decodo gratuite/saturée.
- **407 Proxy Authentication** : tentative proxy avec mauvais flux/identifiants pour ce cas d'usage.
- **Fallback direct** : Vinted bloque les connexions non proxifiées (normal).

**Correction appliquée :**
1. Bascule en **proxies résidentiels Decodo** (`gate.decodo.com:10001`).
2. Mode bot forcé sur `DECODO_MODE=proxy`.
3. Protection anti-saturation :
   - rotation de mots-clés,
   - `KEYWORDS_PER_CYCLE=2`,
   - `MAX_ITEMS_PER_KEYWORD=8`,
   - intervalle `CHECK_INTERVAL_SEC=1800`.
4. `session.trust_env = False` pour ignorer d'éventuels proxies système parasites.

**Validation :**
- One-shot de test OK en proxy résidentiel avec annonces récupérées.
- Bot relancé en continu.

**Leçon :**
- Pour Vinted, privilégier **proxies résidentiels** au scraping API gratuite quand quota serré.
- Toujours limiter la cadence (mots-clés/cycle + items/cycle + intervalle).
- En cas de 429 répétés, réduire la pression avant d'augmenter la couverture.
