/**
 * Fixes malformed markdown tables that are missing the separator row.
 *
 * GFM tables require a separator row after the header:
 *   | Header 1 | Header 2 |
 *   |----------|----------|   <-- this row is required
 *   | Cell 1   | Cell 2   |
 *
 * Some AI models generate tables without the separator row.
 * This function detects such cases and inserts the missing row.
 */
export function fixMalformedTables(markdown: string): string {
  const lines = markdown.split('\n')
  const result: string[] = []

  for (let i = 0; i < lines.length; i++) {
    const currentLine = lines[i].trim()
    const nextLine = lines[i + 1]?.trim() ?? ''

    result.push(lines[i])

    // Check if current line looks like a table header (starts and ends with |)
    // and next line looks like a table row (also starts/ends with |) but NOT a separator row
    if (
      isTableHeaderRow(currentLine) &&
      isTableRow(nextLine) &&
      !isSeparatorRow(nextLine)
    ) {
      // Count columns from the header
      const columnCount = countColumns(currentLine)
      // Insert separator row
      result.push(createSeparatorRow(columnCount))
    }
  }

  return result.join('\n')
}

/**
 * Checks if a line looks like a table header row.
 * A header row starts and ends with | and has at least one | in between.
 */
function isTableHeaderRow(line: string): boolean {
  const trimmed = line.trim()
  return trimmed.startsWith('|') && trimmed.endsWith('|') && trimmed.split('|').length >= 3
}

/**
 * Checks if a line looks like a table data row.
 * Similar to header but we only check the pipe format.
 */
function isTableRow(line: string): boolean {
  if (!line) return false
  const trimmed = line.trim()
  return trimmed.startsWith('|') && trimmed.endsWith('|') && trimmed.split('|').length >= 3
}

/**
 * Checks if a line is a GFM separator row like |---|---| or |-|-|
 * Separator rows contain only |, -, :, and whitespace.
 */
function isSeparatorRow(line: string): boolean {
  const trimmed = line.trim()
  if (!trimmed.startsWith('|') || !trimmed.endsWith('|')) return false

  // Remove the outer pipes and check if content is only separators
  const inner = trimmed.slice(1, -1)
  const cells = inner.split('|')

  return cells.every((cell) => /^[\s:-]*$/.test(cell))
}

/**
 * Counts the number of columns in a table row.
 */
function countColumns(line: string): number {
  // Number of columns = number of | separators - 1 (since | wraps the row)
  // e.g., | A | B | C | has 4 pipes and 3 columns
  return (line.match(/\|/g) ?? []).length - 1
}

/**
 * Creates a GFM separator row for the given number of columns.
 * e.g., 3 columns -> |---|---|---|
 */
function createSeparatorRow(columnCount: number): string {
  return '|' + '---|'.repeat(columnCount)
}
