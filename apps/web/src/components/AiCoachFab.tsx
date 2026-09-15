import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  Bot,
  Send,
  Mic,
  Volume2,
  User,
  X,
  Minus,
  Sparkles,
  RotateCcw,
  Maximize2,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { http } from "@/lib/api";
import { Button } from "@/components/ui";
import { useSpeechRecognition, speak } from "@/lib/hooks";
import { cn } from "@/lib/utils";

interface Msg {
  role: "user" | "assistant";
  content: string;
  provider?: string | null;
  timestamp?: string;
}

const ROUTE_SUGGESTIONS: Record<string, string[]> = {
  "/budgets": [
    "Am I on track with my monthly budget?",
    "Suggest a 50/30/20 budget breakdown for my income",
    "Which categories am I overspending on?",
  ],
  "/transactions": [
    "Find my largest expenses this month",
    "Are there any recurring subscription increases?",
    "Are there duplicate or suspicious transactions?",
  ],
  "/tax": [
    "What deductions can I claim for my home office?",
    "Estimate my tax liability with current deductions",
    "How is my quarterly GST BAS calculated?",
  ],
  "/family": [
    "How much has the household spent this month?",
    "Have any child accounts exceeded their limit?",
    "Suggest fair monthly spending limits",
  ],
  "/goals": [
    "How long until I reach my emergency fund goal?",
    "How can I accelerate saving for my top goal?",
    "Calculate monthly contribution needed for $10k",
  ],
  "/debts": [
    "Compare Avalanche vs Snowball debt payoff",
    "How much interest do I save with $100 extra/month?",
    "Create an aggressive debt elimination plan",
  ],
  "/connections": [
    "How do I connect my Australian bank via Basiq Open Banking?",
    "How does Stripe revenue sync with my tax profile?",
    "Is my bank connection end-to-end encrypted?",
  ],
  "/ai-eval": [
    "Explain supervisor routing and specialist agents",
    "How does PII redaction protect my account numbers?",
    "What AI models power FinanceBuddy?",
  ],
  "/settings": [
    "How does the zero-knowledge vault protect my data?",
    "How do I enable passkey biometric authentication?",
    "What does the AI Diagnostics toggle do?",
  ],
};

const DEFAULT_SUGGESTIONS = [
  "How is my overall financial health trending?",
  "What is my net cash flow this month?",
  "Give me 3 actionable money-saving tips",
];

export default function AiCoachFab() {
  const { t, i18n } = useTranslation();
  const location = useLocation();

  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [mode, setMode] = useState<string>("auto");

  const bottomRef = useRef<HTMLDivElement>(null);
  const speech = useSpeechRecognition(i18n.language || "en-US");

  // Voice transcript into input box
  useEffect(() => {
    if (speech.transcript) {
      setInput(speech.transcript);
    }
  }, [speech.transcript]);

  // Auto-scroll on new message
  useEffect(() => {
    if (isOpen && !isMinimized) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isOpen, isMinimized]);

  // Get route-aware suggestions
  const currentPath = location.pathname.toLowerCase();
  const matchedRoute = Object.keys(ROUTE_SUGGESTIONS).find(
    (path) => currentPath === path || (path !== "/" && currentPath.startsWith(path)),
  );
  const starterPrompts = matchedRoute
    ? ROUTE_SUGGESTIONS[matchedRoute]
    : DEFAULT_SUGGESTIONS;

  const sendMutation = useMutation({
    mutationFn: async (text: string) => {
      const { data } = await http.post("/chat/send", {
        thread_id: threadId,
        message: text,
        agent_mode: mode,
        page_context: location.pathname,
      });
      return data;
    },
    onSuccess: (data) => {
      setThreadId(data.thread_id);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: data.reply.content,
          provider: data.reply.provider,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      const errorMsg =
        typeof detail === "string"
          ? detail
          : "⚠️ The AI engine is temporarily unavailable. Please verify LLM provider configuration and try again.";
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: errorMsg,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    },
  });

  function handleSubmit(overrideText?: string) {
    const text = (overrideText || input).trim();
    if (!text || sendMutation.isPending) return;

    setMessages((m) => [
      ...m,
      {
        role: "user",
        content: text,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      },
    ]);
    setInput("");
    speech.reset();
    sendMutation.mutate(text);
  }

  function handleResetChat() {
    setMessages([]);
    setThreadId(null);
    setInput("");
    speech.reset();
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end">
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, scale: 0.88, y: 20 }}
            animate={{
              opacity: 1,
              scale: 1,
              y: 0,
              height: isMinimized ? "auto" : "540px",
            }}
            exit={{ opacity: 0, scale: 0.88, y: 20 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            className={cn(
              "mb-3 flex w-[380px] max-w-[calc(100vw-2rem)] flex-col rounded-2xl border border-line bg-surface shadow-2xl backdrop-blur-lg sm:w-[420px]",
              isMinimized ? "overflow-hidden" : "h-[540px]",
            )}
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-line bg-raised px-4 py-3">
              <div className="flex items-center gap-2.5">
                <div className="grid size-8 place-items-center rounded-xl bg-brand text-white shadow-md shadow-brand/30">
                  <Bot size={18} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold leading-tight text-ink">
                    {t("coach.title")}
                  </h3>
                  <p className="text-[11px] text-muted">
                    {location.pathname === "/" ? "Dashboard" : location.pathname}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1">
                {!isMinimized && messages.length > 0 && (
                  <button
                    onClick={handleResetChat}
                    title={t("coach.clearChat")}
                    className="rounded-lg p-1.5 text-muted transition hover:bg-surface hover:text-ink"
                  >
                    <RotateCcw size={14} />
                  </button>
                )}
                <button
                  onClick={() => setIsMinimized(!isMinimized)}
                  title={isMinimized ? t("coach.expand") : t("coach.minimize")}
                  className="rounded-lg p-1.5 text-muted transition hover:bg-surface hover:text-ink"
                >
                  {isMinimized ? <Maximize2 size={14} /> : <Minus size={14} />}
                </button>
                <button
                  onClick={() => setIsOpen(false)}
                  title={t("coach.close")}
                  className="rounded-lg p-1.5 text-muted transition hover:bg-surface hover:text-ink"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            {/* Body */}
            {!isMinimized && (
              <>
                {/* Agent mode selector */}
                <div className="flex gap-1 border-b border-line/60 bg-surface/50 px-3 py-1.5 overflow-x-auto scrollbar-none">
                  {["auto", "coach", "budget", "tax", "fraud", "goals"].map((m) => (
                    <button
                      key={m}
                      onClick={() => setMode(m)}
                      className={cn(
                        "whitespace-nowrap rounded-md px-2 py-1 text-[11px] font-medium transition",
                        mode === m
                          ? "bg-brand text-white shadow-sm"
                          : "text-muted hover:bg-raised hover:text-ink",
                      )}
                    >
                      {t(`coach.modes.${m}`, m)}
                    </button>
                  ))}
                </div>

                {/* Messages Container */}
                <div className="flex-1 overflow-y-auto p-4 space-y-3.5">
                  {messages.length === 0 && (
                    <div className="flex h-full flex-col justify-center py-4 text-center">
                      <div className="mx-auto mb-3 grid size-12 place-items-center rounded-2xl bg-brand/10 text-brand">
                        <Sparkles size={24} />
                      </div>
                      <p className="text-sm font-semibold text-ink">
                        {t("coach.fabTitle")}
                      </p>
                      <p className="mt-1 text-xs text-muted">
                        {t("coach.pageSuggestions")}:
                      </p>

                      <div className="mt-3 flex flex-col gap-1.5 text-left">
                        {starterPrompts.map((prompt, idx) => (
                          <button
                            key={idx}
                            onClick={() => handleSubmit(prompt)}
                            className="rounded-xl border border-line bg-raised/50 p-2.5 text-xs text-ink transition hover:border-brand/50 hover:bg-brand/5 hover:text-brand"
                          >
                            💡 {prompt}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {messages.map((m, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, y: 5 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={cn("flex gap-2.5", m.role === "user" && "justify-end")}
                    >
                      {m.role === "assistant" && (
                        <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-brand/10 text-brand">
                          <Bot size={15} />
                        </span>
                      )}

                      <div
                        className={cn(
                          "max-w-[82%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-xs leading-relaxed",
                          m.role === "user"
                            ? "bg-brand text-white rounded-br-sm shadow-sm"
                            : "bg-raised border border-line rounded-tl-sm text-ink",
                        )}
                      >
                        {m.content}
                        {m.role === "assistant" && (
                          <div className="mt-2 flex items-center justify-between gap-2 border-t border-line/40 pt-1.5 text-[10px] text-muted">
                            <span>{m.provider ? `via ${m.provider}` : "AI"}</span>
                            <button
                              onClick={() => speak(m.content, i18n.language || "en-US")}
                              className="inline-flex items-center gap-1 text-muted transition hover:text-brand"
                            >
                              <Volume2 size={12} /> {t("coach.speak")}
                            </button>
                          </div>
                        )}
                      </div>

                      {m.role === "user" && (
                        <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-muted/10 text-muted">
                          <User size={14} />
                        </span>
                      )}
                    </motion.div>
                  ))}

                  {sendMutation.isPending && (
                    <div className="flex gap-2.5">
                      <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-brand/10 text-brand">
                        <Bot size={15} />
                      </span>
                      <div className="rounded-2xl rounded-tl-sm border border-line bg-raised px-4 py-3">
                        <span className="flex gap-1.5">
                          {[0, 1, 2].map((i) => (
                            <span
                              key={i}
                              className="size-2 animate-bounce rounded-full bg-brand/70"
                              style={{ animationDelay: `${i * 140}ms` }}
                            />
                          ))}
                        </span>
                      </div>
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>

                {/* Footer Input */}
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleSubmit();
                  }}
                  className="border-t border-line bg-raised/40 p-3"
                >
                  {speech.listening && (
                    <div className="mb-2 flex items-center gap-2 text-xs text-neg animate-pulse">
                      <span className="size-2 rounded-full bg-neg" />
                      {t("coach.listening")}
                    </div>
                  )}

                  <div className="flex items-center gap-2">
                    {speech.supported && (
                      <Button
                        type="button"
                        variant={speech.listening ? "danger" : "outline"}
                        size="sm"
                        onClick={speech.listening ? speech.stop : speech.start}
                        title={t("coach.voice")}
                        className="size-9 rounded-xl p-0"
                      >
                        <Mic size={15} className={speech.listening ? "animate-pulse" : ""} />
                      </Button>
                    )}

                    <input
                      className="input flex-1 h-9 text-xs px-3"
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      placeholder={t("coach.placeholder")}
                    />

                    <Button
                      type="submit"
                      disabled={!input.trim() || sendMutation.isPending}
                      size="sm"
                      className="size-9 rounded-xl p-0"
                    >
                      <Send size={15} />
                    </Button>
                  </div>
                </form>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Floating Action Button */}
      <motion.button
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => {
          if (!isOpen) {
            setIsOpen(true);
            setIsMinimized(false);
          } else if (isMinimized) {
            setIsMinimized(false);
          } else {
            setIsOpen(false);
          }
        }}
        className={cn(
          "group relative flex size-14 items-center justify-center rounded-2xl bg-brand text-white shadow-xl shadow-brand/35 transition-colors focus:outline-none focus:ring-4 focus:ring-brand/30",
          isOpen && !isMinimized && "bg-brand/90",
        )}
        aria-label={t("coach.fabTitle")}
      >
        <div className="relative">
          {isOpen && !isMinimized ? (
            <X size={24} />
          ) : (
            <>
              <Bot size={24} />
              <span className="absolute -top-1 -right-1 flex size-3">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
                <span className="relative inline-flex size-3 rounded-full bg-amber-500" />
              </span>
            </>
          )}
        </div>
      </motion.button>
    </div>
  );
}
