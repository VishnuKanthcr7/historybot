export function publicSources(items) {
  return (items || [])
    .filter((item) => item && (item.textbook_page_number != null || item.printed_page_number != null))
    .map((item) => ({
      textbook_page_number: item.textbook_page_number ?? item.printed_page_number ?? null,
      printed_page_number: item.printed_page_number ?? item.textbook_page_number ?? null,
      citation_label: item.citation_label || undefined,
      authority: item.authority || undefined,
      source_type: item.source_type || undefined,
    }));
}
