import { memo, useEffect, useState } from "react";
import { ArrowRight, Check, X } from "lucide-react";
import { useCourseLanguage } from "@/lib/course-language";
import { cn } from "@/lib/utils";
import { m } from "@/paraglide/messages";
import { getLocale } from "@/paraglide/runtime";
import { Math } from "./math";
import { BlockView, Blocks, RichText } from "./board-blocks";
import type {
  BoardCard,
  CheckQuestionCard,
  ExerciseCard,
  ExplanationCard,
  RecapCard,
  TitleCard,
  WorkedExampleCard,
  Option,
  NextStep,
} from "@/lib/tutor/types";

/* ---------------------------------- shell --------------------------------- */

/** The label and, for the cards whose title is a fixed phrase, the title are the board's own
 *  words: they follow the interface language. A card's title and body are Célestin's, in the
 *  course's language, and say so to a screen reader. */
function BoardFrame({
  label,
  title,
  fixedTitle = false,
  hideTitleOnPhone = false,
  children,
}: {
  label: string;
  title: string;
  fixedTitle?: boolean;
  /** The title card says its eyebrow in its body: on a phone, not twice. */
  hideTitleOnPhone?: boolean;
  children: React.ReactNode;
}) {
  const language = useCourseLanguage();
  return (
    <article className="board-enter flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-board text-board-foreground shadow-sheet-lift">
      <header className="flex items-baseline gap-3 border-b border-border px-6 py-3 max-lg:px-4 max-lg:py-2">
        <span className="text-[11px] font-bold tracking-[0.14em] text-primary uppercase">
          {label}
        </span>
        <h2
          lang={fixedTitle ? undefined : language}
          className={cn(
            "truncate text-sm font-semibold text-muted-foreground",
            hideTitleOnPhone && "max-lg:hidden",
          )}
        >
          <RichText text={title} />
        </h2>
      </header>
      <div
        lang={language}
        className="min-h-0 flex-1 overflow-y-auto px-8 py-7 max-lg:px-4 max-lg:py-4"
      >
        {children}
      </div>
    </article>
  );
}

/* --------------------------------- boards --------------------------------- */

function TitleBoard({ card }: { card: TitleCard }) {
  return (
    <BoardFrame label={CARD_LABEL["title"]()} title={card.eyebrow} hideTitleOnPhone>
      <div className="flex h-full flex-col items-center justify-center text-center">
        <p className="text-xs font-bold tracking-[0.16em] text-muted-foreground uppercase">
          <RichText text={card.eyebrow} />
        </p>
        <h1 className="mt-3 text-3xl font-bold max-lg:text-2xl">
          <RichText text={card.title} />
        </h1>
        <p className="mt-4 max-w-md text-muted-foreground">
          <RichText text={card.objective} />
        </p>
      </div>
    </BoardFrame>
  );
}

function ExplanationBoard({ card }: { card: ExplanationCard }) {
  return (
    <BoardFrame label={CARD_LABEL["explanation"]()} title={card.title}>
      <Blocks blocks={card.blocks} className="mx-auto max-w-2xl" />
    </BoardFrame>
  );
}

/** Every step is visible. A faded example is Célestin's job: it shows the steps it
 *  wants, asks for the next one in the conversation, and redisplays the card. */
function WorkedExampleBoard({ card }: { card: WorkedExampleCard }) {
  return (
    <BoardFrame label={CARD_LABEL["worked_example"]()} title={card.title}>
      <div className="mx-auto max-w-2xl space-y-3">
        <p className="text-[15px] leading-relaxed">
          <RichText text={card.statement} />
        </p>
        {card.drawing && <BlockView block={card.drawing} />}
        {card.steps.map((step, i) => (
          <div key={i} className="math-display rounded-lg border border-border bg-card px-5 py-4">
            <Math block tex={step.tex} />
            {step.note && (
              <p className="mt-2 text-center text-xs text-muted-foreground">{step.note}</p>
            )}
          </div>
        ))}
      </div>
    </BoardFrame>
  );
}

/** Statement and optional hint. Answers go to Célestin in the conversation, typed or
 *  photographed, until a mechanical checker gives this card an answer widget. */
function ExerciseBoard({ card }: { card: ExerciseCard }) {
  return (
    <BoardFrame label={CARD_LABEL["exercise"]()} title={card.title}>
      <div className="mx-auto max-w-2xl space-y-6">
        <p className="text-[15px] leading-relaxed">
          <RichText text={card.statement} />
        </p>
        {card.drawing && <BlockView block={card.drawing} />}
        {card.hint && (
          <div className="rounded-lg border border-border bg-accent px-5 py-4">
            <p
              lang={getLocale()}
              className="text-[11px] font-bold tracking-[0.12em] text-accent-foreground uppercase"
            >
              {m.board_hint()}
            </p>
            <p className="mt-1.5 text-sm text-accent-foreground">
              <RichText text={card.hint} />
            </p>
          </div>
        )}
      </div>
    </BoardFrame>
  );
}

/** Fired when the learner picks an option (002 R8.3), so the tutor sees the answer. */
export type AnswerHandler = (option: Option, correct: boolean) => void;

function CheckQuestionBoard({
  card,
  onAnswer,
}: {
  card: CheckQuestionCard;
  onAnswer?: AnswerHandler | undefined;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  useEffect(() => setPicked(null), [card]);

  return (
    <BoardFrame label={CARD_LABEL["check_question"]()} title={m.board_check_title()} fixedTitle>
      <div className="mx-auto max-w-xl space-y-5">
        <p className="text-lg font-semibold">
          <RichText text={card.question} />
        </p>
        <div className="space-y-2">
          {card.options.map((option) => {
            const chosen = picked === option.id;
            const correct = option.id === card.correct_option_id;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => {
                  setPicked(option.id);
                  onAnswer?.(option, correct);
                }}
                className={cn(
                  "flex w-full items-center gap-3 rounded-lg border px-4 py-3 text-left text-[15px] transition-colors",
                  chosen && correct && "border-success bg-success/10",
                  chosen && !correct && "border-destructive bg-destructive/10",
                  !chosen && "border-border hover:bg-secondary",
                )}
              >
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full border border-border text-xs font-bold">
                  {option.id.toUpperCase()}
                </span>
                <RichText text={option.text} />
                {chosen &&
                  (correct ? (
                    <Check className="ml-auto size-4 shrink-0 text-success" />
                  ) : (
                    <X className="ml-auto size-4 shrink-0 text-destructive" />
                  ))}
              </button>
            );
          })}
        </div>
        {picked === card.correct_option_id && (
          <p className="panel-down text-sm text-muted-foreground">
            <RichText text={card.feedback} />
          </p>
        )}
      </div>
    </BoardFrame>
  );
}

function RecapBoard({ card }: { card: RecapCard }) {
  return (
    <BoardFrame label={CARD_LABEL["recap"]()} title={m.board_recap_title()} fixedTitle>
      <div className="mx-auto max-w-xl space-y-5">
        <div>
          <p
            lang={getLocale()}
            className="text-xs font-bold tracking-[0.12em] text-success uppercase"
          >
            {m.board_recap_acquired()}
          </p>
          <ul className="mt-1 space-y-1 text-[15px]">
            {card.acquired.map((item, i) => (
              <li key={i}>
                <RichText text={item} />
              </li>
            ))}
          </ul>
        </div>
        {card.watch.length > 0 && (
          <div>
            <p
              lang={getLocale()}
              className="text-xs font-bold tracking-[0.12em] text-warning uppercase"
            >
              {m.board_recap_watch()}
            </p>
            <ul className="mt-1 space-y-1 text-[15px]">
              {card.watch.map((item, i) => (
                <li key={i}>
                  <RichText text={item} />
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="rounded-lg border border-border bg-secondary/60 px-5 py-4 text-[15px]">
          <RichText text={card.next} />
        </div>
      </div>
    </BoardFrame>
  );
}

export function CardView({
  card,
  onAnswer,
}: {
  card: BoardCard;
  onAnswer?: AnswerHandler | undefined;
}) {
  switch (card.kind) {
    case "title":
      return <TitleBoard card={card} />;
    case "explanation":
      return <ExplanationBoard card={card} />;
    case "worked_example":
      return <WorkedExampleBoard card={card} />;
    case "exercise":
      return <ExerciseBoard card={card} />;
    case "check_question":
      return <CheckQuestionBoard card={card} onAnswer={onAnswer} />;
    case "recap":
      return <RecapBoard card={card} />;
    default:
      return null;
  }
}

/* ------------------------------ history strip ------------------------------ */

/** Status vocabulary of the strip. Only "done" is produced today; the others wait
 *  for the checker (spec 001 §4.6). */
export type BoardStatus = "open" | "done" | "correct" | "wrong" | "revealed";

function StatusGlyph({ status }: { status: BoardStatus }) {
  const map: Record<BoardStatus, { label: () => string; className: string }> = {
    open: { label: m.board_status_open, className: "bg-warning/20 text-warning-foreground" },
    done: { label: m.board_status_done, className: "bg-secondary text-muted-foreground" },
    correct: { label: m.board_status_correct, className: "bg-success/15 text-success" },
    wrong: { label: m.board_status_wrong, className: "bg-destructive/10 text-destructive" },
    revealed: { label: m.board_status_revealed, className: "bg-secondary text-muted-foreground" },
  };
  const s = map[status];
  return (
    <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-bold", s.className)}>
      {s.label()}
    </span>
  );
}

type StripItem = {
  key: string;
  label: string;
  title: string;
  status: BoardStatus;
  select: () => void;
};

function HistoryStrip({ items, current }: { items: StripItem[]; current: string }) {
  const language = useCourseLanguage();
  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-1">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          title={item.title}
          onClick={item.select}
          className={cn(
            "w-44 shrink-0 rounded-lg max-lg:w-36 border bg-card px-3 py-2 text-left transition-colors",
            item.key === current
              ? "border-primary shadow-sheet"
              : "border-border opacity-80 hover:opacity-100",
          )}
        >
          <span className="flex items-center justify-between gap-2">
            <span className="text-[10px] font-bold tracking-[0.12em] text-muted-foreground uppercase">
              {item.label}
            </span>
            <StatusGlyph status={item.status} />
          </span>
          <span lang={language} className="mt-1 block truncate text-xs font-semibold">
            {item.title}
          </span>
        </button>
      ))}
    </div>
  );
}

/** Message functions, not strings: the language is read when a label is shown. */
const CARD_LABEL: Record<BoardCard["kind"], () => string> = {
  title: m.board_card_title,
  explanation: m.board_card_explanation,
  worked_example: m.board_card_worked_example,
  exercise: m.board_card_exercise,
  check_question: m.board_card_check_question,
  recap: m.board_card_recap,
};

/** Strip label. Plain text only: the strip truncates, and cutting LaTeX mid-token
 *  would show its raw source. */
function cardTitle(card: BoardCard): string {
  if (card.kind === "recap") return m.board_recap_title();
  if (card.kind === "check_question") return stripMath(card.question);
  return stripMath(card.title);
}

function stripMath(text: string): string {
  return text.replace(/\$([^$]*)\$/g, "$1").trim();
}

/* -------------------------------- whiteboard ------------------------------- */

export type WhiteboardProps = {
  card: BoardCard | null;
  cards: BoardCard[];
  onSelect: (index: number) => void;
  onAnswer?: AnswerHandler | undefined;
  /** What the page-turn button offers; null greys it. Without `onNextStep` there
   *  is no button at all — a discussion has no page to turn (007 R2.2). */
  nextStep?: NextStep;
  onNextStep?: (() => void) | undefined;
};

/** She turns the page, not the tutor: greyed until Célestin proposes the next step,
 *  or until a section closes and the next one is waiting. */
function NextStepButton({ next, onClick }: { next: NextStep; onClick: () => void }) {
  const ready = next !== null;
  const label = next?.kind === "section" ? m.board_next_section() : m.board_next_step();
  return (
    <div className={cn("flex items-center justify-end gap-3", !ready && "max-lg:hidden")}>
      {!ready && <span className="text-xs text-muted-foreground">{m.board_next_wait()}</span>}
      <button
        type="button"
        disabled={!ready}
        onClick={onClick}
        aria-label={label}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md px-3.5 py-2 text-sm font-semibold transition-colors max-lg:min-h-11 max-lg:w-full max-lg:justify-center",
          ready
            ? "bg-success text-success-foreground shadow-sheet hover:opacity-90"
            : "cursor-not-allowed border border-border bg-card text-muted-foreground opacity-60",
        )}
      >
        {label} <ArrowRight className="size-4" />
      </button>
    </div>
  );
}

export const Whiteboard = memo(function Whiteboard({
  card,
  cards,
  onSelect,
  onAnswer,
  nextStep = null,
  onNextStep,
}: WhiteboardProps) {
  // The board starts empty and only ever shows what Célestin wrote this session.
  const items: StripItem[] = cards.map((c, i) => ({
    key: `tutor-${i}`,
    label: CARD_LABEL[c.kind](),
    title: cardTitle(c),
    status: "done" as BoardStatus,
    select: () => onSelect(i),
  }));

  const currentKey = card ? `tutor-${cards.indexOf(card)}` : "";

  return (
    <section className="flex h-full min-h-0 flex-col gap-3 bg-paper p-5 max-lg:gap-2 max-lg:p-2">
      <div className="flex items-center justify-between max-lg:hidden">
        <p className="text-[11px] font-bold tracking-[0.14em] text-muted-foreground uppercase">
          {m.board_title()}
        </p>
      </div>
      {items.length > 0 && (
        // A phone shows the strip once there is a second card to go back to.
        <div className={cn(items.length < 2 && "max-lg:hidden")}>
          <HistoryStrip items={items} current={currentKey} />
        </div>
      )}
      <div className="min-h-0 flex-1">
        {card ? (
          <div key={currentKey} className="h-full">
            <CardView card={card} onAnswer={onAnswer} />
          </div>
        ) : (
          <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted-foreground">
            {m.board_empty()}
          </div>
        )}
      </div>
      {card && onNextStep && <NextStepButton next={nextStep} onClick={onNextStep} />}
    </section>
  );
});
