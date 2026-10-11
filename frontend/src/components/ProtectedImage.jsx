import { useEffect, useState } from "react";
import { fetchProtectedImage } from "../services/api.js";

export default function ProtectedImage({ id, alt, className, onFail }) {
  const [src, setSrc] = useState("");

  useEffect(() => {
    if (!id) return undefined;
    let cancelled = false;
    let objectUrl = "";
    fetchProtectedImage(id)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => {
        if (!cancelled) {
          setSrc("");
          if (onFail) onFail();
        }
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setSrc("");
    };
    // onFail is a stable callback from the figure; the image reloads only when the id changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (!src) return null;
  return (
    <img
      src={src}
      alt={alt || ""}
      className={className}
      loading="lazy"
      onError={() => {
        setSrc("");
        if (onFail) onFail();
      }}
    />
  );
}

// One image with its caption and credit. A missing or failed image hides the whole figure
// (caption included) so the answer never shows an empty box.
export function ImageFigure({ img, pageLabel, className = "max-h-52 w-full object-contain", children }) {
  const [failed, setFailed] = useState(false);
  if (!img?.id || failed) return null;
  const credit = [img.source, img.license].filter(Boolean).join(" · ");
  return (
    <figure className="mt-3 overflow-hidden rounded-xl border border-rule bg-paper p-2">
      {children}
      <ProtectedImage id={img.id} alt={img.alt} className={className} onFail={() => setFailed(true)} />
      <figcaption className="mt-1 text-xs text-muted">
        <span className="font-medium text-ink">{img.title}</span>
        {img.textbook_page_number ? ` · ${pageLabel || "Textbook page"} ${img.textbook_page_number}` : ""}
        {credit ? <span className="mt-1 block break-words">{credit}</span> : null}
      </figcaption>
    </figure>
  );
}
