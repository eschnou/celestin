# Les suites numériques

## 1. Objectif du chapitre

Décrire une suite par ses termes et par son terme général, reconnaître une suite arithmétique ou géométrique, calculer un terme quelconque et la somme des premiers termes de chaque sorte, et décider de quelle sorte est une suite donnée par une liste de termes.

### Ce que l'interro attend

| Type | Attendu |
|---|---|
| Définitions à énoncer | suite, suite arithmétique, raison d'une suite arithmétique, suite géométrique, raison d'une suite géométrique |
| Procédures | calculer $u_n$ à partir de $u_1$ et de $r$ ou $q$ ; trouver $r$ à partir de deux termes ; somme des $n$ premiers termes ; décider si une suite est arithmétique, géométrique ou ni l'une ni l'autre |
| Problèmes | une situation qui se révèle arithmétique ou géométrique (rangées empilées, doublement) |

## 2. Prérequis

- Puissances à exposant entier.
- Résolution d'une équation du premier degré.
- Lecture d'un point $(x\ ;\ y)$ dans un repère.

## 3. Conventions de notation

- Virgule décimale : `0,5`.
- Une suite est notée $(u_n)$ ; ses termes sont $u_1, u_2, u_3, \dots$ : **le premier terme est $u_1$**, jamais $u_0$. Exemple : $u_1 = 5$.
- Raison d'une suite arithmétique : $r$. Raison d'une suite géométrique : $q$. Somme des $n$ premiers termes : $S_n$.
- Ensembles écrits avec des accolades et des points-virgules : `{2 ; 5}`.
- Graphiques : une suite se représente par des points isolés $(n\ ;\ u_n)$, $n$ en abscisse et $u_n$ en ordonnée ; les points ne sont jamais reliés par un trait.

## 4. Notions, dans l'ordre d'enseignement

### 4.1 Les suites

> Une suite est une liste de nombres rangés dans un ordre précis : $u_1, u_2, u_3, \dots$ Le nombre $u_n$ est le terme de rang $n$.

Une suite peut être donnée par une formule pour $u_n$ (le terme général) ou par une règle qui permet de passer d'un terme au suivant.

**Exemples du cours** : $u_n = 3n - 2$ donne $u_1 = 1$, $u_2 = 4$, $u_3 = 7$.

**Représentation graphique** : graphique de $u_n = 3n - 2$, points isolés $(1\ ;\ 1)$, $(2\ ;\ 4)$, $(3\ ;\ 7)$, $(4\ ;\ 10)$, $(5\ ;\ 13)$, $(6\ ;\ 16)$.

### 4.2 Les suites arithmétiques

> Une suite est arithmétique si chaque terme s'obtient en ajoutant au précédent le même nombre $r$, appelé raison : $u_{n+1} = u_n + r$.

- Terme général : $u_n = u_1 + (n - 1)\,r$.
- Somme des $n$ premiers termes : $S_n = \dfrac{n\,(u_1 + u_n)}{2}$.

**Exemples du cours** : $u_1 = 5$ et $r = 3$ : $u_{10} = 5 + 9 \cdot 3 = 32$ et $S_{10} = \dfrac{10\,(5 + 32)}{2} = 185$.

**Erreurs fréquentes** : écrire $u_n = u_1 + n\,r$ (de $u_1$ à $u_n$, il y a $n - 1$ pas).

### 4.3 Les suites géométriques

> Une suite est géométrique si chaque terme s'obtient en multipliant le précédent par le même nombre $q$, appelé raison : $u_{n+1} = q \cdot u_n$.

- Terme général : $u_n = u_1 \cdot q^{\,n-1}$.
- Somme des $n$ premiers termes : $S_n = u_1 \cdot \dfrac{1 - q^n}{1 - q}$. Condition : $q \neq 1$.

**Exemples du cours** : $u_1 = 2$ et $q = 3$ : $u_5 = 2 \cdot 3^4 = 162$ et $S_5 = 2 \cdot \dfrac{1 - 3^5}{1 - 3} = 242$.

### 4.4 De quelle sorte est la suite ?

Méthode :
1. Calculer les différences $u_2 - u_1$, $u_3 - u_2$, $u_4 - u_3$. Si elles sont toutes égales, la suite est arithmétique et $r$ est cette différence.
2. Sinon, calculer les quotients $\dfrac{u_2}{u_1}$, $\dfrac{u_3}{u_2}$, $\dfrac{u_4}{u_3}$. S'ils sont tous égaux, la suite est géométrique et $q$ est ce quotient.
3. Si ni l'un ni l'autre, la suite n'est ni arithmétique ni géométrique.

**Exemples du cours** : $3, 6, 12, 24$ : les différences $3, 6, 12$ ne sont pas égales, les quotients $2, 2, 2$ le sont : géométrique de raison $q = 2$. $7, 4, 1, -2$ : les différences valent toutes $-3$ : arithmétique de raison $r = -3$.

**Erreurs fréquentes** : ne tester que les deux premiers termes.

## 5. Vocabulaire

**Mots du cours, à employer** : suite, terme, rang, terme général, suite arithmétique, raison, suite géométrique, somme des $n$ premiers termes.

**Mots à ne pas introduire** : Rien dans la matière.

## 6. Exercices types

### 6.1 Suites arithmétiques

#### 6.1.1

**Une suite arithmétique a $u_1 = 4$ et $r = 5$. Calcule $u_{12}$ et $S_{12}$.**
**Méthode :** $u_n = u_1 + (n - 1)\,r$, puis $S_n = \frac{n\,(u_1 + u_n)}{2}$.
**Réponse :** $u_{12} = 4 + 11 \cdot 5 = 59$ et $S_{12} = \frac{12\,(4 + 59)}{2} = 378$.

#### 6.1.2

**Une suite arithmétique a $u_3 = 11$ et $u_7 = 23$. Calcule $r$ et $u_1$.**
**Méthode :** quatre pas séparent $u_3$ de $u_7$, donc $4r = u_7 - u_3$ ; ensuite on remonte depuis $u_3$.
**Réponse :** $r = \frac{23 - 11}{4} = 3$ et $u_1 = 11 - 2 \cdot 3 = 5$.

### 6.2 Suites géométriques

#### 6.2.1

**Une suite géométrique a $u_1 = 3$ et $q = 2$. Calcule $u_8$.**
**Méthode :** $u_n = u_1 \cdot q^{\,n-1}$.
**Réponse :** $u_8 = 3 \cdot 2^7 = 384$.

#### 6.2.2

**Une suite géométrique a $u_1 = 1000$ et $q = 0,5$. Calcule $u_4$ et $S_4$.**
**Méthode :** terme général, puis formule de la somme avec $q \neq 1$.
**Réponse :** $u_4 = 1000 \cdot 0,5^3 = 125$ et $S_4 = 1000 \cdot \frac{1 - 0,5^4}{1 - 0,5} = 1875$.

### 6.3 De quelle sorte est la suite ?

#### 6.3.1

**Décide de quelle sorte est la suite $2, 6, 18, 54$.**
**Méthode :** les différences, puis les quotients.
**Réponse :** les différences $4, 12, 36$ ne sont pas égales ; les quotients valent tous $3$ : géométrique de raison $q = 3$.

#### 6.3.2

**Décide de quelle sorte est la suite $20, 17, 14, 11$.**
**Méthode :** les différences, puis les quotients.
**Réponse :** les différences valent toutes $-3$ : arithmétique de raison $r = -3$.

#### 6.3.3

**Décide de quelle sorte est la suite $1, 4, 9, 16$.**
**Méthode :** les différences, puis les quotients.
**Réponse :** les différences $3, 5, 7$ ne sont pas égales et les quotients $4 ; 2,25 ; \dots$ non plus : ni l'une ni l'autre.

#### 6.3.4

**Écris les quatre premiers termes de $u_n = 2n + 1$ et dis de quelle sorte est la suite.**
**Méthode :** calculer $u_1, \dots, u_4$, puis appliquer la méthode du § 4.4.
**Réponse :** non corrigé dans la matière

### 6.4 Problèmes

#### 6.4.1

**Une pile de rondins compte 12 rondins dans la rangée du bas, et chaque rangée en a un de moins que celle du dessous. Il y a 8 rangées. Combien y a-t-il de rondins dans la pile ?**
**Méthode :** les rangées forment une suite arithmétique avec $u_1 = 12$ et $r = -1$ ; additionner les 8 termes.
**Réponse :** $u_8 = 12 - 7 = 5$ et $S_8 = \frac{8\,(12 + 5)}{2} = 68$ rondins.

#### 6.4.2

**Une culture compte 500 bactéries au départ et leur nombre double toutes les heures. Combien y a-t-il de bactéries après 4 heures ?**
**Méthode :** $u_1 = 500$ est le nombre au départ, donc le nombre après 4 heures est $u_5$ ; suite géométrique de raison $q = 2$.
**Réponse :** $u_5 = 500 \cdot 2^4 = 8000$ bactéries.

## 7. Points à vérifier

Aucun.
