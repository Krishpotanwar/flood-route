import type { ClosureSnapshot, OfflineReportPayload, VehicleClass } from "../types.ts";

export const QUEUE_KEY = "floodroute_offline_reports";
export const SNAPSHOT_PREFIX = "floodroute_snapshot_";
export const DEFAULT_STALE_SECONDS = 300; // 5 minutes (TRD 11)
export const SYNC_TAG = "floodroute-sync-reports";

const VITE_ENV =
  typeof import.meta !== "undefined"
    ? (import.meta as unknown as { env?: Record<string, string | undefined> }).env
    : undefined;
const API_BASE = (VITE_ENV?.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

/**
 * Prefix an API path with the configured base URL, falling back to
 * same-origin relative paths when no base is configured.
 */
export function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${p}`;
}

/**
 * Ask the service worker to flush queued reports via Background Sync.
 * No-op where service workers or the SyncManager are unavailable: the
 * online/offline window listeners flush the queue instead.
 */
export function tryRegisterBackgroundSync(): void {
  try {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.ready
      .then((reg) => {
        const r = reg as unknown as { sync?: { register: (tag: string) => Promise<void> } };
        if (r.sync) r.sync.register(SYNC_TAG).catch(() => {});
      })
      .catch(() => {});
  } catch {
    // Background Sync unsupported: online/offline listeners flush the queue instead.
  }
}

/**
 * Format conditions timestamp into standard TRD 11 banner string.
 * Example output: "Conditions as of 14:30"
 */
export function formatConditionsAsOf(isoString: string): string {
  if (!isoString) return "Conditions time unknown";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "Conditions time unknown";
    const hours = String(d.getHours()).padStart(2, "0");
    const minutes = String(d.getMinutes()).padStart(2, "0");
    return `Conditions as of ${hours}:${minutes}`;
  } catch {
    return "Conditions time unknown";
  }
}

/**
 * Check whether snapshot or data age exceeds staleness threshold.
 */
export function isSnapshotStale(
  isoString: string,
  maxAgeSeconds: number = DEFAULT_STALE_SECONDS,
  nowMs?: number
): boolean {
  if (!isoString) return true;
  const time = Date.parse(isoString);
  if (isNaN(time)) return true;
  const current = nowMs !== undefined ? nowMs : Date.now();
  const elapsedSeconds = (current - time) / 1000;
  return elapsedSeconds > maxAgeSeconds;
}

/**
 * Calculate age in elapsed minutes from timestamp.
 */
export function getSnapshotAgeMinutes(isoString: string, nowMs?: number): number {
  if (!isoString) return 0;
  const time = Date.parse(isoString);
  if (isNaN(time)) return 0;
  const current = nowMs !== undefined ? nowMs : Date.now();
  const elapsedMinutes = Math.floor((current - time) / 60000);
  return elapsedMinutes > 0 ? elapsedMinutes : 0;
}

/**
 * Get storage object safely with fallback when window is not available (e.g. during Node tests).
 */
function getStorage(storage?: Storage): Storage | null {
  if (storage) return storage;
  try {
    if (typeof window !== "undefined") return window.localStorage;
  } catch { /* Storage is blocked; callers decide whether it is required. */ }
  return null;
}

/**
 * Queue an offline crowd report for later submission when back online.
 */
export function queueOfflineReport(
  report: Omit<OfflineReportPayload, "queued_at">,
  storage?: Storage
): OfflineReportPayload {
  const payload: OfflineReportPayload = {
    ...report,
    id: report.id || `rep_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    queued_at: new Date().toISOString(),
  };

  const store = getStorage(storage);
  if (!store) throw new Error("Report could not be saved. Allow browser storage and try again.");
  const existing = getQueuedOfflineReports(store);
  existing.push(payload);
  store.setItem(QUEUE_KEY, JSON.stringify(existing));

  return payload;
}

/**
 * Retrieve all currently queued offline crowd reports.
 */
export function getQueuedOfflineReports(storage?: Storage): OfflineReportPayload[] {
  const store = getStorage(storage);
  if (!store) return [];
  try {
    const raw = store.getItem(QUEUE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/**
 * Remove a specific queued report by its id or queued_at timestamp.
 */
export function removeQueuedOfflineReport(reportIdOrQueuedAt: string, storage?: Storage): void {
  const store = getStorage(storage);
  if (!store) return;
  try {
    const current = getQueuedOfflineReports(store);
    const filtered = current.filter(
      (r) => r.id !== reportIdOrQueuedAt && r.queued_at !== reportIdOrQueuedAt
    );
    store.setItem(QUEUE_KEY, JSON.stringify(filtered));
  } catch {
    // Storage access error
  }
}

/**
 * Clear all queued offline crowd reports.
 */
export function clearQueuedOfflineReports(storage?: Storage): void {
  const store = getStorage(storage);
  if (!store) return;
  try {
    store.removeItem(QUEUE_KEY);
  } catch {
    // Storage access error
  }
}

/**
 * Flush all queued offline reports to the server.
 */
// ponytail: one queue flush per tab; use an IndexedDB lease for cross-tab sync.
let reportsFlushing = false;
export async function flushOfflineReports(
  sendFn: (report: OfflineReportPayload) => Promise<boolean>,
  storage?: Storage
): Promise<{ sent: number; failed: number }> {
  if (reportsFlushing) return { sent: 0, failed: 0 };
  reportsFlushing = true;
  try {
    const reports = getQueuedOfflineReports(storage);
    if (reports.length === 0) {
      return { sent: 0, failed: 0 };
    }

    let sent = 0;
    let failed = 0;
    const sentIds = new Set<string>();

    for (const rep of reports) {
      try {
        const success = await sendFn(rep);
        if (success) {
          sent += 1;
          sentIds.add(rep.id || rep.queued_at);
        } else {
          failed += 1;
        }
      } catch {
        failed += 1;
      }
    }

    const store = getStorage(storage);
    if (store) {
      try {
        const remaining = getQueuedOfflineReports(store).filter((report) => !sentIds.has(report.id || report.queued_at));
        store.setItem(QUEUE_KEY, JSON.stringify(remaining));
      } catch {
        // Storage write error
      }
    }

    return { sent, failed };
  } finally { reportsFlushing = false; }
}

/**
 * Resolve cache key for a city and vehicle class snapshot.
 */
export function getSnapshotCacheKey(city: string, vclass: string): string {
  return `${SNAPSHOT_PREFIX}${city.trim().toLowerCase()}_${vclass}`;
}

/**
 * Save snapshot payload to local cache.
 */
export function saveCachedSnapshot(snapshot: ClosureSnapshot, storage?: Storage): void {
  const store = getStorage(storage);
  if (!store || !snapshot.city || !snapshot.vclass) return;
  try {
    const key = getSnapshotCacheKey(snapshot.city, snapshot.vclass);
    store.setItem(key, JSON.stringify(snapshot));
  } catch {
    // Storage write error
  }
}

/**
 * Retrieve cached snapshot payload from local cache.
 */
export function getCachedSnapshot(
  city: string,
  vclass: string,
  storage?: Storage
): ClosureSnapshot | null {
  const store = getStorage(storage);
  if (!store) return null;
  try {
    const key = getSnapshotCacheKey(city, vclass);
    const raw = store.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as ClosureSnapshot;
  } catch {
    return null;
  }
}

/**
 * Fetch closure snapshot from API with fallback to local cache.
 */
export async function fetchClosureSnapshot(
  city: string,
  vclass: VehicleClass,
  fetchFn?: typeof fetch,
  storage?: Storage
): Promise<{ snapshot: ClosureSnapshot | null; fromCache: boolean; isStale: boolean }> {
  const runner = fetchFn || (typeof window !== "undefined" ? window.fetch.bind(window) : undefined);
  const cached = getCachedSnapshot(city, vclass, storage);

  if (!runner) {
    return {
      snapshot: cached,
      fromCache: true,
      isStale: cached ? Boolean(cached.stale) || isSnapshotStale(cached.conditions_as_of) : true,
    };
  }

  try {
    const headers: Record<string, string> = {};
    if (cached?.etag) {
      headers["If-None-Match"] = cached.etag;
    }

    const res = await runner(
      apiUrl(`/v1/feed/snapshot/closures?city=${encodeURIComponent(city)}&vclass=${encodeURIComponent(vclass)}`),
      { headers, signal: AbortSignal.timeout(7000) }
    );

    if (res.status === 304 && cached) {
      return {
        snapshot: cached,
        fromCache: true,
        isStale: Boolean(cached.stale) || isSnapshotStale(cached.conditions_as_of),
      };
    }

    if (res.ok) {
      const data: ClosureSnapshot = await res.json();
      saveCachedSnapshot(data, storage);
      return {
        snapshot: data,
        fromCache: false,
        isStale: Boolean(data.stale) || isSnapshotStale(data.conditions_as_of),
      };
    }

    // Server error or non-200
    return {
      snapshot: cached,
      fromCache: true,
      isStale: cached ? Boolean(cached.stale) || isSnapshotStale(cached.conditions_as_of) : true,
    };
  } catch {
    // Network failure (offline)
    return {
      snapshot: cached,
      fromCache: true,
      isStale: cached ? Boolean(cached.stale) || isSnapshotStale(cached.conditions_as_of) : true,
    };
  }
}
