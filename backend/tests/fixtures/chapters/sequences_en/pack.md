# Arithmetic and geometric sequences

## 1. Chapter objective

Describe a sequence by its terms and by its general term, recognise an arithmetic or a geometric sequence, find any term and the sum of the first terms of each kind, and decide which kind of sequence a list of terms is.

### What the test expects

| Type | Expected |
|---|---|
| Definitions to state | sequence, arithmetic sequence, common difference, geometric sequence, common ratio |
| Procedures | find $u_n$ from $u_1$ and $r$ or $q$; find $r$ from two terms; sum of the first $n$ terms; decide whether a sequence is arithmetic, geometric or neither |
| Problems | a situation that turns out to be arithmetic or geometric (stacked rows, doubling) |

## 2. Prerequisites

- Powers with whole-number exponents.
- Solving a first-degree equation.
- Reading a point $(x, y)$ in a coordinate system.

## 3. Notation conventions

- Decimal point: `0.5`.
- A sequence is written $(u_n)$; its terms are $u_1, u_2, u_3, \dots$: **the first term is $u_1$**, never $u_0$. Example: $u_1 = 5$.
- Common difference of an arithmetic sequence: $r$. Common ratio of a geometric sequence: $q$. Sum of the first $n$ terms: $S_n$.
- Sets written with braces and commas: `{2, 5}`.
- Graphs: a sequence is drawn as isolated points $(n, u_n)$, with $n$ on the horizontal axis and $u_n$ on the vertical axis; the points are never joined by a line.

## 4. Concepts, in teaching order

### 4.1 Sequences

> A sequence is a list of numbers in a definite order: $u_1, u_2, u_3, \dots$ The number $u_n$ is the term of position $n$.

A sequence can be given by a formula for $u_n$ (the general term) or by a rule that goes from one term to the next.

**Examples from the course**: $u_n = 3n - 2$ gives $u_1 = 1$, $u_2 = 4$, $u_3 = 7$.

**Graphical representation**: graph of $u_n = 3n - 2$, isolated points $(1, 1)$, $(2, 4)$, $(3, 7)$, $(4, 10)$, $(5, 13)$, $(6, 16)$.

### 4.2 Arithmetic sequences

> A sequence is arithmetic if each term is obtained from the previous one by adding the same number $r$, called the common difference: $u_{n+1} = u_n + r$.

- General term: $u_n = u_1 + (n - 1)\,r$.
- Sum of the first $n$ terms: $S_n = \dfrac{n\,(u_1 + u_n)}{2}$.

**Examples from the course**: $u_1 = 5$ and $r = 3$: $u_{10} = 5 + 9 \cdot 3 = 32$ and $S_{10} = \dfrac{10\,(5 + 32)}{2} = 185$.

**Common mistakes**: writing $u_n = u_1 + n\,r$ (the number of steps from $u_1$ to $u_n$ is $n - 1$).

### 4.3 Geometric sequences

> A sequence is geometric if each term is obtained from the previous one by multiplying by the same number $q$, called the common ratio: $u_{n+1} = q \cdot u_n$.

- General term: $u_n = u_1 \cdot q^{\,n-1}$.
- Sum of the first $n$ terms: $S_n = u_1 \cdot \dfrac{1 - q^n}{1 - q}$. Condition: $q \neq 1$.

**Examples from the course**: $u_1 = 2$ and $q = 3$: $u_5 = 2 \cdot 3^4 = 162$ and $S_5 = 2 \cdot \dfrac{1 - 3^5}{1 - 3} = 242$.

### 4.4 Which kind of sequence?

Method:
1. Compute the differences $u_2 - u_1$, $u_3 - u_2$, $u_4 - u_3$. If they are all equal, the sequence is arithmetic and $r$ is that difference.
2. Otherwise compute the ratios $\dfrac{u_2}{u_1}$, $\dfrac{u_3}{u_2}$, $\dfrac{u_4}{u_3}$. If they are all equal, the sequence is geometric and $q$ is that ratio.
3. If neither, the sequence is neither arithmetic nor geometric.

**Examples from the course**: $3, 6, 12, 24$: the differences $3, 6, 12$ are not equal, the ratios $2, 2, 2$ are: geometric with $q = 2$. $7, 4, 1, -2$: the differences are all $-3$: arithmetic with $r = -3$.

**Common mistakes**: testing only the first two terms.

## 5. Vocabulary

**Course words, to be used**: sequence, term, position, general term, arithmetic sequence, common difference, geometric sequence, common ratio, sum of the first $n$ terms.

**Words not to introduce**: Nothing in the material.

## 6. Typical exercises

### 6.1 Arithmetic sequences

#### 6.1.1

**An arithmetic sequence has $u_1 = 4$ and $r = 5$. Find $u_{12}$ and $S_{12}$.**
**Method:** $u_n = u_1 + (n - 1)\,r$, then $S_n = \frac{n\,(u_1 + u_n)}{2}$.
**Answer:** $u_{12} = 4 + 11 \cdot 5 = 59$ and $S_{12} = \frac{12\,(4 + 59)}{2} = 378$.

#### 6.1.2

**An arithmetic sequence has $u_3 = 11$ and $u_7 = 23$. Find $r$ and $u_1$.**
**Method:** four steps separate $u_3$ from $u_7$, so $4r = u_7 - u_3$; then go back from $u_3$.
**Answer:** $r = \frac{23 - 11}{4} = 3$ and $u_1 = 11 - 2 \cdot 3 = 5$.

### 6.2 Geometric sequences

#### 6.2.1

**A geometric sequence has $u_1 = 3$ and $q = 2$. Find $u_8$.**
**Method:** $u_n = u_1 \cdot q^{\,n-1}$.
**Answer:** $u_8 = 3 \cdot 2^7 = 384$.

#### 6.2.2

**A geometric sequence has $u_1 = 1000$ and $q = 0.5$. Find $u_4$ and $S_4$.**
**Method:** general term, then the sum formula with $q \neq 1$.
**Answer:** $u_4 = 1000 \cdot 0.5^3 = 125$ and $S_4 = 1000 \cdot \frac{1 - 0.5^4}{1 - 0.5} = 1875$.

### 6.3 Which kind of sequence?

#### 6.3.1

**Decide which kind of sequence this is: $2, 6, 18, 54$.**
**Method:** differences, then ratios.
**Answer:** the differences $4, 12, 36$ are not equal; the ratios are all $3$: geometric with $q = 3$.

#### 6.3.2

**Decide which kind of sequence this is: $20, 17, 14, 11$.**
**Method:** differences, then ratios.
**Answer:** the differences are all $-3$: arithmetic with $r = -3$.

#### 6.3.3

**Decide which kind of sequence this is: $1, 4, 9, 16$.**
**Method:** differences, then ratios.
**Answer:** the differences $3, 5, 7$ are not equal and the ratios $4, 2.25, \dots$ are not equal: neither.

#### 6.3.4

**Write the first four terms of $u_n = 2n + 1$ and say which kind of sequence it is.**
**Method:** compute $u_1, \dots, u_4$, then apply the method of § 4.4.
**Answer:** not corrected in the material

### 6.4 Problems

#### 6.4.1

**A stack of logs has 12 logs in the bottom row, and each row has one log fewer than the row below it. There are 8 rows. How many logs are there in the stack?**
**Method:** the rows form an arithmetic sequence with $u_1 = 12$ and $r = -1$; add the 8 terms.
**Answer:** $u_8 = 12 - 7 = 5$ and $S_8 = \frac{8\,(12 + 5)}{2} = 68$ logs.

#### 6.4.2

**A culture has 500 bacteria at the start and the number doubles every hour. How many bacteria are there after 4 hours?**
**Method:** $u_1 = 500$ is the number at the start, so the number after 4 hours is $u_5$; geometric sequence with $q = 2$.
**Answer:** $u_5 = 500 \cdot 2^4 = 8000$ bacteria.

## 7. Points to check

None.
