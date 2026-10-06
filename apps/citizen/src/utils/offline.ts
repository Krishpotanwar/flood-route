import type { ClosureSnapshot, OfflineReportPayload, VehicleClass } from "../types.ts";

export const QUEUE_KEY = "floodroute_offline_reports";
export const SNAPSHOT_PREFIX = "floodroute_snapshot_";
export const DEFAULT_STALE_SECONDS = 300; // 5 minutes (TRD 11)

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
  if (typeof window !== "undefined" && window.localStorage) {
    return window.localStorage;
  }
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
  if (store) {
    try {
      const existing = getQueuedOfflineReports(store);
      existing.push(payload);
      store.setItem(QUEUE_KEY, JSON.stringify(existing));
    } catch {
      // Storage quota or permission error
    }
  }

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
export async function flushOfflineReports(
  sendFn: (report: OfflineReportPayload) => Promise<boolean>,
  storage?: Storage
): Promise<{ sent: number; failed: number }> {
  const reports = getQueuedOfflineReports(storage);
  if (reports.length === 0) {
    return { sent: 0, failed: 0 };
  }

  let sent = 0;
  let failed = 0;
  const remaining: OfflineReportPayload[] = [];

  for (const rep of reports) {
    try {
      const success = await sendFn(rep);
      if (success) {
        sent += 1;
      } else {
        failed += 1;
        remaining.push(rep);
      }
    } catch {
      failed += 1;
      remaining.push(rep);
    }
  }

  const store = getStorage(storage);
  if (store) {
    try {
      store.setItem(QUEUE_KEY, JSON.stringify(remaining));
    } catch {
      // Storage write error
    }
  }

  return { sent, failed };
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
      isStale: cached ? isSnapshotStale(cached.conditions_as_of) : true,
    };
  }

  try {
    const headers: Record<string, string> = {};
    if (cached?.etag) {
      headers["If-None-Match"] = cached.etag;
    }

    const res = await runner(
      `/v1/feed/snapshot/closures?city=${encodeURIComponent(city)}&vclass=${encodeURIComponent(vclass)}`,
      { headers }
    );

    if (res.status === 304 && cached) {
      return {
        snapshot: cached,
        fromCache: true,
        isStale: isSnapshotStale(cached.conditions_as_of),
      };
    }

    if (res.ok) {
      const data: ClosureSnapshot = await res.json();
      saveCachedSnapshot(data, storage);
      return {
        snapshot: data,
        fromCache: false,
        isStale: isSnapshotStale(data.conditions_as_of),
      };
    }

    // Server error or non-200
    return {
      snapshot: cached,
      fromCache: true,
      isStale: cached ? isSnapshotStale(cached.conditions_as_of) : true,
    };
  } catch {
    // Network failure (offline)
    return {
      snapshot: cached,
      fromCache: true,
      isStale: cached ? isSnapshotStale(cached.conditions_as_of) : true,
    };
  }
}
