import { useCallback, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { translate, type TranslationKey } from "../i18n";
import type {
  DashboardResponse,
  DistrictNotificationsResponse,
  StorageLiveResponse,
  DatasetEntry,
  ExperimentsResponse,
  ExperimentDetailsResponse,
  ModelVersionsResponse,
  TestRunsResponse,
  TrainingHistoryResponse,
  ModelMetricsResponse,
} from "./types";

/** Backend dashboard stats + history (/api/dashboard). */
export function useDashboard(enabled: boolean) {
  return useQuery<DashboardResponse>({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardResponse>("/api/dashboard"),
    enabled,
    staleTime: 60 * 1000,
  });
}

/** Real-time district storage notifications (max 21, priority-ranked). */
export function useDistrictNotifications(enabled: boolean) {
  return useQuery<DistrictNotificationsResponse>({
    queryKey: ["district-notifications"],
    queryFn: () => api<DistrictNotificationsResponse>("/api/notifications/district-storage?limit=21"),
    enabled,
    staleTime: 2 * 60 * 1000,
  });
}

/** Full 31-district live storage telemetry. */
export function useStorageLive(enabled: boolean) {
  return useQuery<StorageLiveResponse>({
    queryKey: ["storage-live"],
    queryFn: () => api<StorageLiveResponse>("/api/districts/storage-live"),
    enabled,
    staleTime: 2 * 60 * 1000,
  });
}

/** Dataset catalogue from the backend. */
export function useDatasets(enabled: boolean) {
  return useQuery<DatasetEntry[]>({
    queryKey: ["datasets"],
    queryFn: () => api<DatasetEntry[]>("/api/datasets"),
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

/** MLOps experiment tracking records (/api/experiments). Admin/Researcher. */
export function useExperiments(enabled: boolean) {
  return useQuery<ExperimentsResponse>({
    queryKey: ["experiments"],
    queryFn: () => api<ExperimentsResponse>("/api/experiments"),
    enabled,
    staleTime: 60 * 1000,
  });
}

/** Registered model versions (/api/model_versions). */
export function useModelVersions(enabled: boolean) {
  return useQuery<ModelVersionsResponse>({
    queryKey: ["model-versions"],
    queryFn: () => api<ModelVersionsResponse>("/api/model_versions"),
    enabled,
    staleTime: 60 * 1000,
  });
}

/** Backend self-test runs (/api/test_runs). */
export function useTestRuns(enabled: boolean) {
  return useQuery<TestRunsResponse>({
    queryKey: ["test-runs"],
    queryFn: () => api<TestRunsResponse>("/api/test_runs"),
    enabled,
    staleTime: 60 * 1000,
  });
}

/** Raw training log tail (/api/training_history). */
export function useTrainingHistory(enabled: boolean) {
  return useQuery<TrainingHistoryResponse>({
    queryKey: ["training-history"],
    queryFn: () => api<TrainingHistoryResponse>("/api/training_history"),
    enabled,
    staleTime: 60 * 1000,
  });
}

/**
 * Honest per-model metrics from training_registry.json (/api/model_metrics).
 *
 * Drives the Model Confidence card: held-out test numbers, the train/test gap,
 * the dataset provenance and whether the quantum leg was simulated. Nothing is
 * defaulted client-side — when the registry is missing the backend says so.
 */
export function useModelMetrics(enabled: boolean) {
  return useQuery<ModelMetricsResponse>({
    queryKey: ["model-metrics"],
    queryFn: () => api<ModelMetricsResponse>("/api/model_metrics"),
    enabled,
    staleTime: 60 * 1000,
    retry: 1,
  });
}

/** Single experiment with metrics + hyperparameter trials (/api/experiments/<id>). */
export function useExperimentDetails(expId: string | null) {
  return useQuery<ExperimentDetailsResponse>({
    queryKey: ["experiment", expId],
    queryFn: () => api<ExperimentDetailsResponse>(`/api/experiments/${expId}`),
    enabled: !!expId,
    staleTime: 60 * 1000,
  });
}

interface WeatherData {
  current?: {
    temperature_2m?: number;
    relative_humidity_2m?: number;
    apparent_temperature?: number;
    precipitation?: number;
    weather_code?: number;
    wind_speed_10m?: number;
    uv_index?: number;
  };
  daily?: {
    temperature_2m_max?: number[];
    temperature_2m_min?: number[];
    precipitation_probability_max?: number[];
  };
  locationName: string;
}

/**
 * Live weather from Open-Meteo (the same public API the web dashboard calls).
 * Uses expo-location when permission is granted; falls back to Bengaluru
 * coordinates exactly like the web app does.
 */
export function useLocalWeather() {
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const coords = await resolveCoords();
        const data = await fetchWeather(coords.lat, coords.lon);
        if (!cancelled) {
          setWeather({ ...data, locationName: coords.name });
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message || "Failed to load weather.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  return { weather, loading, error, refresh };
}

/**
 * Map an Open-Meteo condition code to a translation key.
 * Returns a key (not text) so the caller renders it in the active language.
 */
export function weatherCodeKey(code?: number): TranslationKey {
  if (code === undefined || code === null) return "weather.clearSkies";
  if (code === 0) return "weather.clearSky";
  if (code <= 3) return "weather.partlyCloudy";
  if (code <= 48) return "weather.foggy";
  if (code <= 55) return "weather.lightDrizzle";
  if (code <= 65) return "weather.moderateRain";
  if (code <= 82) return "weather.heavyShowers";
  if (code >= 95) return "weather.thunderstorm";
  return "weather.fairWeather";
}

/**
 * Reject if a promise does not settle in time.
 *
 * A location fix may never arrive (indoors, emulator with no fix) and the
 * permission promise never settles if the system dialog is left unanswered.
 * Without this the dashboard would show its loading spinner forever.
 */
function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Timed out")), ms);
    p.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      (e) => {
        clearTimeout(timer);
        reject(e);
      },
    );
  });
}

async function resolveCoords(): Promise<{ lat: number; lon: number; name: string }> {
  // Default: Bengaluru (matches web dashboard fallback).
  let lat = 12.9716;
  let lon = 77.5946;
  let name = "Bengaluru, Karnataka";

  try {
    const Location = await import("expo-location");
    const { status } = await withTimeout(Location.requestForegroundPermissionsAsync(), 8000);
    if (status === "granted") {
      const pos = await withTimeout(Location.getCurrentPositionAsync({}), 8000);
      lat = pos.coords.latitude;
      lon = pos.coords.longitude;
      name = translate("weather.gpsLocation");
      try {
        const places = await withTimeout(
          Location.reverseGeocodeAsync({ latitude: lat, longitude: lon }),
          6000,
        );
        const p = places?.[0];
        if (p) {
          name = [p.city || p.district || p.region, p.region && p.city !== p.region ? p.region : null]
            .filter(Boolean)
            .join(", ");
        }
      } catch {
        // keep GPS label
      }
    }
  } catch {
    // expo-location unavailable — keep fallback coordinates
  }
  return { lat, lon, name };
}

async function fetchWeather(lat: number, lon: number): Promise<Omit<WeatherData, "locationName">> {
  const url =
    `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}` +
    `&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,uv_index` +
    `&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) throw new Error("Weather service unavailable");
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}
