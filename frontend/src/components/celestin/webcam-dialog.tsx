/**
 * The webcam, for a computer: a live view of the sheet in front of it, a button to take the picture, and a
 * chance to take it again before it is used. On a phone the browser's own camera does this job
 * (`photo-button.tsx`), so this never opens there.
 */

import { Camera, Loader2, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { primary, secondary } from "@/components/celestin/styles";
import { browserWebcam, type WebcamDeps } from "@/components/celestin/webcam-camera";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { m } from "@/paraglide/messages";

type View =
  | { kind: "starting" }
  | { kind: "live" }
  | { kind: "taken"; blob: Blob; url: string }
  | { kind: "error"; denied: boolean };

export function WebcamDialog({
  open,
  onOpenChange,
  onPhoto,
  deps = browserWebcam,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The picture she chose to use. */
  onPhoto: (photo: Blob) => void;
  deps?: WebcamDeps;
}) {
  const [view, setView] = useState<View>({ kind: "starting" });
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const release = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const start = useCallback(async () => {
    setView({ kind: "starting" });
    try {
      const stream = await deps.getCamera();
      streamRef.current = stream;
      setView({ kind: "live" });
    } catch (error) {
      setView({
        kind: "error",
        denied: error instanceof DOMException && error.name === "NotAllowedError",
      });
    }
  }, [deps]);

  // The camera is on only while the dialog is open and a picture is not on screen: the light goes off with it.
  useEffect(() => {
    if (!open) return;
    void start();
    return release;
  }, [open, start, release]);

  // The stream is handed to the video once both exist.
  useEffect(() => {
    const video = videoRef.current;
    if (view.kind === "live" && video && streamRef.current) {
      video.srcObject = streamRef.current;
      // Some browsers refuse autoplay: the picture is still taken from the live frame.
      void Promise.resolve(video.play?.()).catch(() => undefined);
    }
  }, [view]);

  useEffect(() => {
    if (view.kind !== "taken") return;
    return () => URL.revokeObjectURL(view.url);
  }, [view]);

  const take = async () => {
    const video = videoRef.current;
    if (!video) return;
    try {
      const blob = await deps.capture(video);
      release();
      setView({ kind: "taken", blob, url: URL.createObjectURL(blob) });
    } catch {
      setView({ kind: "error", denied: false });
    }
  };

  const use = () => {
    if (view.kind !== "taken") return;
    onPhoto(view.blob);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{m.lesson_webcam_title()}</DialogTitle>
          <DialogDescription>{m.lesson_webcam_description()}</DialogDescription>
        </DialogHeader>
        <div className="relative aspect-video overflow-hidden rounded-lg bg-black">
          {view.kind === "starting" && (
            <p className="absolute inset-0 flex items-center justify-center gap-2 text-sm text-white/80">
              <Loader2 className="size-4 animate-spin" /> {m.lesson_webcam_starting()}
            </p>
          )}
          {view.kind === "live" && (
            <video ref={videoRef} autoPlay muted playsInline className="size-full object-contain" />
          )}
          {view.kind === "taken" && (
            <img
              src={view.url}
              alt={m.lesson_webcam_preview()}
              className="size-full object-contain"
            />
          )}
          {view.kind === "error" && (
            <p
              role="alert"
              className="absolute inset-0 flex items-center justify-center p-6 text-center text-sm text-white"
            >
              {view.denied ? m.lesson_webcam_denied() : m.lesson_webcam_none()}
            </p>
          )}
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          {view.kind === "live" && (
            <button
              type="button"
              onClick={() => void take()}
              className={`${primary} min-h-10 gap-2 px-4`}
            >
              <Camera className="size-4" aria-hidden /> {m.lesson_webcam_capture()}
            </button>
          )}
          {view.kind === "taken" && (
            <>
              <button
                type="button"
                onClick={() => void start()}
                className={`${secondary} min-h-10 gap-2 px-4`}
              >
                <RotateCcw className="size-4" aria-hidden /> {m.lesson_webcam_retake()}
              </button>
              <button type="button" onClick={use} className={`${primary} min-h-10 px-4`}>
                {m.lesson_webcam_use()}
              </button>
            </>
          )}
          {view.kind === "error" && (
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className={`${secondary} min-h-10 px-4`}
            >
              {m.common_cancel()}
            </button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
