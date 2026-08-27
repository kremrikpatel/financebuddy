import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import en from "./en";
import es from "./es";
import fr from "./fr";
import de from "./de";
import hi from "./hi";
import ar from "./ar";

export const LANGUAGES = [
  { code: "en", label: "English", dir: "ltr" },
  { code: "es", label: "Español", dir: "ltr" },
  { code: "fr", label: "Français", dir: "ltr" },
  { code: "de", label: "Deutsch", dir: "ltr" },
  { code: "hi", label: "हिन्दी", dir: "ltr" },
  { code: "ar", label: "العربية", dir: "rtl" },
] as const;

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { en, es, fr, de, hi, ar },
    fallbackLng: "en",
    interpolation: { escapeValue: false },
    detection: { order: ["localStorage", "navigator"], caches: ["localStorage"] },
  });

export function applyDirection(lang: string) {
  const entry = LANGUAGES.find((l) => l.code === lang) ?? LANGUAGES[0];
  document.documentElement.dir = entry.dir;
  document.documentElement.lang = lang;
}

export default i18n;
