import fs from "node:fs";
import path from "node:path";
import { getVerifiedImageRow, resolveImagePath } from "../services/images.js";

const MEDIA_TYPES = {
  ".png": "image/png",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
};

export async function getImage(req, res, next) {
  try {
    const row = await getVerifiedImageRow(req.params.imageId);
    const filePath = resolveImagePath(row.file_path);
    if (!fs.existsSync(filePath)) {
      res.status(404).json({ error: { code: "NOT_FOUND", message: "Image not found." } });
      return;
    }
    const type = MEDIA_TYPES[path.extname(filePath).toLowerCase()] || "application/octet-stream";
    res.setHeader("Content-Type", type);
    res.setHeader("Cache-Control", "private, no-store");
    fs.createReadStream(filePath).pipe(res);
  } catch (err) {
    next(err);
  }
}
