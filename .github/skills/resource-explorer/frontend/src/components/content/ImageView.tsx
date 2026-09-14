/**
 * The image itself, from the bytes the server returned.
 *
 * Unframed and at natural size, per the house rule that media is never framed
 * and never re-cropped. The `data:` URL is built only after `imageDataUrl`
 * agrees the media type is a bitmap — an SVG would execute in this origin, so
 * it never reaches here.
 */

import { useState, type JSX } from "react";

import { imageDataUrl } from "../../api/render";

export interface ImageViewProps {
  mediaType: string;
  dataBase64: string | null;
  label: string;
}

export function ImageView({ mediaType, dataBase64, label }: ImageViewProps): JSX.Element {
  const [natural, setNatural] = useState<{ width: number; height: number } | null>(null);
  const source = imageDataUrl(mediaType, dataBase64);

  if (source === null) {
    return (
      <p
        data-testid="image-refused"
        className="rounded border border-warning bg-warning-tint px-3 py-2 text-sm text-warning"
      >
        These bytes are typed {mediaType}, which this viewer will not render as an image.
        Scriptable formats are never drawn inside this page.
      </p>
    );
  }

  return (
    <figure className="min-w-0">
      <img
        data-testid="content-image"
        src={source}
        alt={`Contents of ${label}`}
        onLoad={(event) =>
          setNatural({
            width: event.currentTarget.naturalWidth,
            height: event.currentTarget.naturalHeight,
          })
        }
        className="max-w-full"
      />
      <figcaption className="mt-2 text-xs text-muted">
        {mediaType}
        {natural === null
          ? ""
          : ` · ${String(natural.width)} × ${String(natural.height)} pixels, shown at natural size`}
      </figcaption>
    </figure>
  );
}
