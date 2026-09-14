/**
 * Delimited text, parsed into the same row shape a `rows` payload arrives in,
 * so one table renders both.
 *
 * RFC 4180 quoting, because a CSV cell that legitimately contains a comma or a
 * newline is the exact case a naive split gets wrong and then hides.
 */

export interface Delimited {
  columns: string[];
  rows: Record<string, string>[];
}

export function delimiterFor(mediaType: string, sample: string): string {
  if (mediaType.includes("tab-separated")) return "\t";
  const firstLine = sample.split(/\r?\n/, 1)[0] ?? "";
  const candidates: [string, number][] = [
    [",", (firstLine.match(/,/g) ?? []).length],
    ["\t", (firstLine.match(/\t/g) ?? []).length],
    [";", (firstLine.match(/;/g) ?? []).length],
  ];
  candidates.sort((left, right) => right[1] - left[1]);
  const best = candidates[0];
  return best && best[1] > 0 ? best[0] : ",";
}

/** One pass, character by character: quotes are stateful and cannot be split. */
export function parseDelimited(text: string, delimiter: string): string[][] {
  const records: string[][] = [];
  let record: string[] = [];
  let field = "";
  let quoted = false;
  let index = 0;

  const endField = (): void => {
    record.push(field);
    field = "";
  };
  const endRecord = (): void => {
    endField();
    records.push(record);
    record = [];
  };

  while (index < text.length) {
    const char = text[index] as string;
    if (quoted) {
      if (char === '"') {
        if (text[index + 1] === '"') {
          field += '"';
          index += 2;
          continue;
        }
        quoted = false;
        index += 1;
        continue;
      }
      field += char;
      index += 1;
      continue;
    }
    if (char === '"' && field === "") {
      quoted = true;
      index += 1;
      continue;
    }
    if (char === delimiter) {
      endField();
      index += 1;
      continue;
    }
    if (char === "\r") {
      index += 1;
      continue;
    }
    if (char === "\n") {
      endRecord();
      index += 1;
      continue;
    }
    field += char;
    index += 1;
  }
  if (field !== "" || record.length > 0) endRecord();
  return records;
}

/** A header row with a duplicate or blank name still has to address its column. */
function uniqueColumns(header: string[]): string[] {
  const seen = new Map<string, number>();
  return header.map((name, index) => {
    const base = name.trim() === "" ? `column ${String(index + 1)}` : name.trim();
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    return count === 0 ? base : `${base} (${String(count + 1)})`;
  });
}

export function toDelimitedTable(text: string, mediaType: string): Delimited {
  const delimiter = delimiterFor(mediaType, text);
  const records = parseDelimited(text, delimiter).filter(
    (record) => !(record.length === 1 && record[0] === ""),
  );
  const header = records[0];
  if (header === undefined) return { columns: [], rows: [] };
  const columns = uniqueColumns(header);
  const rows = records.slice(1).map((record) => {
    const row: Record<string, string> = {};
    columns.forEach((column, index) => {
      row[column] = record[index] ?? "";
    });
    return row;
  });
  return { columns, rows };
}
