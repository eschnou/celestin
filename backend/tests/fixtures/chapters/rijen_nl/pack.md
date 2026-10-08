# Rekenkundige en meetkundige rijen

## 1. Doel van het hoofdstuk

Een rij beschrijven door haar termen en door haar algemene term, een rekenkundige of een meetkundige rij herkennen, om het even welke term en de som van de eerste termen van elke soort vinden, en beslissen van welke soort een lijst termen is.

### Wat de toets verwacht

| Soort | Verwacht |
|---|---|
| Definities om op te zeggen | rij, rekenkundige rij, verschil, meetkundige rij, reden |
| Procedures | $u_n$ vinden uit $u_1$ en $r$ of $q$; $r$ vinden uit twee termen; som van de eerste $n$ termen; beslissen of een rij rekenkundig, meetkundig of geen van beide is |
| Problemen | een situatie die rekenkundig of meetkundig blijkt te zijn (gestapelde rijen, verdubbeling) |

## 2. Voorkennis

- Machten met gehele exponenten.
- Een eerstegraadsvergelijking oplossen.
- Een punt $(x ; y)$ aflezen in een assenstelsel.

## 3. Notatieafspraken

- Decimale komma: `0,5`.
- Een rij wordt geschreven $(u_n)$; haar termen zijn $u_1, u_2, u_3, \dots$: **de eerste term is $u_1$**, nooit $u_0$. Voorbeeld: $u_1 = 5$.
- Verschil van een rekenkundige rij: $r$. Reden van een meetkundige rij: $q$. Som van de eerste $n$ termen: $S_n$.
- Verzamelingen geschreven met accolades en puntkomma's: `{2 ; 5}`.
- Grafieken: een rij wordt getekend als afzonderlijke punten $(n ; u_n)$, met $n$ op de horizontale as en $u_n$ op de verticale as; de punten worden nooit door een lijn verbonden.

## 4. Begrippen, in didactische volgorde

### 4.1 Rijen

> Een rij is een lijst getallen in een vaste volgorde: $u_1, u_2, u_3, \dots$ Het getal $u_n$ is de term met rangnummer $n$.

Een rij kan gegeven worden door een formule voor $u_n$ (de algemene term) of door een regel die van de ene term naar de volgende gaat.

**Voorbeelden uit de cursus**: $u_n = 3n - 2$ geeft $u_1 = 1$, $u_2 = 4$, $u_3 = 7$.

**Grafische voorstelling**: grafiek van $u_n = 3n - 2$, afzonderlijke punten $(1 ; 1)$, $(2 ; 4)$, $(3 ; 7)$, $(4 ; 10)$, $(5 ; 13)$, $(6 ; 16)$.

### 4.2 Rekenkundige rijen

> Een rij is rekenkundig als elke term uit de vorige verkregen wordt door hetzelfde getal $r$ erbij te tellen, het verschil genoemd: $u_{n+1} = u_n + r$.

- Algemene term: $u_n = u_1 + (n - 1)\,r$.
- Som van de eerste $n$ termen: $S_n = \dfrac{n\,(u_1 + u_n)}{2}$.

**Voorbeelden uit de cursus**: $u_1 = 5$ en $r = 3$: $u_{10} = 5 + 9 \cdot 3 = 32$ en $S_{10} = \dfrac{10\,(5 + 32)}{2} = 185$.

**Veelgemaakte fouten**: $u_n = u_1 + n\,r$ schrijven (het aantal stappen van $u_1$ naar $u_n$ is $n - 1$).

### 4.3 Meetkundige rijen

> Een rij is meetkundig als elke term uit de vorige verkregen wordt door met hetzelfde getal $q$ te vermenigvuldigen, de reden genoemd: $u_{n+1} = q \cdot u_n$.

- Algemene term: $u_n = u_1 \cdot q^{\,n-1}$.
- Som van de eerste $n$ termen: $S_n = u_1 \cdot \dfrac{1 - q^n}{1 - q}$. Voorwaarde: $q \neq 1$.

**Voorbeelden uit de cursus**: $u_1 = 2$ en $q = 3$: $u_5 = 2 \cdot 3^4 = 162$ en $S_5 = 2 \cdot \dfrac{1 - 3^5}{1 - 3} = 242$.

### 4.4 Welke soort rij?

Methode:
1. Bereken de verschillen $u_2 - u_1$, $u_3 - u_2$, $u_4 - u_3$. Zijn ze allemaal gelijk, dan is de rij rekenkundig en is $r$ dat verschil.
2. Zo niet, bereken dan de verhoudingen $\dfrac{u_2}{u_1}$, $\dfrac{u_3}{u_2}$, $\dfrac{u_4}{u_3}$. Zijn ze allemaal gelijk, dan is de rij meetkundig en is $q$ die verhouding.
3. Is geen van beide het geval, dan is de rij noch rekenkundig, noch meetkundig.

**Voorbeelden uit de cursus**: $3 ; 6 ; 12 ; 24$: de verschillen $3 ; 6 ; 12$ zijn niet gelijk, de verhoudingen $2 ; 2 ; 2$ wel: meetkundig met $q = 2$. $7 ; 4 ; 1 ; -2$: de verschillen zijn allemaal $-3$: rekenkundig met $r = -3$.

**Veelgemaakte fouten**: alleen de eerste twee termen testen.

## 5. Woordenschat

**Woorden van de cursus, te gebruiken**: rij, term, rangnummer, algemene term, rekenkundige rij, verschil, meetkundige rij, reden, som van de eerste $n$ termen.

**Woorden die je niet invoert**: Niets in de cursus.

## 6. Typische oefeningen

### 6.1 Rekenkundige rijen

#### 6.1.1

**Een rekenkundige rij heeft $u_1 = 4$ en $r = 5$. Zoek $u_{12}$ en $S_{12}$.**
**Methode:** $u_n = u_1 + (n - 1)\,r$, dan $S_n = \frac{n\,(u_1 + u_n)}{2}$.
**Antwoord:** $u_{12} = 4 + 11 \cdot 5 = 59$ en $S_{12} = \frac{12\,(4 + 59)}{2} = 378$.

#### 6.1.2

**Een rekenkundige rij heeft $u_3 = 11$ en $u_7 = 23$. Zoek $r$ en $u_1$.**
**Methode:** vier stappen scheiden $u_3$ van $u_7$, dus $4r = u_7 - u_3$; ga dan terug vanaf $u_3$.
**Antwoord:** $r = \frac{23 - 11}{4} = 3$ en $u_1 = 11 - 2 \cdot 3 = 5$.

### 6.2 Meetkundige rijen

#### 6.2.1

**Een meetkundige rij heeft $u_1 = 3$ en $q = 2$. Zoek $u_8$.**
**Methode:** $u_n = u_1 \cdot q^{\,n-1}$.
**Antwoord:** $u_8 = 3 \cdot 2^7 = 384$.

#### 6.2.2

**Een meetkundige rij heeft $u_1 = 1000$ en $q = 0,5$. Zoek $u_4$ en $S_4$.**
**Methode:** algemene term, dan de somformule met $q \neq 1$.
**Antwoord:** $u_4 = 1000 \cdot 0,5^3 = 125$ en $S_4 = 1000 \cdot \frac{1 - 0,5^4}{1 - 0,5} = 1875$.

### 6.3 Welke soort rij?

#### 6.3.1

**Beslis van welke soort deze rij is: $2 ; 6 ; 18 ; 54$.**
**Methode:** verschillen, dan verhoudingen.
**Antwoord:** de verschillen $4 ; 12 ; 36$ zijn niet gelijk; de verhoudingen zijn allemaal $3$: meetkundig met $q = 3$.

#### 6.3.2

**Beslis van welke soort deze rij is: $20 ; 17 ; 14 ; 11$.**
**Methode:** verschillen, dan verhoudingen.
**Antwoord:** de verschillen zijn allemaal $-3$: rekenkundig met $r = -3$.

#### 6.3.3

**Beslis van welke soort deze rij is: $1 ; 4 ; 9 ; 16$.**
**Methode:** verschillen, dan verhoudingen.
**Antwoord:** de verschillen $3 ; 5 ; 7$ zijn niet gelijk en de verhoudingen $4 ; 2,25 ; \dots$ zijn niet gelijk: geen van beide.

#### 6.3.4

**Schrijf de eerste vier termen van $u_n = 2n + 1$ en zeg van welke soort rij het is.**
**Methode:** bereken $u_1, \dots, u_4$ en pas dan de methode van § 4.4 toe.
**Antwoord:** niet verbeterd in de cursus

### 6.4 Problemen

#### 6.4.1

**Een stapel boomstammen heeft 12 stammen in de onderste rij, en elke rij heeft één stam minder dan de rij eronder. Er zijn 8 rijen. Hoeveel stammen telt de stapel?**
**Methode:** de rijen vormen een rekenkundige rij met $u_1 = 12$ en $r = -1$; tel de 8 termen op.
**Antwoord:** $u_8 = 12 - 7 = 5$ en $S_8 = \frac{8\,(12 + 5)}{2} = 68$ stammen.

#### 6.4.2

**Een cultuur telt in het begin 500 bacteriën en het aantal verdubbelt elk uur. Hoeveel bacteriën zijn er na 4 uur?**
**Methode:** $u_1 = 500$ is het aantal in het begin, dus het aantal na 4 uur is $u_5$; meetkundige rij met $q = 2$.
**Antwoord:** $u_5 = 500 \cdot 2^4 = 8000$ bacteriën.

## 7. Na te kijken punten

Geen.
