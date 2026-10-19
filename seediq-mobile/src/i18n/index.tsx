import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { View, StyleSheet } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { theme } from "../theme/theme";
import { en, type Translations } from "./en";
import { kn } from "./kn";
import { hi } from "./hi";

// ---------------------------------------------------------------------------
// Language catalogue — exactly three languages.
// ---------------------------------------------------------------------------

export type LanguageCode = "en" | "kn" | "hi";

export interface LanguageOption {
  code: LanguageCode;
  /** Endonym, always shown in its own script (never translated). */
  label: string;
  englishName: string;
}

export const LANGUAGES: LanguageOption[] = [
  { code: "en", label: "English", englishName: "English" },
  { code: "kn", label: "ಕನ್ನಡ", englishName: "Kannada" },
  { code: "hi", label: "हिन्दी", englishName: "Hindi" },
];

export const DEFAULT_LANGUAGE: LanguageCode = "en";
export const LANGUAGE_STORAGE_KEY = "seediq_language";

const DICTIONARIES: Record<LanguageCode, Translations> = { en, kn, hi };

// ---------------------------------------------------------------------------
// Key typing — dotted paths derived from the canonical English resource, so a
// missing or misspelled key is a compile error.
// ---------------------------------------------------------------------------

type Leaves<T> = {
  [K in keyof T & string]: T[K] extends string ? K : `${K}.${Leaves<T[K]>}`;
}[keyof T & string];

export type TranslationKey = Leaves<Translations>;

export type TranslateParams = Record<string, string | number | null | undefined>;

function lookup(dict: Translations, key: string): string | undefined {
  const parts = key.split(".");
  let node: unknown = dict;
  for (const part of parts) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

function interpolate(template: string, params?: TranslateParams): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = params[name];
    return value === undefined || value === null ? match : String(value);
  });
}

// ---------------------------------------------------------------------------
// Module-level language state.
//
// Non-React modules (the PDF report renderer, the auth error mapper) need the
// same dictionary. They read it through this module-level pointer, which the
// provider keeps in sync, so no user-facing string escapes the i18n system.
// ---------------------------------------------------------------------------

let activeLanguage: LanguageCode = DEFAULT_LANGUAGE;

export function getActiveLanguage(): LanguageCode {
  return activeLanguage;
}

export function getLanguageLabel(code: LanguageCode): string {
  return LANGUAGES.find((l) => l.code === code)?.label ?? code;
}

/**
 * Translate outside React (PDF reports, API error text).
 * Inside components always prefer the `t` returned by `useI18n()`.
 */
export function translate(key: TranslationKey, params?: TranslateParams): string {
  const dict = DICTIONARIES[activeLanguage] ?? en;
  const value = lookup(dict, key) ?? lookup(en, key) ?? key;
  return interpolate(value, params);
}

function isLanguageCode(value: string | null | undefined): value is LanguageCode {
  return value === "en" || value === "kn" || value === "hi";
}

// ---------------------------------------------------------------------------
// React binding
// ---------------------------------------------------------------------------

interface I18nContextValue {
  language: LanguageCode;
  t: (key: TranslationKey, params?: TranslateParams) => string;
  setLanguage: (code: LanguageCode) => Promise<void>;
  languages: LanguageOption[];
}

const I18nContext = createContext<I18nContextValue | undefined>(undefined);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<LanguageCode>(DEFAULT_LANGUAGE);
  const [ready, setReady] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Restore the persisted language before the first paint so the app never
  // flashes the wrong language on relaunch.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const stored = await AsyncStorage.getItem(LANGUAGE_STORAGE_KEY);
        if (!cancelled && isLanguageCode(stored)) {
          activeLanguage = stored;
          if (mounted.current) setLanguageState(stored);
        }
      } catch {
        // Unreadable storage falls back to English — never fatal.
      } finally {
        if (!cancelled && mounted.current) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setLanguage = useCallback(async (code: LanguageCode) => {
    activeLanguage = code;
    if (mounted.current) setLanguageState(code);
    try {
      await AsyncStorage.setItem(LANGUAGE_STORAGE_KEY, code);
    } catch {
      // Persistence failure keeps the in-memory language for this session.
    }
  }, []);

  const t = useCallback(
    (key: TranslationKey, params?: TranslateParams) => {
      const dict = DICTIONARIES[language] ?? en;
      const value = lookup(dict, key) ?? lookup(en, key) ?? key;
      return interpolate(value, params);
    },
    [language],
  );

  const value = useMemo<I18nContextValue>(
    () => ({ language, t, setLanguage, languages: LANGUAGES }),
    [language, t, setLanguage],
  );

  if (!ready) {
    // Single deterministic frame while the persisted choice is read.
    return <View style={styles.gate} />;
  }

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within an I18nProvider");
  return ctx;
}

const styles = StyleSheet.create({
  gate: { flex: 1, backgroundColor: theme.colors.background },
});
