import React, { useState } from "react";
import { LatLon } from "../types";

interface ReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmitReport: (data: {
    lat: number;
    lon: number;
    depthClass: string;
    photoRef?: string;
  }) => Promise<void>;
  defaultLocation?: LatLon;
}

export const ReportModal: React.FC<ReportModalProps> = ({
  isOpen,
  onClose,
  onSubmitReport,
  defaultLocation = { lat: 12.9172, lon: 77.6228 }, // Silk Board default
}) => {
  const [depthClass, setDepthClass] = useState<string>("knee");
  const [lat, setLat] = useState<number>(defaultLocation.lat);
  const [lon, setLon] = useState<number>(defaultLocation.lon);
  const [photoRef, setPhotoRef] = useState<string | undefined>(undefined);
  const [photoUploading, setPhotoUploading] = useState<boolean>(false);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [success, setSuccess] = useState<boolean>(false);

  if (!isOpen) return null;

  const handlePhotoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setPhotoUploading(true);
    setPhotoError(null);

    try {
      const buffer = await file.arrayBuffer();
      const res = await fetch("/v1/reports/photo", {
        method: "POST",
        headers: { "Content-Type": file.type || "image/jpeg" },
        body: buffer,
      });

      if (!res.ok) {
        throw new Error(`Photo upload failed: HTTP ${res.status}`);
      }

      const data = await res.json();
      setPhotoRef(data.photo_ref);
    } catch (err) {
      setPhotoError(err instanceof Error ? err.message : "Upload error");
    } finally {
      setPhotoUploading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await onSubmitReport({ lat, lon, depthClass, photoRef });
      setSuccess(true);
      setTimeout(() => {
        setSuccess(false);
        onClose();
      }, 1500);
    } catch {
      // error handled by caller
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0, fontSize: "var(--fr-text-xl)" }}>Report Waterlogged Road</h2>
          <button
            type="button"
            className="select-btn"
            onClick={onClose}
            style={{ width: "2rem", height: "2rem", padding: 0 }}
          >
            ✕
          </button>
        </div>

        {success ? (
          <div style={{ textAlign: "center", padding: "1rem" }}>
            <span style={{ fontSize: "2rem" }}>✅</span>
            <p style={{ marginTop: "0.5rem", fontWeight: 600 }}>Report Submitted</p>
            <p style={{ fontSize: "var(--fr-text-sm)", color: "var(--fr-ink-2)" }}>
              Thank you for keeping fellow citizens informed.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div className="field-group">
              <label className="field-label">Water Depth</label>
              <div className="segmented-row">
                <button
                  type="button"
                  className={`segmented-btn ${depthClass === "ankle" ? "active" : ""}`}
                  onClick={() => setDepthClass("ankle")}
                >
                  Ankle-Deep
                </button>
                <button
                  type="button"
                  className={`segmented-btn ${depthClass === "knee" ? "active" : ""}`}
                  onClick={() => setDepthClass("knee")}
                >
                  Knee-Deep
                </button>
                <button
                  type="button"
                  className={`segmented-btn ${depthClass === "vehicle_deep" ? "active" : ""}`}
                  onClick={() => setDepthClass("vehicle_deep")}
                >
                  Vehicle-Stalling
                </button>
              </div>
            </div>

            <div className="field-group">
              <label className="field-label" htmlFor="photo-input">
                Evidence Photo (EXIF metadata stripped automatically)
              </label>
              <input
                id="photo-input"
                type="file"
                accept="image/*"
                capture="environment"
                onChange={handlePhotoUpload}
                disabled={photoUploading}
                style={{ fontSize: "var(--fr-text-sm)" }}
              />
              {photoUploading && (
                <span style={{ fontSize: "var(--fr-text-xs)", color: "var(--fr-ink-2)" }}>
                  Stripping metadata and sanitizing...
                </span>
              )}
              {photoRef && (
                <span style={{ fontSize: "var(--fr-text-xs)", color: "var(--fr-safe-ink)" }}>
                  ✓ Attached sanitized photo ({photoRef})
                </span>
              )}
              {photoError && (
                <span style={{ fontSize: "var(--fr-text-xs)", color: "var(--fr-risky-ink)" }}>
                  {photoError}
                </span>
              )}
            </div>

            <div style={{ display: "flex", gap: "0.5rem" }}>
              <div className="field-group" style={{ flex: 1 }}>
                <label className="field-label">Latitude</label>
                <input
                  type="number"
                  step="0.0001"
                  className="text-input"
                  value={lat}
                  onChange={(e) => setLat(parseFloat(e.target.value))}
                />
              </div>
              <div className="field-group" style={{ flex: 1 }}>
                <label className="field-label">Longitude</label>
                <input
                  type="number"
                  step="0.0001"
                  className="text-input"
                  value={lon}
                  onChange={(e) => setLon(parseFloat(e.target.value))}
                />
              </div>
            </div>

            <button type="submit" className="btn-primary" disabled={submitting || photoUploading}>
              {submitting ? "Submitting..." : "Submit Report"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};
