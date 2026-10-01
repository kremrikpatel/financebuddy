import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy, RotateCcw, Sparkles, Volume2 } from "lucide-react";
import { speak } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type { CoachMessage } from "@/stores/coach";
import { BlockView } from "./Blocks";
import ActionCard from "./ActionCard";

/** Inline **bold** only; everything is a React text node (no HTML injection). */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong> : part,
  );
}

/** Minimal, safe markdown: paragraphs, "-"/"*" bullets, "1." numbered lists, **bold**. */
export function Markdown({ text }: { text: string }) {
  const out: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let para: string[] = [];
  const flushPara = () => {
    if (para.length) out.push(<p key={out.length}>{inline(para.join(" "))}</p>);
    para = [];
  };
  const flushList = () => {
    if (!list) return;
    const items = list.items.map((it, i) => <li key={i}>{inline(it)}</li>);
    out.push(list.ordered
      ? <ol key={out.length} className="list-decimal space-y-1 ps-5">{items}</ol>
      : <ul key={out.length} className="list-disc space-y-1 ps-5">{items}</ul>);
    list = null;
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const bullet = /^[-*•]\s+(.*)$/.exec(line);
    const numbered = /^\d+[.)]\s+(.*)$/.exec(line);
    if (bullet || numbered) {
      flushPara();
      const ordered = Boolean(numbered);
      if (list && list.ordered !== ordered) flushList();
      list ??= { ordered, items: [] };
      list.items.push((bullet ?? numbered)![1]);
    } else if (!line) {
      flushPara();
      flushList();
    } else {
      flushList();
      para.push(line.replace(/^#{1,6}\s+/, ""));
    }
  }
  flushPara();
  flushList();
  return <div className="space-y-2">{out}</div>;
}

export default function Message({ message, onRetry }: { message: CoachMessage; onRetry?: () => void }) {
  const { t, i18n } = useTranslation();
  const [copied, setCopied] = useState(false);

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-ee-md bg-brand px-3.5 py-2.5 text-sm text-brand-ink">
          {message.content}
        </div>
      </div>
    );
  }

  const streaming = message.state === "streaming";
  const failed = message.state === "error";
  const stopped = message.state === "stopped";

  async function copy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked: nothing to do */
    }
  }

  return (
    <div className="flex gap-2.5" data-testid="assistant-message" data-state={message.state}>
      <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-brand/10 text-brand" aria-hidden>
        <Sparkles size={14} />
      </span>
      <div className="min-w-0 flex-1 space-y-2">
        <div className={cn("text-sm leading-relaxed text-ink", failed && "text-neg")}>
          {message.content ? (
            <>
              <Markdown text={message.content} />
              {streaming && <span className="ms-0.5 inline-block h-4 w-1.5 translate-y-0.5 animate-caret bg-brand" aria-hidden />}
            </>
          ) : streaming ? (
            <p className="flex items-center gap-2 text-muted" role="status">
              <span className="flex gap-1" aria-hidden>
                {[0, 1, 2].map((i) => (
                  <span key={i} className="size-1.5 animate-pulse rounded-full bg-muted" style={{ animationDelay: `${i * 150}ms` }} />
                ))}
              </span>
              {message.tool ? t("coach.checkingData") : t("coach.thinking")}
            </p>
          ) : null}
          {failed && <p>{message.error || t("coach.errorReply")}</p>}
          {stopped && <p className="mt-1 text-xs text-muted">{t("coach.stopped")}</p>}
        </div>

        {message.blocks.map((b, i) => <BlockView key={i} block={b} />)}
        {message.actions.map((a) => <ActionCard key={a.id} action={a} messageId={message.id} />)}

        {!streaming && (
          <div className="flex flex-wrap items-center gap-1 text-xs text-muted">
            {message.content && (
              <>
                <button type="button" onClick={copy} className="inline-flex min-h-8 items-center gap-1 rounded-md px-1.5 hover:bg-sunken hover:text-ink">
                  {copied ? <Check size={13} aria-hidden /> : <Copy size={13} aria-hidden />}
                  {copied ? t("coach.copied") : t("coach.copy")}
                </button>
                <button type="button" onClick={() => speak(message.content, i18n.language)} className="inline-flex min-h-8 items-center gap-1 rounded-md px-1.5 hover:bg-sunken hover:text-ink">
                  <Volume2 size={13} aria-hidden /> {t("coach.speak")}
                </button>
              </>
            )}
            {(failed || stopped) && onRetry && (
              <button type="button" onClick={onRetry} className="inline-flex min-h-8 items-center gap-1 rounded-md px-1.5 text-brand hover:bg-brand/10">
                <RotateCcw size={13} aria-hidden /> {t("common.retry")}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
