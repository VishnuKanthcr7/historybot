// Unit tests for question-aware image selection (no database, no network).
const { selectImages, classifyImageQuestion, imageKind } = await import("../src/services/images.js");

const rows = [
  { id: "tb-akbar", topic: "Akbar", person_name: "Akbar", caption: "Akbar (textbook figure)", file_path: "data/images/akbar-portrait.png", textbook_page_number: 3 },
  { id: "tb-akbar-map", topic: "Akbar's kingdom", person_name: "Akbar", caption: "Akbar's kingdom (textbook map)", file_path: "data/images/akbar-kingdom-map.png", textbook_page_number: 4 },
  { id: "tb-panch", topic: "Panch Mahal", person_name: null, caption: "Panch mahal at Fatehpur Sikri (textbook figure)", file_path: "data/images/panch-mahal.png", textbook_page_number: 6 },
  { id: "tb-maratha-map", topic: "Maratha Kingdom", person_name: "Shivaji", caption: "Maratha Kingdom (textbook map)", file_path: "data/images/maratha-kingdom-map.png", textbook_page_number: 11 },
  { id: "ex-mughal-map", topic: "Mughal Empire under Akbar (1605)", person_name: "Akbar", caption: "Map of the Mughal Empire in 1605, at the end of Akbar's reign (modern map).", file_path: "data/images/commons-mughal-empire-1605-map.jpg", textbook_page_number: null, license: "CC BY-SA 4.0" },
  { id: "ex-buland", topic: "Buland Darwaza, Fatehpur Sikri (built by Akbar)", person_name: "Akbar", caption: "Buland Darwaza, the great gateway of Fatehpur Sikri (modern photograph).", file_path: "data/images/commons-buland-darwaza-fatehpur-sikri.jpg", textbook_page_number: null, license: "CC BY-SA 3.0" },
  { id: "ex-raigad", topic: "Raigad Fort, Shivaji's capital", person_name: "Shivaji", caption: "Raigad Fort in Maharashtra, Shivaji's capital (modern photograph).", file_path: "data/images/commons-raigad-fort.jpg", textbook_page_number: null, license: "CC BY-SA 4.0" },
  { id: "ex-humayun-tomb", topic: "Humayun's Tomb, Delhi", person_name: "Humayun", caption: "Humayun's Tomb in Delhi, a Mughal monument (modern photograph).", file_path: "data/images/commons-humayuns-tomb.jpg", textbook_page_number: null, license: "CC BY-SA 4.0" },
  { id: "ex-akbar-painting", topic: "Akbar (Mughal painting)", person_name: "Akbar", caption: "Mughal painting of Akbar by Govardhan, c. 1630 (artistic depiction).", file_path: "data/images/commons-akbar-govardhan-miniature.jpg", textbook_page_number: null, license: "Public domain" },
  { id: "ex-shivaji-painting", topic: "Shivaji (portrait painting)", person_name: "Shivaji", caption: "Painting of Shivaji, c. 1680s, British Museum (artistic depiction).", file_path: "data/images/commons-shivaji-british-museum.jpg", textbook_page_number: null, license: "Public domain" },
];

let pass = 0;
let fail = 0;
function check(name, ok, detail = "") {
  if (ok) pass += 1; else fail += 1;
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
}
const ids = (q, a, pages) => selectImages(q, a, rows, pages).map((r) => r.id);
const byId = Object.fromEntries(rows.map((r) => [r.id, r]));

check("classify who-was as person", classifyImageQuestion("Who was Akbar?") === "person");
check("classify kingdom as map", classifyImageQuestion("Explain the expansion of the Maratha kingdom") === "map");
check("classify fort as place", classifyImageQuestion("Tell me about Raigad fort") === "place");
check("classify Mansabdari as general", classifyImageQuestion("Explain the Mansabdari system.") === "general");
check("kind: textbook Akbar figure is a portrait", imageKind(byId["tb-akbar"]) === "portrait");
check("kind: maps are maps", imageKind(byId["tb-akbar-map"]) === "map" && imageKind(byId["ex-mughal-map"]) === "map");
check("kind: fort photo is a place", imageKind(byId["ex-raigad"]) === "place");

let r = ids("Who was Akbar?", "Akbar was a Mughal emperor.", [7, 10]);
check("Akbar person: portrait first (textbook figure even when other pages cited)", r[0] === "tb-akbar", r.join(","));
check("Akbar person: one portrait only, second is a map/place", r.length === 2 && !["portrait"].includes(imageKind(byId[r[1]])), r.join(","));

r = ids("Who was Shivaji?", "Shivaji founded the Maratha kingdom.", [11]);
check("Shivaji person: verified painting first", r[0] === "ex-shivaji-painting", r.join(","));
check("Shivaji person: secondary is the Maratha map", r[1] === "tb-maratha-map", r.join(","));

r = ids("Who was Humayun?", "Humayun was defeated and Akbar later became emperor.", [4]);
check("Humayun: never borrows Akbar images", !r.some((id) => /akbar|mughal-map|buland/.test(id)), r.join(","));
check("Humayun: no portrait shown (none verified)", !r.some((id) => imageKind(byId[id]) === "portrait"), r.join(","));

r = ids("Who was Sher Shah Suri?", "Sher Shah Suri defeated Humayun.", [4]);
check("Sher Shah: no images at all", r.length === 0, r.join(","));

r = ids("Show the extent of Akbar's empire on a map", "Akbar's empire covered north India.", [4]);
check("Map question: maps first", r.length >= 1 && r.every((id) => imageKind(byId[id]) === "map"), r.join(","));

r = ids("Tell me about Raigad fort", "Raigad was Shivaji's capital.", []);
check("Fort question: place photo first, no portrait", r[0] === "ex-raigad" && !r.includes("ex-shivaji-painting"), r.join(","));

r = ids("Describe the Panch Mahal", "Panch Mahal is at Fatehpur Sikri.", [20]);
check("Panch Mahal named in question: textbook figure even if page differs", r.includes("tb-panch"), r.join(","));

r = ids("What is the Taj Mahal?", "The Taj Mahal is a marble monument.", [6]);
check("Taj Mahal: no Panch Mahal figure", !r.includes("tb-panch"), r.join(","));

r = ids("Explain Akbar's revenue system.", "Akbar's revenue system measured land.", [30]);
check("Textbook figure on a far page is not shown for a non-person question", !r.includes("tb-akbar") && !r.includes("tb-akbar-map"), r.join(","));

r = ids("Explain the Mansabdari system.", "Mansabdari ranked officials under Akbar.", [7, 10]);
check("General: at most 2 images, at most one portrait", r.length <= 2 && r.filter((id) => imageKind(byId[id]) === "portrait").length <= 1, r.join(","));

check("No portrait is captioned as a map/place", rows.filter((x) => imageKind(x) !== "portrait").every((x) => !/portrait|painting|depiction/i.test(x.caption)));

console.log(`image_selection ${pass}/${pass + fail} PASS`);
process.exit(fail ? 1 : 0);
