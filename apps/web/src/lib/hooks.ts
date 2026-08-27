import { useCallback, useEffect, useRef, useState } from "react";

/** Web Speech API — speech-to-text (Chrome/Edge/Safari; graceful fallback). */
export function useSpeechRecognition(lang = "en-US") {
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [supported, setSupported] = useState(false);
  const recRef = useRef<any>(null);

  useEffect(() => {
    const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
    setSupported(Boolean(SR));
    if (!SR) return;
    const rec = new SR();
    rec.lang = lang;
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = (e: any) => {
      let text = "";
      for (let i = e.resultIndex; i < e.results.length; i++) text += e.results[i][0].transcript;
      setTranscript(text.trim());
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    return () => {
      try {
        rec.stop();
      } catch {
        /* noop */
      }
    };
  }, [lang]);

  const start = useCallback(() => {
    setTranscript("");
    setListening(true);
    try {
      recRef.current?.start();
    } catch {
      setListening(false);
    }
  }, []);

  const stop = useCallback(() => recRef.current?.stop(), []);

  return { listening, transcript, supported, start, stop, reset: () => setTranscript("") };
}

/** Text-to-speech for coach replies. */
export function speak(text: string, lang = "en-US") {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text.slice(0, 600));
  u.lang = lang;
  u.rate = 1.03;
  window.speechSynthesis.speak(u);
}

export function useTheme() {
  const [dark, setDark] = useState(
    () => localStorage.getItem("fb.theme") === "dark" ||
      (!localStorage.getItem("fb.theme") && matchMedia("(prefers-color-scheme: dark)").matches),
  );
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("fb.theme", dark ? "dark" : "light");
  }, [dark]);
  return { dark, toggle: () => setDark((d) => !d) };
}
