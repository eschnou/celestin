export type WebcamDeps = {
  /** Opens the camera: rejects when it is refused or there is none. */
  getCamera: () => Promise<MediaStream>;
  /** The picture on screen now, as a JPEG. */
  capture: (video: HTMLVideoElement) => Promise<Blob>;
};

export const browserWebcam: WebcamDeps = {
  getCamera: () =>
    navigator.mediaDevices.getUserMedia({
      // The sheet is read from a good picture: ask for the camera's best, it will give what it has.
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1920 },
        height: { ideal: 1080 },
      },
      audio: false,
    }),
  capture: (video) =>
    new Promise<Blob>((resolve, reject) => {
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d")?.drawImage(video, 0, 0);
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error("no picture"))),
        "image/jpeg",
        0.9,
      );
    }),
};
