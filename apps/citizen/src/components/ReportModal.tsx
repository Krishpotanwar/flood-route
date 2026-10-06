import React, { useEffect, useRef, useState } from "react";
import { LatLon } from "../types";
import { apiUrl } from "../utils/offline";

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
  demoMode?: boolean;
  isOnline?: boolean;
}

const DEPTH_OPTIONS = [
  { value: "ankle", label: "Ankle deep" },
  { value: "knee", label: "Knee deep" },
  { value: "vehicle_deep", label: "Vehicle stalling" },
];

export const ReportModal: React.FC<ReportModalProps> = ({
  isOpen,
  onClose,
  onSubmitReport,
  defaultLocation = { lat: 12.9172, lon: 77.6228 },
  demoMode = false,
  isOnline = true,
}) => {
  const [depthClass, setDepthClass] = useState("knee");
  const [lat, setLat] = useState(String(defaultLocation.lat));
  const [lon, setLon] = useState(String(defaultLocation.lon));
  const [photoRef, setPhotoRef] = useState<string>();
  const [photoUploading, setPhotoUploading] = useState(false);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const uploadController = useRef<AbortController | null>(null);
  const closeRef = useRef(onClose);
  const submittingRef = useRef(submitting);
  const sessionRef = useRef(0);
  closeRef.current = onClose;
  submittingRef.current = submitting;

  useEffect(() => {
    if (!isOpen) return;
    setDepthClass("knee");
    setLat(String(defaultLocation.lat));
    setLon(String(defaultLocation.lon));
    setPhotoRef(undefined);
    setPhotoUploading(false);
    setPhotoError(null);
    setSubmitError(null);
    setSuccess(false);
    setSubmitting(false);
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialogRef.current?.querySelector<HTMLButtonElement>("button")?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!submittingRef.current) closeRef.current();
      }
      if (event.key !== "Tab") return;
      const controls = dialogRef.current?.querySelectorAll<HTMLElement>(
        "button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href], [tabindex='0']"
      );
      if (!controls?.length) {
        event.preventDefault();
        dialogRef.current?.focus();
        return;
      }
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (!dialogRef.current?.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      sessionRef.current += 1;
      uploadController.current?.abort();
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
      previousFocus?.focus();
    };
  }, [isOpen, defaultLocation.lat, defaultLocation.lon]);

  useEffect(() => {
    if (success) dialogRef.current?.querySelector<HTMLButtonElement>(".modal-success button")?.focus();
  }, [success]);

  if (!isOpen) return null;

  const validLat = lat.trim() !== "" && Number.isFinite(Number(lat)) && Number(lat) >= 6 && Number(lat) <= 37.5;
  const validLon = lon.trim() !== "" && Number.isFinite(Number(lon)) && Number(lon) >= 68 && Number(lon) <= 97.6;
  const validLocation = validLat && validLon;

  const handlePhotoUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    setPhotoRef(undefined);
    setPhotoError(null);
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > 5 * 1024 * 1024) {
      setPhotoError("Choose a JPEG, PNG or WebP photo no larger than 5 MB.");
      event.target.value = "";
      return;
    }

    const controller = new AbortController();
    uploadController.current?.abort();
    uploadController.current = controller;
    setPhotoUploading(true);
    try {
      const response = await fetch(apiUrl("/v1/reports/photo"), {
        method: "POST",
        headers: { "Content-Type": file.type },
        body: file,
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("Photo upload failed. Retry or submit without a photo.");
      const data = await response.json();
      if (typeof data.photo_ref !== "string" || !/^ph_[a-f0-9]{24}\.jpg$/.test(data.photo_ref)) {
        throw new Error("Photo could not be verified. Retry without a photo.");
      }
      if (!controller.signal.aborted) setPhotoRef(data.photo_ref);
    } catch (error) {
      if (!controller.signal.aborted) {
        setPhotoError(error instanceof Error ? error.message : "Photo upload failed.");
      }
    } finally {
      if (!controller.signal.aborted) setPhotoUploading(false);
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!validLocation || submitting || photoUploading) return;
    const session = sessionRef.current;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await onSubmitReport({ lat: Number(lat), lon: Number(lon), depthClass, photoRef });
      if (sessionRef.current === session) setSuccess(true);
    } catch (error) {
      if (sessionRef.current === session) {
        setSubmitError(error instanceof Error ? error.message : "Report could not be saved. Please retry.");
      }
    } finally {
      if (sessionRef.current === session) setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={() => { if (!submitting) onClose(); }}>
      <div
        className="modal-dialog"
        ref={dialogRef}
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="report-title"
        aria-describedby="report-description"
        tabIndex={-1}
      >
        <div className="modal-header">
          <div>
            <p className="eyebrow">{demoMode ? "Demo report" : "Community observation"}</p>
            <h2 id="report-title">Report a flooded road.</h2>
          </div>
          <button type="button" className="select-btn btn-icon" onClick={onClose} disabled={submitting} aria-label="Close report dialog">×</button>
        </div>
        <p className="field-hint" id="report-description">
          {demoMode ? "Try the reporting flow. No report will be sent." : "Share what you can observe safely. Reports may be queued while offline."}
        </p>

        {success ? (
          <div className="modal-success" role="status">
            <p className="eyebrow">Saved</p>
            <h3>{demoMode ? "Demo report recorded." : "Report saved for submission."}</h3>
            <p className="field-hint">{demoMode ? "No report was sent. Switch to Live data to submit a real observation." : "Queued reports upload when a connection is available."}</p>
            <button type="button" className="btn-primary" onClick={onClose}>Done <span aria-hidden="true">→</span></button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="modal-form" aria-busy={submitting}>
            <div className="field-group">
              <span className="field-label" id="depth-label">Observed water depth</span>
              <div className="segmented-row" role="group" aria-labelledby="depth-label">
                {DEPTH_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={`segmented-btn ${depthClass === option.value ? "active" : ""}`}
                    aria-pressed={depthClass === option.value}
                    onClick={() => setDepthClass(option.value)}
                    disabled={submitting}
                  >{option.label}</button>
                ))}
              </div>
            </div>

            <div className="field-group">
              <label className="field-label" htmlFor="photo-input">Evidence photo <span className="field-hint">(optional)</span></label>
              <input
                id="photo-input"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                capture="environment"
                onChange={handlePhotoUpload}
                disabled={photoUploading || submitting || demoMode || !isOnline}
                aria-describedby="photo-hint"
              />
              <p className="field-hint" id="photo-hint">{demoMode || !isOnline ? "Photo upload is available with the connected API in Live data mode." : "JPEG, PNG or WebP · 5 MB max. Photo metadata is removed on upload."}</p>
              {photoUploading && <p className="field-hint" role="status">Uploading and removing photo metadata…</p>}
              {photoRef && <p className="field-hint" role="status">Photo attached. Metadata removed.</p>}
              {photoError && <p className="field-hint" role="alert">{photoError}</p>}
            </div>

            <div className="coordinate-fields">
              <div className="field-group">
                <label className="field-label" htmlFor="report-latitude">Latitude</label>
                <input id="report-latitude" type="number" step="any" min={6} max={37.5} required className="text-input" value={lat} onChange={(event) => setLat(event.target.value)} disabled={submitting} aria-invalid={!validLat} />
              </div>
              <div className="field-group">
                <label className="field-label" htmlFor="report-longitude">Longitude</label>
                <input id="report-longitude" type="number" step="any" min={68} max={97.6} required className="text-input" value={lon} onChange={(event) => setLon(event.target.value)} disabled={submitting} aria-invalid={!validLon} />
              </div>
            </div>
            <p className="field-hint">Confirm the coordinates of the flooded road before submitting.</p>
            {!validLocation && <p className="field-hint" role="alert">Choose a location in India: latitude 6 to 37.5 and longitude 68 to 97.6.</p>}
            {submitError && <p className="field-hint" role="alert">{submitError}</p>}
            <button type="submit" className="btn-primary" disabled={submitting || photoUploading || !validLocation}>
              {submitting ? "Saving report…" : demoMode ? "Preview report submission" : "Submit road report"}
              {!submitting && <span aria-hidden="true">↗</span>}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};
