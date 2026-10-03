import fs from "node:fs";
import { getVerifiedImageRow, resolveImagePath } from "../services/images.js";

export async function getImage(req, res, next) {
  try {
    const row = await getVerifiedImageRow(req.params.imageId);
    const filePath = resolveImagePath(row.file_path);
    if (!fs.existsSync(filePath)) {
      res.status(404).json({ error: { code: "NOT_FOUND", message: "Image not found." } });
      return;
    }
    res.setHeader("Content-Type", "image/png");
    res.setHeader("Cache-Control", "public, max-age=86400");
    fs.createReadStream(filePath).pipe(res);
  } catch (err) {
    next(err);
  }
}
