# Statistique descriptive à une variable

## 1. Objectif du chapitre

Décrire une série statistique à une variable : reconnaître la sorte de variable, calculer effectifs et fréquences, représenter la série par le graphique qui lui convient, et calculer ses paramètres de position (mode, moyenne, médiane, quartiles).

### Ce que l'interro attend

| Type | Attendu |
|---|---|
| Définitions à énoncer | population, individu, échantillon, variable statistique, fréquence, quartiles |
| Procédures | tracer un diagramme circulaire, un diagramme en bâtons, un histogramme, un polygone des fréquences cumulées, une boîte à moustaches ; calculer mode, moyenne, médiane, Q₁ et Q₃ |
| Reconnaissance | qualitative, quantitative discrète ou continue |

## 2. Prérequis

- Calcul d'un pourcentage.
- Axe gradué, repère.

## 3. Conventions de notation

- Virgule décimale : `13,15`.
- Classes fermées à gauche, ouvertes à droite : `[150 ; 160[`.
- Effectif total noté $N$, fréquence $f = n / N$, écrite en décimal (`0,25`) ou en pourcentage (`25 %`).
- Moyenne notée $\bar{x}$, médiane $Me$, quartiles $Q_1$ et $Q_3$.
- Représentations graphiques :
  - « diagramme circulaire » pour une variable qualitative, angle = (effectif / $N$) × 360° ;
  - « diagramme en bâtons » pour une variable discrète, valeurs en abscisse, effectifs en ordonnée ; le « polygone des effectifs » joint le sommet des bâtons ;
  - « histogramme » pour une variable continue, aire proportionnelle à l'effectif ; classes d'amplitudes inégales ramenées à une amplitude de référence (hauteur = effectif × amplitude de référence / amplitude) ; le polygone des effectifs est fermé sur l'axe au milieu d'une classe vide de chaque côté ;
  - « polygone des effectifs (ou fréquences) cumulés croissants », points aux bornes supérieures des classes, départ à 0 sur la première borne ;
  - « boîte à moustaches », horizontale, de $Q_1$ à $Q_3$ coupée à la médiane, moustaches jusqu'au minimum et au maximum.

## 4. Notions, dans l'ordre d'enseignement

### 4.1 Population, individu, échantillon

> Une population est un ensemble d'individus ayant des caractéristiques propres et sur lesquels portent les observations.

> Un individu est un élément de la population.

> Un échantillon est un sous-ensemble de la population.

**Représentation graphique** : diagramme d'ensembles emboîtés : l'ensemble « Population » contient l'ensemble « Échantillon », une croix « individu » dans l'échantillon.

### 4.2 Variable statistique

> Le caractère étudié s'appelle la variable statistique.

- Qualitative : ses valeurs ne sont pas des nombres (couleur, moyen de transport…).
- Quantitative discrète : valeurs isolées (nombre de frères et sœurs, note entière…).
- Quantitative continue : toutes les valeurs d'un intervalle (taille, masse, âge…) ; on regroupe les valeurs en classes $[a ; b[$.

### 4.3 Effectifs et fréquences

L'effectif d'une valeur est le nombre d'individus qui prennent cette valeur. L'effectif total est noté $N$.

> La fréquence d'une valeur est le quotient de son effectif par l'effectif total : $f = n / N$.

### 4.4 Variable qualitative : diagramme circulaire

L'angle d'un secteur est proportionnel à l'effectif : angle = (effectif / $N$) × 360°.

**Exemple du cours** : moyen de transport de 30 élèves : Vélo 9 ; Bus 12 ; À pied 6 ; Voiture 3.

**Représentation graphique** : diagramme circulaire, secteurs Vélo 108°, Bus 144°, À pied 72°, Voiture 36°.

### 4.5 Variable discrète : diagramme en bâtons

En abscisse les valeurs, en ordonnée les effectifs ; en joignant le sommet des bâtons, on obtient le polygone des effectifs.

**Exemple du cours** : notes sur 20 de 20 élèves : 10 → 1 ; 11 → 2 ; 12 → 4 ; 13 → 5 ; 14 → 4 ; 15 → 2 ; 16 → 2.

**Représentation graphique** : diagramme en bâtons, axe « Note », axe « Effectifs », bâtons 10 → 1, 11 → 2, 12 → 4, 13 → 5, 14 → 4, 15 → 2, 16 → 2, avec le polygone des effectifs.

### 4.6 Variable continue : histogramme

Des rectangles accolés, un par classe ; l'aire de chaque rectangle est proportionnelle à l'effectif. Classes d'amplitudes inégales : hauteur = effectif × amplitude de référence / amplitude.

**Exemple du cours** : taille (cm) de 50 élèves : [150 ; 160[ → 8 ; [160 ; 165[ → 12 ; [165 ; 170[ → 15 ; [170 ; 180[ → 10 ; [180 ; 200[ → 5, amplitude de référence 5 cm.

**Représentation graphique** : histogramme, axe « Taille (cm) », axe « Effectif pour une amplitude de 5 cm », hauteurs 4 ; 12 ; 15 ; 5 ; 1,25, polygone des effectifs fermé.

### 4.7 Effectifs cumulés

L'effectif cumulé croissant d'une classe est la somme des effectifs de cette classe et des classes précédentes.

**Exemple du cours** : tailles : 8 ; 20 ; 35 ; 45 ; 50, soit 16 % ; 40 % ; 70 % ; 90 % ; 100 %.

**Représentation graphique** : polygone des fréquences cumulées croissantes, points (150 ; 0), (160 ; 16), (165 ; 40), (170 ; 70), (180 ; 90), (200 ; 100), axe vertical en %.

### 4.8 Paramètres de position

- Le mode est la valeur de plus grand effectif ; pour une variable continue, la classe modale.
- $\bar{x} = (n_1x_1 + n_2x_2 + \dots + n_kx_k) / N$ ; pour une variable continue, $x_i$ est le centre de la classe.
- La médiane $Me$ partage la série ordonnée en deux groupes de même effectif : si $N$ est impair, la valeur de rang $(N + 1)/2$ ; si $N$ est pair, la moyenne des valeurs de rang $N/2$ et $N/2 + 1$.

**Exemple du cours** : notes : mode 13 ; $\bar{x} = 263 / 20 = 13{,}15$ ; $Me = 13$.

### 4.9 Quartiles et boîte à moustaches

> Le premier quartile $Q_1$ est la plus petite valeur de la série telle qu'au moins 25 % des valeurs lui soient inférieures ou égales. Le troisième quartile $Q_3$ est la plus petite valeur telle qu'au moins 75 % des valeurs lui soient inférieures ou égales.

**Exemple du cours** : notes : $Q_1 = 12$ ; $Q_3 = 14$.

**Représentation graphique** : boîte à moustaches horizontale, minimum 10, $Q_1$ 12, médiane 13, $Q_3$ 14, maximum 16.

## 5. Vocabulaire

**Mots du cours, à employer** : population, individu, échantillon, variable statistique, qualitative, quantitative discrète, quantitative continue, classe, amplitude, effectif, fréquence, effectif cumulé, mode, classe modale, moyenne, médiane, quartile, diagramme circulaire, diagramme en bâtons, histogramme, polygone des effectifs, boîte à moustaches.

## 6. Exercices types

### 6.1 Variable discrète

#### 6.1.1

**Pointures de 25 élèves : 36 : 2 ; 37 : 4 ; 38 : 7 ; 39 : 6 ; 40 : 4 ; 41 : 2. a) Trace le diagramme en bâtons. b) Donne le mode. c) Calcule la moyenne. d) Détermine la médiane.**
**Méthode :** diagramme en bâtons ; $\bar{x}$ par la formule ; $Me$ = valeur de rang 13.
**Réponse :** b) 38 ; c) $\bar{x} = 962 / 25 = 38{,}48$ ; d) $Me = 38$.

#### 6.1.2

**Pour les pointures de 6.1.1, détermine $Q_1$ et $Q_3$ et trace la boîte à moustaches.**
**Méthode :** effectifs cumulés ; 25 % de 25 = 6,25, donc la 7ᵉ valeur ; 75 % de 25 = 18,75, donc la 19ᵉ.
**Réponse :** $Q_1 = 38$ ; $Q_3 = 39$.

### 6.2 Variable continue

#### 6.2.1

**Masse (kg) de 40 colis : [0 ; 2[ : 6 ; [2 ; 4[ : 10 ; [4 ; 8[ : 16 ; [8 ; 16[ : 8. a) Trace l'histogramme avec une amplitude de référence de 2 kg. b) Quelle classe a le plus grand effectif ?**
**Méthode :** hauteur = effectif × 2 / amplitude.
**Réponse :** a) hauteurs 6 ; 10 ; 8 ; 2 ; b) [4 ; 8[.

#### 6.2.2

**Pour les colis de 6.2.1, calcule les fréquences cumulées croissantes et trace leur polygone.**
**Méthode :** cumuler les effectifs, diviser par 40.
**Réponse :** 15 % ; 40 % ; 80 % ; 100 %.

### 6.3 Variable qualitative

#### 6.3.1

**40 élèves ont choisi une option : latin 10, sciences 18, langues 12. Calcule l'angle de chaque secteur du diagramme circulaire.**
**Méthode :** angle = (effectif / 40) × 360°.
**Réponse :** 90° ; 162° ; 108°.

## 7. Points à vérifier

Aucun.
