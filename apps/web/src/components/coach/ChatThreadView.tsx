import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { ArrowUp, Mic, Sparkles, Square } from "lucide-react";
import { IconButton, Notice } from "@/components/ui";
import { useSpeechRecognition } from "@/lib/hooks";
import { promptKeys, tabLabelKey } from "@/lib/coachTabs";
import { cn } from "@/lib/utils";
import { useCoach } from "@/stores/coach";
import Message from "./Message";

export interface ChatThreadHandle {
  focus: () => void;
  sendText: (text: string) => void;
}

interface Props {
  threadKey: string | null;
  tab: string;
  path: string;
  className?: string;
}

const EMPTY: never[] = [];
const AUTO_GROW = { fieldSizing: "content" } as CSSProperties;

/** Conversation surface shared by the tab dock, the Coach page and the hub. */
const ChatThreadView = forwardRef<ChatThreadHandle, Props>(function ChatThreadView({ threadKey, tab, path, className }, ref) {
  const { t, i18n } = useTranslation();
  const messages = useCoach((s) => (threadKey ? s.messages[threadKey] ?? EMPTY : EMPTY));
  const inflight = useCoach((s) => s.inflight);
  const degraded = useCoach((s) => s.degraded);
  const summary = useCoach((s) => s.summaries[tab] ?? null);
  const send = useCoach((s) => s.send);
  const stop = useCoach((s) => s.stop);
  const retry = useCoach((s) => s.retry);

  const [text, setText] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const speech = useSpeechRecognition(i18n.language || "en-US");

  const activeRequest = Object.entries(inflight).find(([, f]) => f.key === threadKey)?.[0];
  const lastContent = messages.at(-1)?.content;

  useEffect(() => {
    if (speech.transcript) setText(speech.transcript);
  }, [speech.transcript]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, lastContent]);

  function submit(value = text) {
    const clean = value.trim();
    if (!clean || activeRequest) return;
    void send({ threadKey, text: clean, tab, path, summary });
    setText("");
    speech.reset();
  }

  useImperativeHandle(ref, () => ({
    focus: () => inputRef.current?.focus(),
    sendText: (value: string) => submit(value),
  }));

  const prompts = promptKeys(tab).filter((k) => i18n.exists(k));

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4" aria-live="polite" aria-relevant="additions text">
        {degraded && (
          <Notice tone="warn">
            <p className="font-medium">{t("coach.degradedTitle")}</p>
            <p className="text-muted">{t("coach.degradedBody")}</p>
          </Notice>
        )}

        {messages.length === 0 ? (
          <div className="flex flex-col items-start gap-3 pt-2">
            <div className="flex items-center gap-2 text-ink">
              <Sparkles size={16} className="text-brand" aria-hidden />
              <p className="text-sm font-semibold">{t("coach.emptyTitle", { tab: t(tabLabelKey(tab)) })}</p>
            </div>
            <p className="text-sm text-muted">{t("coach.emptyBody")}</p>
            <ul className="flex w-full flex-col gap-2" aria-label={t("coach.pageSuggestions")}>
              {prompts.map((k) => (
                <li key={k}>
                  <button
                    type="button"
                    onClick={() => submit(t(k))}
                    className="w-full rounded-lg border border-line bg-raised px-3 py-2.5 text-start text-sm text-ink transition-colors hover:border-brand/50 hover:bg-brand/5"
                  >
                    {t(k)}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          messages.map((m) => (
            <Message key={m.key} message={m} onRetry={threadKey ? () => retry(threadKey, m.key) : undefined} />
          ))
        )}
        <div ref={endRef} />
      </div>

      <form
        className="border-t border-line px-3 pb-2 pt-3"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        {speech.listening && (
          <p className="mb-2 flex items-center gap-2 text-sm text-neg" role="status">
            <span className="size-2 animate-pulse rounded-full bg-neg" aria-hidden />
            {t("coach.listening")}
          </p>
        )}
        <div className="flex items-end gap-2 rounded-xl border border-field/70 bg-raised p-1.5 focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/25">
          {speech.supported && (
            <IconButton
              label={t("coach.voice")}
              icon={<Mic size={17} />}
              variant={speech.listening ? "danger" : "ghost"}
              onClick={speech.listening ? speech.stop : speech.start}
              aria-pressed={speech.listening}
              className="size-9 min-h-9"
            />
          )}
          <textarea
            ref={inputRef}
            value={text}
            rows={1}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder={t("coach.placeholderTab", { tab: t(tabLabelKey(tab)) })}
            aria-label={t("coach.placeholder")}
            className="max-h-32 min-h-9 flex-1 resize-none bg-transparent px-1.5 py-2 text-base text-ink outline-none placeholder:text-muted focus-visible:outline-none sm:text-sm"
            style={AUTO_GROW}
          />
          {activeRequest ? (
            <IconButton
              label={t("coach.stop")}
              icon={<Square size={14} fill="currentColor" />}
              variant="secondary"
              onClick={() => stop(activeRequest)}
              className="size-9 min-h-9"
            />
          ) : (
            <IconButton
              type="submit"
              label={t("coach.send")}
              icon={<ArrowUp size={17} />}
              variant="primary"
              disabled={!text.trim()}
              className="size-9 min-h-9"
            />
          )}
        </div>
        <p className="mt-2 text-center text-xs text-muted">{t("coach.disclaimer")}</p>
      </form>
    </div>
  );
});

export default ChatThreadView;
