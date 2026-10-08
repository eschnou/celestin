# Beschrijvende statistiek met één veranderlijke

## 1. Doel van het hoofdstuk

Het soort van een statistische veranderlijke herkennen, de grafiek kiezen en aflezen die erbij past (cirkeldiagram, staafdiagram, histogram, cumulatieve frequentiepolygoon), en het gemiddelde, de mediaan, de modus en de kwartielen van een reeks berekenen, met de boxplot.

### Wat de toets verwacht

| Soort | Verwacht |
|---|---|
| Definities om op te zeggen | populatie, individu, steekproef, statistische veranderlijke, relatieve frequentie |
| Procedures | hoek van een sector in een cirkeldiagram; hoogte van een staaf van een histogram bij klassen van verschillende breedte; cumulatieve frequenties; gemiddelde, mediaan, modus, $Q_1$ en $Q_3$ |
| Herkenning | het soort van een veranderlijke en de grafiek die erbij past |
| Grafieken om te tekenen | staafdiagram met frequentiepolygoon, histogram, cumulatieve frequentiepolygoon, boxplot |

## 2. Voorkennis

- Breuken, procenten en decimale getallen.
- Punten aflezen en tekenen in een assenstelsel.
- Getallen ordenen.

## 3. Notatieafspraken

- Decimale komma: `2,125`.
- Klassen bevatten hun linkergrens en sluiten hun rechtergrens uit: `[10 ; 20[`.
- Totaal geschreven $N$, frequentie $n$, relatieve frequentie $f = n / N$, geschreven als decimaal getal (`0,25`) of als percentage (`25 %`).
- Gemiddelde geschreven $\bar{x}$, mediaan $M$, kwartielen $Q_1$ en $Q_3$.
- Grafische voorstellingen:
  - “cirkeldiagram” voor een kwalitatieve veranderlijke, hoek = (frequentie / $N$) × 360°;
  - “staafdiagram” voor een discrete veranderlijke, waarden op de horizontale as, frequenties op de verticale as; de “frequentiepolygoon” verbindt de toppen van de staven;
  - “histogram” voor een continue veranderlijke, oppervlakte evenredig met de frequentie; klassen van verschillende breedte worden herleid tot een referentiebreedte (hoogte = frequentie × referentiebreedte / klassenbreedte);
  - “cumulatieve frequentiepolygoon”, punten op de bovengrenzen van de klassen, beginnend met 0 op de ondergrens van de eerste klasse;
  - “boxplot”, horizontaal, van $Q_1$ tot $Q_3$ verdeeld door de mediaan, met snorharen tot het minimum en het maximum.

## 4. Begrippen, in didactische volgorde

### 4.1 Populatie, individu, steekproef

> Een populatie is de verzameling van alle individuen waarover een onderzoek gaat.

> Een individu is één element van de populatie.

> Een steekproef is een deel van de populatie dat werkelijk waargenomen wordt.

**Grafische voorstelling**: verzamelingendiagram met ingesloten verzamelingen: de verzameling “Populatie” bevat de verzameling “Steekproef”, een kruisje “individu” binnen de steekproef.

### 4.2 Statistische veranderlijke

> De eigenschap die onderzocht wordt, heet de statistische veranderlijke.

- Kwalitatief: haar waarden zijn geen getallen (kleur, lievelingssport).
- Kwantitatief discreet: ze neemt alleen afzonderlijke waarden aan (aantal boeken, schoenmaat).
- Kwantitatief continu: ze kan elke waarde van een interval aannemen (lengte, massa, tijd); de waarden worden gegroepeerd in klassen $[a ; b[$.

### 4.3 Frequentie en relatieve frequentie

De frequentie van een waarde is het aantal individuen met die waarde; het totaal is $N$. De relatieve frequentie is $f = \dfrac{n}{N}$, geschreven als decimaal getal ($0{,}25$) of als percentage ($25\ \%$).

### 4.4 Een kwalitatieve veranderlijke voorstellen

**Voorbeelden uit de cursus**: lievelingssport van 40 leerlingen: voetbal 14, basketbal 10, zwemmen 8, tennis 8. Hoek van een sector: $\dfrac{\text{frequentie}}{N} \times 360°$.

**Grafische voorstelling**: cirkeldiagram, sectoren Voetbal 126°, Basketbal 90°, Zwemmen 72°, Tennis 72°.

### 4.5 Een discrete veranderlijke voorstellen

**Voorbeelden uit de cursus**: aantal boeken dat 24 leerlingen vorige maand lazen: 0 → 3, 1 → 5, 2 → 7, 3 → 5, 4 → 3, 5 → 1.

**Grafische voorstelling**: staafdiagram, as “Gelezen boeken”, as “Frequentie”, staven 0 → 3, 1 → 5, 2 → 7, 3 → 5, 4 → 3, 5 → 1, met de frequentiepolygoon.

### 4.6 Een continue veranderlijke voorstellen

**Voorbeelden uit de cursus**: dagelijkse reistijd naar school van 50 leerlingen: $[0 ; 10[$: 5 ; $[10 ; 20[$: 10 ; $[20 ; 30[$: 15 ; $[30 ; 50[$: 12 ; $[50 ; 90[$: 8.

De rechthoeken raken elkaar, één per klasse; de oppervlakte van een rechthoek is evenredig met de frequentie. Bij klassen van verschillende breedte neemt de cursus een referentiebreedte (hier 10 minuten): hoogte $= \dfrac{\text{frequentie} \times 10}{\text{klassenbreedte}}$.

**Grafische voorstelling**: histogram, as “Reistijd (min)” met de waarden 0, 10, 20, 30, 50, 90, as “Frequentie per 10 minuten”, hoogten 5 ; 10 ; 15 ; 6 ; 2.

### 4.7 Cumulatieve frequenties

De cumulatieve frequentie van een klasse is de som van haar frequentie en die van de klassen ervoor.

**Voorbeelden uit de cursus**: reistijden: 5 ; 15 ; 30 ; 42 ; 50, dus de cumulatieve relatieve frequenties zijn 10 % ; 30 % ; 60 % ; 84 % ; 100 %.

**Grafische voorstelling**: cumulatieve frequentiepolygoon, punten $(0 ; 0)$, $(10 ; 10)$, $(20 ; 30)$, $(30 ; 60)$, $(50 ; 84)$, $(90 ; 100)$, verticale as in %.

### 4.8 Modus, gemiddelde en mediaan

- Modus: de waarde met de grootste frequentie; bij een continue veranderlijke, de modale klasse.
- Gemiddelde: $\bar{x} = \dfrac{n_1 x_1 + n_2 x_2 + \dots + n_k x_k}{N}$. Bij een continue veranderlijke is $x_i$ het midden van elke klasse.
- Mediaan $M$: ze verdeelt de geordende gegevens in twee groepen van gelijke grootte. Is $N$ oneven, dan is het de waarde op plaats $\frac{N+1}{2}$; is $N$ even, dan is het het gemiddelde van de waarden op plaats $\frac{N}{2}$ en $\frac{N}{2} + 1$.

**Voorbeelden uit de cursus**: boeken: modus 2 ; $\bar{x} = \dfrac{51}{24} = 2{,}125$ ; $M = 2$.

### 4.9 Kwartielen en boxplot

> Het eerste kwartiel $Q_1$ is de kleinste waarde van de gegevens waarvoor minstens 25 % van de waarden kleiner dan of gelijk aan die waarde is. Het derde kwartiel $Q_3$ is de kleinste waarde waarvoor minstens 75 % van de waarden kleiner dan of gelijk aan die waarde is.

**Voorbeelden uit de cursus**: boeken: $Q_1 = 1$ ; $Q_3 = 3$.

**Grafische voorstelling**: horizontale boxplot, minimum 0, $Q_1$ 1, mediaan 2, $Q_3$ 3, maximum 5.

## 5. Woordenschat

**Woorden van de cursus, te gebruiken**: populatie, individu, steekproef, statistische veranderlijke, kwalitatief, kwantitatief discreet, kwantitatief continu, klasse, klassenbreedte, frequentie, relatieve frequentie, cumulatieve frequentie, modus, modale klasse, gemiddelde, mediaan, kwartiel, cirkeldiagram, staafdiagram, histogram, frequentiepolygoon, boxplot.

**Woorden die je niet invoert**: Niets in de cursus.

## 6. Typische oefeningen

### 6.1 Discrete veranderlijke

#### 6.1.1

**De leeftijden van de 20 leden van een schaakclub: 14: 3 ; 15: 5 ; 16: 6 ; 17: 4 ; 18: 2. a) Teken het staafdiagram. b) Geef de modus. c) Bereken het gemiddelde. d) Zoek de mediaan.**
**Methode:** staafdiagram; $\bar{x}$ met de formule; $M$ is het gemiddelde van de waarden op plaats 10 en 11.
**Antwoord:** b) 16 ; c) $\bar{x} = 317 / 20 = 15{,}85$ ; d) $M = 16$.

#### 6.1.2

**Zoek voor de leeftijden van 6.1.1 $Q_1$ en $Q_3$ en teken de boxplot.**
**Methode:** cumulatieve frequenties; 25 % van 20 is 5, dus de 5e waarde; 75 % van 20 is 15, dus de 15e waarde.
**Antwoord:** $Q_1 = 15$ ; $Q_3 = 17$.

### 6.2 Continue veranderlijke

#### 6.2.1

**Wachttijd van 40 patiënten bij een kliniek: $[0 ; 5[$: 4 ; $[5 ; 10[$: 8 ; $[10 ; 20[$: 16 ; $[20 ; 40[$: 12. a) Teken het histogram met een referentiebreedte van 5 minuten. b) Welke klasse heeft de grootste frequentie?**
**Methode:** hoogte = frequentie × 5 / klassenbreedte.
**Antwoord:** a) hoogten 4 ; 8 ; 8 ; 3 ; b) $[10 ; 20[$.

#### 6.2.2

**Bereken voor de wachttijden van 6.2.1 de cumulatieve relatieve frequenties en teken hun polygoon.**
**Methode:** de frequenties optellen, delen door 40.
**Antwoord:** 10 % ; 30 % ; 70 % ; 100 %.

### 6.3 Kwalitatieve veranderlijke

#### 6.3.1

**48 leerlingen kozen hun middagmaal: pasta 20, salade 12, broodje 16. Bereken de hoek van elke sector van het cirkeldiagram.**
**Methode:** hoek = frequentie / 48 × 360°.
**Antwoord:** 150° ; 90° ; 120°.

## 7. Na te kijken punten

Geen.
