"""The flowchart rules `display_board` applies.

They run in the tool, not on the card model: they could change (a limit, a fold)
and a stored card must keep replaying. Each refusal is a rule code for the logs
and a French message naming the field, handed back to the model to fix.

The structural rules (sizes, kinds, at most two exits) live on the card model,
`app/domain/flowchart.py`. This module must not import `tools/board.py`, which
imports it.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from app.domain.board import BoardCard, ExerciseCard
from app.domain.flowchart import FlowchartBlock, FlowNode
from app.domain.language import DEFAULT_COURSE_LANGUAGE, CourseLanguage, by_language
from app.services.tools.charts import Refusal
from app.services.tools.context import TurnContext
from app.services.tools.text import MATH, math_tex, spaced

# One organigramme is already a board's worth; a second goes on the next card.
MAX_FLOWCHARTS_PER_CARD = 1
# What one row holds at phone width: three boxes, a question counting for two
# (a diamond is about twice a step's width). Passages weigh nothing.
ROW_BUDGET = 3
# A question fits a diamond at phone width. Raw characters, TeX source included.
MAX_QUESTION = 40
# A hidden text shorter than this (letters and digits of its words, plus its
# formulas' TeX) is not looked for: « Fin », « SA » would match everywhere.
MIN_SECRET = 5
# A hidden formula's TeX, whitespace removed, shorter than this is not looked for
# inside other formulas: `$q$`, `$u_n$` are the chapter's everyday notation. Only a
# hidden text that is a formula (its words under MIN_SECRET) is looked for so.
MIN_FORMULA = 4


def layers(exits: Mapping[str, Sequence[str]]) -> tuple[dict[str, int], set[tuple[str, str]]]:
    """Each node's row and the loops, as the board lays them out (the frontend's
    `flowchart/layout.ts` `layers`; `tests/fixtures/flowchart_layers.json` holds the
    two together).

    A depth-first walk from the first node, then from any node not yet reached, in
    order, marks the exits that go back up the walk as loops; every other exit
    goes down, and a node's row is its longest path from a root. `exits` keeps the
    nodes' order (a dict does)."""
    state: dict[str, int] = {}
    loops: set[tuple[str, str]] = set()
    finished: list[str] = []

    def walk(u: str) -> None:
        state[u] = 1
        for v in exits[u]:
            if v not in exits or v == u:
                continue
            if state.get(v) == 1:
                loops.add((u, v))
            elif v not in state:
                walk(v)
        state[u] = 2
        finished.append(u)

    for u in exits:
        if u not in state:
            walk(u)
    row = dict.fromkeys(exits, 0)
    # Reverse finishing order is a topological order of the exits that are not loops.
    for u in reversed(finished):
        for v in exits[u]:
            if v in exits and v != u and (u, v) not in loops:
                row[v] = max(row[v], row[u] + 1)
    return row, loops


def _exits(block: FlowchartBlock) -> dict[str, list[str]]:
    return {node.id: [e.to for e in node.next] for node in block.nodes}


def reading_order(block: FlowchartBlock) -> list[int]:
    """Node indices in the order a reader follows them, as the board's screen-reader
    list numbers its steps (`flowchart/graph.ts` `readingOrder`): depth-first from
    the first node, each node's exits in order, then any node not reached."""
    index = {node.id: i for i, node in reversed(list(enumerate(block.nodes)))}
    seen: set[int] = set()
    order: list[int] = []

    def walk(u: int) -> None:
        seen.add(u)
        order.append(u)
        for e in block.nodes[u].next:
            if (v := index.get(e.to)) is not None and v not in seen:
                walk(v)

    for u in range(len(block.nodes)):
        if u not in seen:
            walk(u)
    return order


def _name(nodes: Sequence[FlowNode], i: int) -> str:
    return f"nodes[{i}] (« {nodes[i].id} »)"


def _listing(names: Sequence[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} et {names[-1]}"


def _ids(block: FlowchartBlock, where: str) -> Refusal | None:
    first: dict[str, int] = {}
    for j, node in enumerate(block.nodes):
        if node.id in first:
            return (
                "ids",
                f"{where} : l'identifiant « {node.id} » sert à nodes[{first[node.id]}] et à nodes[{j}] ; "
                "chaque nœud a le sien.",
            )
        first[node.id] = j
    seen: set[str] = set()
    for name in block.hidden:
        if name in seen:
            return ("ids", f"{where} : hidden cite « {name} » deux fois.")
        seen.add(name)
    return None


def _blank(block: FlowchartBlock, where: str) -> Refusal | None:
    """A text of spaces only passes the schema's min_length, and draws an empty box."""
    for i, node in enumerate(block.nodes):
        if not node.text.strip():
            return ("blank", f"{where} : nodes[{i}].text est vide ; chaque case dit son étape.")
        for k, e in enumerate(node.next):
            if e.label is not None and not e.label.strip():
                fix = "écris sa réponse (« oui », « non »…)" if node.kind == "decision" else "écris-la, ou retire-la"
                return ("blank", f"{where} : nodes[{i}].next[{k}].label est vide ; {fix}.")
    if block.caption is not None and not block.caption.strip():
        return ("blank", f"{where} : caption est vide ; écris-la, ou retire-la.")
    return None


# A box whose whole text marks a hole instead of saying its step. The board writes
# « ? » itself for a hidden node, from its real text.
# Marks only: « ? », « … », « ___ », « ( ? ) », « $?$ ».
_HOLE_MARKS = re.compile(r"[\s?¿!？！.…⋯⋮_\-–—()\[\]{}<>«»\"'‘’“”*$□■▢◻]+")
# Or a hole phrase from a closed list, read on the text's words without case, accents
# or punctuation (`_plain_words`): « À compléter… », « (à remplir) », « ??? à
# trouver », « Étape manquante », « Case 3 : ? », `$\ldots$`. The whole text only:
# « Compléter le tableau », « Case vide ? » are steps and questions.
_HOLE_HEAD = r"(?:case|etape|noeud|texte|bloc|question|reponse)(?: no?)?(?: \d+)?"
_HOLE_GAP = (
    r"(?:(?:a toi de |a )(?:completer|remplir|trouver|retrouver|deviner|determiner|preciser|ecrire|placer)"
    r"(?: par (?:l )?eleve| par toi)?"
    r"|manquante?(?: ici)?|cachee?|inconnue?|mystere)"
)
_HOLE_WORDS = re.compile(rf"{_HOLE_HEAD}(?: {_HOLE_GAP})?|{_HOLE_GAP}|[lc]?dots")
# The same list for an English course (spec 011 §4.6), read on the same plain words:
# « To complete… », « (fill in) », « ??? to find », « Missing step », « Box 3 : ? », « TBD ».
_HOLE_HEAD_EN = r"(?:box|step|node|text|block|question|answer)(?: no)?(?: \d+)?"
_HOLE_GAP_EN = (
    r"(?:(?:to |for you to )(?:complete|fill in|fill|find|guess|determine|specify|write|place)"
    r"(?: by the student| by you)?"
    r"|fill in"
    r"|to be (?:completed|filled in|filled|found|determined|specified)"
    r"|missing(?: here)?|hidden|unknown|mystery|tbd|tbc)"
)
# English puts the adjective first (« Missing step »), French after (« Étape manquante »).
_HOLE_WORDS_EN = re.compile(
    rf"{_HOLE_HEAD_EN}(?: {_HOLE_GAP_EN})?|{_HOLE_GAP_EN}(?: {_HOLE_HEAD_EN})?|[lc]?dots"
)
# The same list for a Dutch course (spec 017 §4.6), read on the same plain words (no case, accents or
# punctuation): « In te vullen », « Vul aan », « ??? te vinden », « Ontbrekende stap », « Vak 3 : ? », « TBD ».
_HOLE_HEAD_NL = r"(?:vak|stap|knoop|tekst|blok|vraag|antwoord|waarde)(?: nr)?(?: \d+)?"
_HOLE_GAP_NL = (
    r"(?:(?:nog )?(?:in|aan) te vullen"
    r"|(?:hier )?(?:in|aan)vullen"
    r"|(?:nog )?te (?:vinden|bepalen|raden|schrijven|plaatsen|preciseren)"
    r"|vul (?:(?:het|de) (?:antwoord|vak|stap|gat) )?(?:hier )?(?:in|aan)"
    r"|ontbrekende?(?: hier)?|ontbreekt(?: hier)?|leeg|lege|blanco|verborgen|onbekende?|mysterie|tbd)"
    r"(?: door (?:de )?leerling| door jou)?"
)
# Dutch puts the adjective first (« Ontbrekende stap »), as English does.
_HOLE_WORDS_NL = re.compile(
    rf"{_HOLE_HEAD_NL}(?: {_HOLE_GAP_NL})?|{_HOLE_GAP_NL}(?: {_HOLE_HEAD_NL})?|[lc]?dots"
)
HOLE_WORDS = by_language(fr=_HOLE_WORDS, en=_HOLE_WORDS_EN, nl=_HOLE_WORDS_NL)


def _plain_words(text: str) -> str:
    """The text's letters and digits, lower-cased, without accents, one space between
    words: « (À compléter…) » reads « a completer », « Nœud 2 » « noeud 2 »."""
    folded = unicodedata.normalize("NFKD", text).casefold().replace("œ", "oe").replace("æ", "ae")
    return " ".join(_WORD.findall("".join(c for c in folded if not unicodedata.combining(c))))


def _is_hole(text: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE) -> bool:
    """Whether a box's whole text only marks a hole (`_HOLE_MARKS`, `HOLE_WORDS`)."""
    return bool(_HOLE_MARKS.fullmatch(text) or HOLE_WORDS[language].fullmatch(_plain_words(text)))


def _placeholder(
    block: FlowchartBlock, where: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> Refusal | None:
    """A « ? » or « À compléter » typed as a box's text: a hand-made hole the tool
    cannot check for leaks, and on a build exercise a drawing that shows the method's
    shape anyway."""
    for i, node in enumerate(block.nodes):
        if _is_hole(node.text, language):
            return (
                "placeholder",
                f"{where} : nodes[{i}].text, « {node.text.strip()} », marque un trou au lieu de dire "
                "l'étape. Donne le vrai texte de la case : pour la cacher, mets son id dans hidden (sur "
                "le drawing d'un exercise) et le tableau affiche « ? ». Si ton élève doit construire "
                "l'organigramme, ne l'affiche pas.",
            )
    return None


def _unknown_ids(block: FlowchartBlock, where: str) -> Refusal | None:
    known = {node.id for node in block.nodes}
    fields = [
        *((f"nodes[{i}].next[{k}].to", e.to) for i, node in enumerate(block.nodes) for k, e in enumerate(node.next)),
        *((f"path[{k}]", name) for k, name in enumerate(block.path)),
        *((f"hidden[{k}]", name) for k, name in enumerate(block.hidden)),
    ]
    for field, name in fields:
        if name not in known:
            return (
                "unknown_id",
                f"{where} : {field} renvoie à « {name} », qui n'est l'identifiant d'aucun nœud.",
            )
    return None


def _self_loops(block: FlowchartBlock, where: str) -> Refusal | None:
    for i, node in enumerate(block.nodes):
        if any(e.to == node.id for e in node.next):
            return (
                "self_loop",
                f"{where} : {_name(block.nodes, i)} sort vers lui-même ; "
                "une boucle revient à une étape précédente.",
            )
    return None


def _start(block: FlowchartBlock, where: str) -> Refusal | None:
    nodes = block.nodes
    if any(node.kind == "start" for node in nodes[1:]):
        return (
            "start",
            f"{where} : un nœud start vient en premier (nodes[0]), et il n'y en a qu'un.",
        )
    if nodes[0].kind == "start":
        for i, node in enumerate(nodes):
            if any(e.to == nodes[0].id for e in node.next):
                return (
                    "start",
                    f"{where} : {_name(nodes, i)} ramène au nœud start ; "
                    "une boucle revient à une étape, pas au début.",
                )
    return None


def _end(block: FlowchartBlock, where: str) -> Refusal | None:
    for i, node in enumerate(block.nodes):
        if node.kind == "end" and node.next:
            return ("end", f"{where} : {_name(block.nodes, i)} est un nœud end, il n'a pas de sortie.")
    return None


def _exit_count(block: FlowchartBlock, where: str) -> Refusal | None:
    for i, node in enumerate(block.nodes):
        if node.kind != "decision" and len(node.next) > 1:
            return (
                "exits",
                f"{where} : {_name(block.nodes, i)} a {len(node.next)} sorties ; "
                "seule une question (decision) en a plusieurs.",
            )
    return None


def _decisions(block: FlowchartBlock, where: str) -> Refusal | None:
    nodes = block.nodes
    for i, node in enumerate(nodes):
        if node.kind != "decision":
            continue
        if not node.next:
            return (
                "decision",
                f"{where} : la question {_name(nodes, i)} n'a pas de sortie ; "
                "chaque réponse que le cours donne a sa flèche, et une réponse que le cours ne "
                "traite pas n'en a pas : pas de case que le cours ne donne pas.",
            )
        for k, e in enumerate(node.next):
            if e.label is None or not e.label.strip():
                return (
                    "decision",
                    f"{where} : nodes[{i}].next[{k}] n'a pas d'étiquette ; chaque sortie d'une "
                    "question dit sa réponse (« oui », « non »…). Une question peut n'avoir "
                    "qu'une sortie : une réponse que le cours ne traite pas n'a pas de flèche.",
                )
        if len(node.next) == 2:
            first, second = node.next
            if _label_key(first.label or "") == _label_key(second.label or ""):
                return (
                    "decision",
                    f"{where} : les deux sorties de {_name(nodes, i)} portent l'étiquette « {second.label} ».",
                )
            if first.to == second.to:
                return (
                    "decision",
                    f"{where} : les deux sorties de {_name(nodes, i)} mènent à « {first.to} » ; "
                    "chaque réponse a son chemin.",
                )
    return None


def _label_key(label: str) -> str:
    """How an answer reads: its words lower-cased with their spaces folded, its
    formulas without spaces (`$\\Delta>0$` and `$\\Delta > 0$` are one answer;
    `$\\Delta$` and `$\\delta$` are two)."""
    parts: list[str] = []
    pos = 0
    for m in MATH.finditer(label):
        parts += [spaced(label[pos : m.start()]), f"${_tex(m)}$"]
        pos = m.end()
    parts.append(spaced(label[pos:]))
    return " ".join(part for part in parts if part)


def _question_length(block: FlowchartBlock, where: str) -> Refusal | None:
    for i, node in enumerate(block.nodes):
        if node.kind == "decision" and len(node.text) > MAX_QUESTION:
            return (
                "decision_text",
                f"{where} : la question {_name(block.nodes, i)} dépasse {MAX_QUESTION} caractères ; "
                "garde-la courte et fais le calcul dans une étape avant elle.",
            )
    return None


def _reachable(block: FlowchartBlock, where: str) -> Refusal | None:
    exits = _exits(block)
    seen: set[str] = set()
    todo = [block.nodes[0].id]
    while todo:
        u = todo.pop()
        if u not in seen:
            seen.add(u)
            todo.extend(exits[u])
    for i, node in enumerate(block.nodes):
        if node.id not in seen:
            return (
                "unreachable",
                f"{where} : aucune flèche ne mène de nodes[0] à {_name(block.nodes, i)} ; "
                "relie-le, ou retire-le.",
            )
    return None


def _dead_ends(block: FlowchartBlock, where: str) -> Refusal | None:
    if not any(node.kind == "end" for node in block.nodes):
        return None
    for i, node in enumerate(block.nodes):
        if node.kind != "end" and not node.next:
            return (
                "dead_end",
                f"{where} : {_name(block.nodes, i)} n'a pas de sortie ; dans un organigramme "
                "qui a une fin, seuls les nœuds end terminent.",
            )
    return None


def _width(block: FlowchartBlock, where: str) -> Refusal | None:
    row, _ = layers(_exits(block))
    weight: dict[int, int] = {}
    for node in block.nodes:
        weight[row[node.id]] = weight.get(row[node.id], 0) + (2 if node.kind == "decision" else 1)
    for r in sorted(weight):
        if weight[r] > ROW_BUDGET:
            names = [_name(block.nodes, i) for i, node in enumerate(block.nodes) if row[node.id] == r]
            return (
                "wide",
                f"{where} : {_listing(names)} se retrouvent côte à côte ; le tableau en aligne au plus "
                "trois, une question comptant pour deux. Regroupe des étapes, ou montre une partie "
                "de la méthode à la fois.",
            )
    return None


def _path(block: FlowchartBlock, where: str) -> Refusal | None:
    exits = _exits(block)
    for a, b in zip(block.path, block.path[1:]):
        if b not in exits[a]:
            return (
                "path",
                f"{where} : path passe de « {a} » à « {b} » sans flèche de l'un à l'autre ; "
                "path suit les flèches, dans l'ordre.",
            )
    return None


# The graph rules, in the order they are reported. The shape comes first: every
# later rule reads ids and exits.
_GRAPH_RULES: tuple[Callable[[FlowchartBlock, str], Refusal | None], ...] = (
    _ids,
    _blank,
    _placeholder,
    _unknown_ids,
    _self_loops,
    _start,
    _end,
    _exit_count,
    _decisions,
    _question_length,
    _reachable,
    _dead_ends,
    _width,
    _path,
)


def flowchart_refusal(
    block: FlowchartBlock, at: str, language: CourseLanguage = DEFAULT_COURSE_LANGUAGE
) -> Refusal | None:
    """The first graph rule the flowchart breaks, as (rule, message), or None. Only the
    placeholder rule reads words, so only it is given the course's language."""
    where = f"L'organigramme {at}"
    for rule in _GRAPH_RULES:
        if refusal := (rule(block, where, language) if rule is _placeholder else rule(block, where)):
            return refusal
    return None


_WORD = re.compile(r"[^\W_]+")


def _tex(m: re.Match[str]) -> str:
    return "".join(math_tex(m).split())


def _words(prose: str) -> list[tuple[str, str]]:
    return [("w", w) for w in _WORD.findall(unicodedata.normalize("NFKC", prose).casefold())]


def _tokens(text: str) -> list[tuple[str, str]]:
    """Words (NFKC, case-folded, letters and digits) and each formula as one token."""
    out: list[tuple[str, str]] = []
    pos = 0
    for m in MATH.finditer(text):
        out += _words(text[pos : m.start()])
        out.append(("m", _tex(m)))
        pos = m.end()
    return out + _words(text[pos:])


def _inside(f: str, g: str) -> bool:
    """Whether formula `f` is in formula `g` as whole symbols: `i\\leftarrowi+1`
    is in `S\\leftarrowS+u_i;i\\leftarrowi+1`, not in `i\\leftarrowi+10`."""
    start = g.find(f)
    while start >= 0:
        end = start + len(f)
        before = start == 0 or not (g[start - 1].isalnum() and f[0].isalnum())
        after = end == len(g) or not (g[end].isalnum() and f[-1].isalnum())
        if before and after:
            return True
        start = g.find(f, start + 1)
    return False


def leaks(secret: str, text: str) -> bool:
    """Whether `text` gives `secret` away: its whole run of words and formulas, or,
    when the secret is a formula, that formula inside a formula of `text`. Whole
    words, so « raison » is not found in « raisonnement ». Paraphrase is not
    caught. `scripts/probe.py` folds Célestin's spoken text with it too."""
    needle = _tokens(secret)
    if sum(len(v) for _, v in needle) >= MIN_SECRET:
        hay, n = _tokens(text), len(needle)
        if any(hay[i : i + n] == needle for i in range(len(hay) - n + 1)):
            return True
    # A secret with words (« Calculer $\Delta$ », « $u_{n+1} - u_n$ constante ? »)
    # is not given away by its formula alone: that is the method's notation, which
    # the other boxes use. A secret that is a formula (`$i \leftarrow i + 1$`,
    # « Si $i \leqslant n$ ») is, wherever the formula shows, inside a longer one too.
    if sum(len(v) for kind, v in needle if kind == "w") >= MIN_SECRET:
        return False
    formulas = [_tex(m) for m in MATH.finditer(text)]
    return any(
        len(f) >= MIN_FORMULA and any(_inside(f, g) for g in formulas) for kind, f in needle if kind == "m"
    )


# Where a lone hidden node's text would be its answer, not a label to place.
_STATEMENT_FIELDS = ("title", "statement", "hint")


def _visible(block: FlowchartBlock, at: str, card: ExerciseCard, hidden: set[str]) -> Iterator[tuple[str, str]]:
    """The texts in scope of the leak rule, with the field a message names."""
    for j, node in enumerate(block.nodes):
        if node.id not in hidden:
            yield f"{at}.nodes[{j}].text", node.text
    for j, node in enumerate(block.nodes):
        for k, e in enumerate(node.next):
            if e.label is not None:
                yield f"{at}.nodes[{j}].next[{k}].label", e.label
    if block.caption is not None:
        yield f"{at}.caption", block.caption
    # Two hidden nodes or more: the statement may list their texts as labels to place.
    if len(hidden) == 1:
        for field in _STATEMENT_FIELDS:
            if (value := getattr(card, field)) is not None:
                yield field, value


def _hidden_leak(block: FlowchartBlock, at: str, card: ExerciseCard) -> Refusal | None:
    hidden = set(block.hidden)
    for i, node in enumerate(block.nodes):
        if node.id not in hidden:
            continue
        for field, text in _visible(block, at, card, hidden):
            if leaks(node.text, text):
                message = (
                    f"L'organigramme {at} : le texte caché de {_name(block.nodes, i)} se lit dans "
                    f"{field} ; retire-le de là tant que ton élève doit le retrouver."
                )
                if field in _STATEMENT_FIELDS:
                    message += (
                        " Avec une seule case cachée, c'est la réponse ; pour donner des "
                        "étiquettes à placer, cache au moins deux cases."
                    )
                return ("hidden_leak", message)
    return None


def _placement(block: FlowchartBlock, at: str, exercise: bool) -> Refusal | None:
    """`path` shows the way, so never on an open exercise; `hidden` asks for the
    boxes, so only there."""
    if exercise and block.path:
        return (
            "exercise_path",
            f"L'organigramme {at} accompagne un exercice ouvert : pas de path, sinon il montre le "
            "chemin à suivre. Le chemin se montre après la tentative, dans un worked_example ou "
            "une explanation.",
        )
    if not exercise and block.hidden:
        return (
            "hidden_place",
            f"L'organigramme {at} : hidden ne sert que sur le drawing d'un exercise, pour un "
            "organigramme à compléter. Ici, montre toutes les cases.",
        )
    return None


def flowcharts_refusal(
    items: Sequence[tuple[str, FlowchartBlock]], card: BoardCard, ctx: TurnContext
) -> Refusal | None:
    """The first rule the card's flowcharts break, as (rule, message), or None: the
    per-card limit, then for each flowchart in card order where `path` and `hidden`
    may go, the graph rules, and whether a hidden text shows elsewhere on the card.

    `ctx.pack` is not read: a flowchart keeps to the pack's method by prompt, and
    the probe measures it (a string check would refuse the course's own short
    imperatives)."""
    if len(items) > MAX_FLOWCHARTS_PER_CARD:
        return (
            "per_card",
            "Une carte porte au plus un organigramme ; mets l'autre sur une carte suivante.",
        )
    exercise = card if isinstance(card, ExerciseCard) else None
    for at, block in items:
        if refusal := _placement(block, at, exercise is not None) or flowchart_refusal(block, at, ctx.language):
            return refusal
        if exercise is not None and block.hidden and (refusal := _hidden_leak(block, at, exercise)):
            return refusal
    return None


def flowcharts_summary(items: Sequence[tuple[str, FlowchartBlock]]) -> dict[str, Any]:
    """What `flowchart_displayed` logs besides the ids: counts and a flag, never a
    text, a label or a node id."""
    return {
        "nodes": [len(block.nodes) for _, block in items],
        "hidden": sum(len(block.hidden) for _, block in items),
        "path": any(block.path for _, block in items),
    }
