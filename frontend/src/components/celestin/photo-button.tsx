/**
 * The camera of the composer: a photo of her work, from wherever she has one.
 *
 * - On a phone: « Prendre une photo » opens the phone's own camera (a file input with `capture`), and
 *   « Choisir une image » its gallery.
 * - On a computer: « Prendre une photo » opens the webcam (`webcam-dialog.tsx`), and « Choisir une image »
 *   the file chooser. Without a webcam the button goes straight to the chooser.
 *
 * Both routes give one picture to `onPhoto`.
 */

import { Camera, FolderOpen, Loader2 } from "lucide-react";
import { useRef, useState, type ChangeEvent } from "react";

import type { WebcamDeps } from "@/components/celestin/webcam-camera";
import { WebcamDialog } from "@/components/celestin/webcam-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useCoarsePointer } from "@/hooks/use-coarse-pointer";
import { m } from "@/paraglide/messages";

const hasWebcam = (): boolean =>
  typeof navigator !== "undefined" && typeof navigator.mediaDevices?.getUserMedia === "function";

export function PhotoButton({
  onPhoto,
  busy,
  disabled,
  className,
  webcamDeps,
}: {
  onPhoto: (photo: Blob) => void;
  /** A photo is being read. */
  busy: boolean;
  disabled: boolean;
  className: string;
  webcamDeps?: WebcamDeps;
}) {
  const coarse = useCoarsePointer();
  const [webcamOpen, setWebcamOpen] = useState(false);
  const cameraInput = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const canTake = coarse || hasWebcam();

  const chosen = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = ""; // the same photo can be chosen twice
    if (file) onPhoto(file);
  };
  const take = () => (coarse ? cameraInput.current?.click() : setWebcamOpen(true));

  const trigger = (extra?: { onClick: () => void }) => (
    <button
      type="button"
      title={m.lesson_photo_open()}
      aria-label={m.lesson_photo_open()}
      disabled={disabled || busy}
      className={`${className} disabled:opacity-60`}
      {...extra}
    >
      {busy ? <Loader2 className="size-4 animate-spin" /> : <Camera className="size-4" />}
    </button>
  );

  return (
    <>
      {canTake ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild disabled={disabled || busy}>
            {trigger()}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" side="top">
            <DropdownMenuItem onSelect={take}>
              <Camera /> {m.lesson_photo_take()}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => fileInput.current?.click()}>
              <FolderOpen /> {m.lesson_photo_choose()}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : (
        trigger({ onClick: () => fileInput.current?.click() })
      )}
      {/* The phone's camera: the browser asks for it and gives back the picture. */}
      <input
        ref={cameraInput}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        onChange={chosen}
        data-testid="photo-camera-input"
      />
      <input
        ref={fileInput}
        type="file"
        accept="image/*"
        hidden
        onChange={chosen}
        data-testid="photo-file-input"
      />
      {!coarse && canTake && (
        <WebcamDialog
          open={webcamOpen}
          onOpenChange={setWebcamOpen}
          onPhoto={onPhoto}
          {...(webcamDeps ? { deps: webcamDeps } : {})}
        />
      )}
    </>
  );
}
