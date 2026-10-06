import { test } from "node:test";
import assert from "node:assert";
import {
  clearQueuedOfflineReports,
  fetchClosureSnapshot,
  flushOfflineReports,
  formatConditionsAsOf,
  getCachedSnapshot,
  getQueuedOfflineReports,
  getSnapshotAgeMinutes,
  isSnapshotStale,
  queueOfflineReport,
  removeQueuedOfflineReport,
  saveCachedSnapshot,
} from "./offline.ts";
import type { ClosureSnapshot, OfflineReportPayload } from "../types.ts";

// Simple in-memory mock storage for testing
class MockStorage implements Storage {
  private data: Map<string, string> = new Map();

  get length(): number {
    return this.data.size;
  }

  clear(): void {
    this.data.clear();
  }

  getItem(key: string): string | null {
    return this.data.get(key) ?? null;
  }

  key(index: number): string | null {
    return Array.from(this.data.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.data.delete(key);
  }

  setItem(key: string, value: string): void {
    this.data.set(key, value);
  }
}

test("formatConditionsAsOf formats ISO timestamps to HH:MM", () => {
  assert.strictEqual(formatConditionsAsOf(""), "Conditions time unknown");
  assert.strictEqual(formatConditionsAsOf("invalid-date"), "Conditions time unknown");

  const iso = new Date(2026, 9, 6, 14, 35, 0).toISOString();
  const formatted = formatConditionsAsOf(iso);
  assert.match(formatted, /^Conditions as of \d{2}:\d{2}$/);
});

test("isSnapshotStale calculates staleness based on threshold", () => {
  const now = 1791280000000;
  const freshTime = new Date(now - 120 * 1000).toISOString(); // 2 mins ago
  const staleTime = new Date(now - 600 * 1000).toISOString(); // 10 mins ago

  assert.strictEqual(isSnapshotStale("", 300, now), true);
  assert.strictEqual(isSnapshotStale("invalid", 300, now), true);
  assert.strictEqual(isSnapshotStale(freshTime, 300, now), false);
  assert.strictEqual(isSnapshotStale(staleTime, 300, now), true);
});

test("getSnapshotAgeMinutes computes non-negative elapsed minutes", () => {
  const now = 1791280000000;
  const iso = new Date(now - 15 * 60 * 1000).toISOString();
  assert.strictEqual(getSnapshotAgeMinutes(iso, now), 15);
  assert.strictEqual(getSnapshotAgeMinutes("", now), 0);
});

test("queueOfflineReport and queue management", () => {
  const storage = new MockStorage();

  const r1 = queueOfflineReport(
    {
      lat: 12.97,
      lon: 77.59,
      depth_class: "ankle_deep",
      reporter_id: "test_reporter",
    },
    storage
  );

  const r2 = queueOfflineReport(
    {
      lat: 12.98,
      lon: 77.60,
      depth_class: "knee_deep",
      reporter_id: "test_reporter",
    },
    storage
  );

  const queued = getQueuedOfflineReports(storage);
  assert.strictEqual(queued.length, 2);
  assert.strictEqual(queued[0].depth_class, "ankle_deep");
  assert.strictEqual(queued[1].depth_class, "knee_deep");

  // Remove r1
  removeQueuedOfflineReport(r1.id!, storage);
  const remaining = getQueuedOfflineReports(storage);
  assert.strictEqual(remaining.length, 1);
  assert.strictEqual(remaining[0].id, r2.id);

  // Clear all
  clearQueuedOfflineReports(storage);
  assert.strictEqual(getQueuedOfflineReports(storage).length, 0);
});

test("flushOfflineReports sends queued items and retains failures", async () => {
  const storage = new MockStorage();

  queueOfflineReport(
    { lat: 12.91, lon: 77.61, depth_class: "pass_ok", reporter_id: "u1" },
    storage
  );
  queueOfflineReport(
    { lat: 12.92, lon: 77.62, depth_class: "fail_req", reporter_id: "u2" },
    storage
  );

  const sendMock = async (item: OfflineReportPayload): Promise<boolean> => {
    return item.depth_class !== "fail_req";
  };

  const result = await flushOfflineReports(sendMock, storage);
  assert.strictEqual(result.sent, 1);
  assert.strictEqual(result.failed, 1);

  const pending = getQueuedOfflineReports(storage);
  assert.strictEqual(pending.length, 1);
  assert.strictEqual(pending[0].depth_class, "fail_req");
});

test("saveCachedSnapshot and getCachedSnapshot persist and restore snapshot", () => {
  const storage = new MockStorage();
  const mockSnapshot: ClosureSnapshot = {
    type: "FeatureCollection",
    snapshot_version: "v1.0",
    city: "mumbai",
    city_id: 3,
    vclass: "car",
    bbox: [72.75, 18.88, 73.05, 19.3],
    generated_at: new Date().toISOString(),
    conditions_as_of: new Date().toISOString(),
    feature_count: 2,
    features: [
      {
        type: "Feature",
        geometry: { type: "LineString", coordinates: [[72.85, 19.01], [72.86, 19.02]] },
        properties: {
          segment_id: 901,
          osm_way_id: 1901,
          road_class: "primary",
          state: "impassable",
          p_unusable: 1.0,
          structure: "underpass",
        },
      },
    ],
    etag: '"abc123etag"',
  };

  saveCachedSnapshot(mockSnapshot, storage);
  const loaded = getCachedSnapshot("mumbai", "car", storage);
  assert.ok(loaded);
  assert.strictEqual(loaded.city, "mumbai");
  assert.strictEqual(loaded.etag, '"abc123etag"');
  assert.strictEqual(loaded.features.length, 1);
});

test("fetchClosureSnapshot handles 200, 304, and network failure fallback", async () => {
  const storage = new MockStorage();
  const mockSnapshot: ClosureSnapshot = {
    type: "FeatureCollection",
    snapshot_version: "v1.0",
    city: "bengaluru",
    city_id: 1,
    vclass: "car",
    bbox: [77.4, 12.8, 77.85, 13.2],
    generated_at: new Date().toISOString(),
    conditions_as_of: new Date().toISOString(),
    feature_count: 0,
    features: [],
    etag: '"etag_initial"',
  };

  // 1. Initial successful fetch (200 OK)
  const fetch200 = async (): Promise<Response> => {
    return {
      status: 200,
      ok: true,
      json: async () => mockSnapshot,
    } as unknown as Response;
  };

  const res1 = await fetchClosureSnapshot("bengaluru", "car", fetch200, storage);
  assert.strictEqual(res1.fromCache, false);
  assert.strictEqual(res1.snapshot?.etag, '"etag_initial"');

  // 2. Conditional fetch returning 304 Not Modified
  const fetch304 = async (): Promise<Response> => {
    return {
      status: 304,
      ok: false,
    } as unknown as Response;
  };

  const res2 = await fetchClosureSnapshot("bengaluru", "car", fetch304, storage);
  assert.strictEqual(res2.fromCache, true);
  assert.strictEqual(res2.snapshot?.etag, '"etag_initial"');

  // 3. Network outage (offline fetch throws)
  const fetchError = async (): Promise<Response> => {
    throw new Error("Network offline");
  };

  const res3 = await fetchClosureSnapshot("bengaluru", "car", fetchError, storage);
  assert.strictEqual(res3.fromCache, true);
  assert.strictEqual(res3.snapshot?.etag, '"etag_initial"');
});
