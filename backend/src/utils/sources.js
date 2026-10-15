export function publicSources(items) {
  return (items || [])
    .filter((item) => item && (item.textbook_page_number != null || item.printed_page_number != null))
    .map((item) => ({
      textbook_page_number: item.textbook_page_number ?? item.printed_page_number ?? null,
      printed_page_number: item.printed_page_number ?? item.textbook_page_number ?? null,
      citation_label: item.citation_label || undefined,
      authority: item.authority || undefined,
      source_type: item.source_type || undefined,
      // Shown to students under "Sources": chapter and a short quote of the retrieved passage.
      chapter: typeof item.chapter === "string" ? item.chapter.slice(0, 40) : undefined,
      excerpt: typeof item.excerpt === "string" && item.excerpt.trim() ? item.excerpt.trim().slice(0, 300) : undefined,
    }));
}
