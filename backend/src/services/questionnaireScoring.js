// Likert questionnaire scoring. Pure functions; no database.
// Missing data: an unanswered item is null, never zero. A subscale score is the mean of the ANSWERED items
// (after reverse-scoring) and is reported only when at least minRatio of that subscale's items were answered;
// otherwise it is null ("insufficient responses"). No cutoffs or interpretation bands are applied.

export const PLACEHOLDER_TAG = "[REQUIRES RESEARCHER APPROVAL]";

export function validValue(value, scaleMin, scaleMax) {
  return Number.isInteger(value) && value >= scaleMin && value <= scaleMax;
}

export function reverse(value, scaleMin, scaleMax) {
  return scaleMin + scaleMax - value;
}

// items: [{ id, subscale, reverse_scored }], values: { [itemId]: number|null }
export function scoreQuestionnaire(items, values, { scaleMin, scaleMax, minRatio = 0.5 }) {
  const subscales = new Map();
  let answered = 0;
  for (const item of items) {
    const raw = values?.[item.id];
    const ok = validValue(raw, scaleMin, scaleMax);
    const entry = subscales.get(item.subscale) || { subscale: item.subscale, items: 0, answered: 0, sum: 0 };
    entry.items += 1;
    if (ok) {
      answered += 1;
      entry.answered += 1;
      entry.sum += item.reverse_scored ? reverse(raw, scaleMin, scaleMax) : raw;
    }
    subscales.set(item.subscale, entry);
  }
  return {
    answered,
    total: items.length,
    missing: items.length - answered,
    completion: items.length ? Math.round((answered / items.length) * 1000) / 1000 : 0,
    subscales: [...subscales.values()].map((e) => ({
      subscale: e.subscale,
      items: e.items,
      answered: e.answered,
      score: e.answered > 0 && e.answered / e.items >= minRatio ? Math.round((e.sum / e.answered) * 100) / 100 : null,
    })),
  };
}

// Why an instrument cannot be published yet (null when it can).
export function publishProblem(instrument, items) {
  if (!items.length) return "Add at least one item.";
  if (items.some((i) => i.requires_approval || String(i.text).includes(PLACEHOLDER_TAG))) {
    return "Replace every placeholder item marked 'REQUIRES RESEARCHER APPROVAL' with an approved item first.";
  }
  if (!instrument.approval_note || String(instrument.approval_note).trim().length < 10) {
    return "Enter the approval note: who approved these items and their source.";
  }
  if (instrument.phase === "post" && !instrument.pre_instrument_id) return "Link this post-questionnaire to its pre-questionnaire.";
  return null;
}
