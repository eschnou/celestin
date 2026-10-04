# Géométrie analytique plane

## 1. Objectif du chapitre

Repérer des points dans un repère orthonormé, calculer le milieu d'un segment et la distance entre deux points, écrire l'équation d'une droite, reconnaître des droites parallèles ou perpendiculaires et calculer les coordonnées du point d'intersection de deux droites sécantes.

### Ce que l'interro attend

| Type | Attendu |
|---|---|
| Définitions à énoncer | repère orthonormé, droites parallèles, droites perpendiculaires |
| Procédures | coordonnées du milieu d'un segment, distance entre deux points, équation d'une droite passant par deux points, coordonnées du point d'intersection de deux droites |
| Reconnaissance | droites parallèles ou perpendiculaires, triangle rectangle |

## 2. Prérequis

- Théorème de Pythagore.
- Résolution d'une équation du premier degré.
- Calcul avec des fractions.

## 3. Conventions de notation

- Virgule décimale : `4,5`.
- Coordonnées d'un point : abscisse puis ordonnée, séparées par un point-virgule : `A(2 ; 3)`.
- Segment `[AB]`, droite `AB`, distance `|AB|`.
- Équation d'une droite : `d ≡ y = mx + p`, où `m` est le coefficient angulaire et `p` l'ordonnée à l'origine.
- Figures : dans un repère orthonormé ; points marqués d'une croix et nommés par une lettre majuscule ; angle droit codé par un petit carré ; segments de même longueur codés par le même nombre de traits.

## 4. Notions, dans l'ordre d'enseignement

### 4.1 Repère orthonormé et coordonnées

> Un repère est orthonormé si ses axes sont perpendiculaires et ont la même unité.

Chaque point du plan est repéré par ses coordonnées : son abscisse, lue sur l'axe horizontal, puis son ordonnée, lue sur l'axe vertical.

**Exemple du cours** : $A(1 ; 1)$, $B(4 ; 5)$ et $C(8 ; 2)$.

**Représentation graphique** : repère orthonormé, points A, B et C marqués d'une croix.

### 4.2 Milieu et distance

- Milieu $M$ du segment $[AB]$ : $M\left(\frac{x_A + x_B}{2} ; \frac{y_A + y_B}{2}\right)$.
- Distance entre $A$ et $B$ : $|AB| = \sqrt{(x_B - x_A)^2 + (y_B - y_A)^2}$.

**Exemple du cours** : le milieu de $[AC]$ est $M(4{,}5 ; 1{,}5)$ ; $|AB| = \sqrt{3^2 + 4^2} = 5$ et $|BC| = \sqrt{4^2 + (-3)^2} = 5$.

### 4.3 Équation d'une droite

> Une droite qui n'est pas parallèle à l'axe vertical a une équation de la forme $y = mx + p$ ; $m$ est son coefficient angulaire et $p$ son ordonnée à l'origine.

- Coefficient angulaire de la droite $AB$ : $m = \frac{y_B - y_A}{x_B - x_A}$.
- On trouve $p$ en remplaçant $x$ et $y$ par les coordonnées d'un point de la droite.

**Exemple du cours** : la droite $AB$, avec $A(1 ; 1)$ et $B(4 ; 5)$ : $m = \frac{5 - 1}{4 - 1} = \frac{4}{3}$ ; $1 = \frac{4}{3} \cdot 1 + p$, donc $p = -\frac{1}{3}$ et $AB \equiv y = \frac{4}{3}x - \frac{1}{3}$.

### 4.4 Droites parallèles et perpendiculaires

> Deux droites sont parallèles si elles ont le même coefficient angulaire.

> Deux droites sont perpendiculaires si le produit de leurs coefficients angulaires vaut $-1$.

**Exemple du cours** : le triangle $ABC$ est rectangle en $B$ : $m_{AB} = \frac{4}{3}$, $m_{BC} = \frac{2 - 5}{8 - 4} = -\frac{3}{4}$ et $\frac{4}{3} \cdot \left(-\frac{3}{4}\right) = -1$. Il est aussi isocèle : $|AB| = |BC| = 5$.

**Représentation graphique** : dans un repère orthonormé, le triangle $ABC$ avec $A(1 ; 1)$, $B(4 ; 5)$ et $C(8 ; 2)$, les points marqués d'une croix, l'angle droit en $B$ codé par un petit carré, $[AB]$ et $[BC]$ codés d'un trait.

### 4.5 Intersection de deux droites

Le point d'intersection de deux droites sécantes appartient aux deux droites : ses coordonnées vérifient les deux équations. On égale les deux expressions de $y$ pour trouver $x$, puis on calcule $y$.

**Exemple du cours** : $d_1 \equiv y = 2x - 1$ et $d_2 \equiv y = -x + 5$ : $2x - 1 = -x + 5$, donc $3x = 6$ et $x = 2$ ; $y = 2 \cdot 2 - 1 = 3$. Le point d'intersection est $I(2 ; 3)$.

**Représentation graphique** : dans un repère orthonormé, les droites $d_1$ et $d_2$ et leur point d'intersection $I$ marqué d'une croix.

## 5. Vocabulaire

**Mots du cours, à employer** : repère orthonormé, abscisse, ordonnée, coordonnées, milieu, distance, coefficient angulaire, ordonnée à l'origine, droites parallèles, droites perpendiculaires, droites sécantes, point d'intersection, triangle rectangle, triangle isocèle.

## 6. Exercices types

### 6.1 Milieu, distance et triangle rectangle

#### 6.1.1

**Soit $A(-2 ; 1)$ et $B(4 ; 9)$. Calcule les coordonnées du milieu $M$ de $[AB]$ et la distance $|AB|$.**
**Méthode :** formules du milieu et de la distance.
**Réponse :** $M(1 ; 5)$ ; $|AB| = \sqrt{6^2 + 8^2} = 10$.

#### 6.1.2

**Démontre que le triangle $PQR$, avec $P(0 ; 0)$, $Q(4 ; 2)$ et $R(3 ; 4)$, est rectangle.**
**Méthode :** calculer les coefficients angulaires des côtés ; deux côtés sont perpendiculaires si le produit de leurs coefficients angulaires vaut $-1$.
**Réponse :** $m_{PQ} = \frac{1}{2}$ et $m_{QR} = -2$ ; leur produit vaut $-1$ : le triangle $PQR$ est rectangle en $Q$.

### 6.2 Droites

#### 6.2.1

**Détermine l'équation de la droite $d$ passant par $A(1 ; 3)$ et $B(3 ; 7)$.**
**Méthode :** $m = \frac{y_B - y_A}{x_B - x_A}$, puis $p$ avec les coordonnées de $A$.
**Réponse :** $m = 2$ et $p = 1$ : $d \equiv y = 2x + 1$.

#### 6.2.2

**Calcule les coordonnées du point d'intersection des droites $d_1 \equiv y = 3x - 2$ et $d_2 \equiv y = -x + 6$.**
**Méthode :** égaler les deux expressions de $y$, puis calculer $y$.
**Réponse :** $3x - 2 = -x + 6$, donc $4x = 8$ et $x = 2$ ; $y = 4$ : $I(2 ; 4)$.

#### 6.2.3

**Les droites $d \equiv y = 2x + 1$ et $d' \equiv y = -\frac{1}{2}x + 3$ sont-elles parallèles, perpendiculaires ou ni l'un ni l'autre ?**
**Méthode :** comparer les coefficients angulaires, puis calculer leur produit.
**Réponse :** $2 \cdot \left(-\frac{1}{2}\right) = -1$ : elles sont perpendiculaires.

## 7. Points à vérifier

Aucun.
