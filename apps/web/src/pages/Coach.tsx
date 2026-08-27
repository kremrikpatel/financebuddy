import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Send, Mic, Volume2, Bot, User } from "lucide-react";
import { motion } from "framer-motion";
import { http } from "@/lib/api";
import { Button } from "@/components/ui";
import { useSpeechRecognition, speak } from "@/lib/hooks";
import { cn } from "@/lib/utils";

interface Msg {
  role: "user" | "assistant";
  content: string;
  provider?: string | null;
}

export default function CoachPage() {
  const { t, i18n } = useTranslation();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [mode, setMode] = useState("auto");
  const bottomRef = useRef<HTMLDivElement>(null);
  const speech = useSpeechRecognition(i18n.language);

  useEffect(() => {
    if (speech.transcript) setInput(speech.transcript);
  }, [speech.transcript]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = useMutation({
    mutationFn: async (text: string) => {
      const { data } = await http.post("/chat/send", {
        thread_id: threadId,
        message: text,
        agent_mode: mode,
      });
      return data;
    },
    onSuccess: (data) => {
      setThreadId(data.thread_id);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: data.reply.content, provider: data.reply.provider },
      ]);
    },
    onError: () => {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: "⚠️ The AI engine is unavailable right now. Configure an LLM provider key (OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY / OLLAMA_BASE_URL) and try again." },
      ]);
    },
  });

  function submit() {
    const text = input.trim();
    if (!text || send.isPending) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    speech.reset();
    send.mutate(text);
  }

  return (
    <div className="flex h-[calc(100vh-8.5rem)] flex-col">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">{t("coach.title")}</h1>
        <div className="flex gap-1 rounded-xl bg-raised p-1">
          {["auto", "coach", "budget", "fraud", "goals"].map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-xs font-medium capitalize transition",
                mode === m ? "bg-brand text-white shadow" : "text-muted hover:text-ink",
              )}
            >
              {t(`coach.modes.${m}`)}
            </button>
          ))}
        </div>
      </div>

      <div className="card flex-1 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="grid h-full place-items-center text-center">
            <div className="max-w-sm space-y-3">
              <Bot size={40} className="mx-auto text-brand" />
              <p className="font-medium">Your money, explained.</p>
              <div className="flex flex-wrap justify-center gap-2 text-xs">
                {[
                  "How is my cash flow trending?",
                  "Any suspicious charges lately?",
                  "Where am I overspending?",
                  "Plan my debt payoff",
                  "How close am I to my goals?",
                ].map((s) => (
                  <button key={s} onClick={() => setInput(s)} className="rounded-full border border-line px-3 py-1.5 text-muted transition hover:border-brand/50 hover:text-brand">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
        <div className="space-y-4">
          {messages.map((m, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className={cn("flex gap-3", m.role === "user" && "justify-end")}
            >
              {m.role === "assistant" && (
                <span className="mt-1 grid size-8 shrink-0 place-items-center rounded-xl bg-brand/10 text-brand"><Bot size={16} /></span>
              )}
              <div
                className={cn(
                  "max-w-[75%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-relaxed",
                  m.role === "user" ? "bg-brand text-white rounded-br-md" : "bg-surface border border-line rounded-tl-md",
                )}
              >
                {m.content}
                {m.role === "assistant" && (
                  <div className="mt-2 flex items-center gap-2 text-[10px] text-muted">
                    {m.provider && <span>via {m.provider}</span>}
                    <button onClick={() => speak(m.content, i18n.language)} className="inline-flex items-center gap-1 hover:text-brand">
                      <Volume2 size={11} /> listen
                    </button>
                  </div>
                )}
              </div>
              {m.role === "user" && (
                <span className="mt-1 grid size-8 shrink-0 place-items-center rounded-xl bg-muted/10 text-muted"><User size={15} /></span>
              )}
            </motion.div>
          ))}
          {send.isPending && (
            <div className="flex gap-3">
              <span className="grid size-8 place-items-center rounded-xl bg-brand/10 text-brand"><Bot size={16} /></span>
              <div className="rounded-2xl rounded-tl-md border border-line bg-surface px-4 py-3">
                <span className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <span key={i} className="size-1.5 animate-bounce rounded-full bg-muted" style={{ animationDelay: `${i * 120}ms` }} />
                  ))}
                </span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); submit(); }}
        className="mt-3 flex items-center gap-2"
      >
        {speech.supported && (
          <Button type="button" variant={speech.listening ? "danger" : "outline"} onClick={speech.listening ? speech.stop : speech.start}
            title={t("coach.voice")} className="size-11 rounded-full p-0">
            <Mic size={17} className={speech.listening ? "animate-pulse" : ""} />
          </Button>
        )}
        <input
          className="input flex-1"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("coach.placeholder")}
        />
        <Button type="submit" disabled={!input.trim() || send.isPending} className="size-11 rounded-full p-0">
          <Send size={17} />
        </Button>
      </form>
    </div>
  );
}
