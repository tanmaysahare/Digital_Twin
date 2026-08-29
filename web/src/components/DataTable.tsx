'use client';

// The workhorse. UI_COMPONENTS.md 12.
//
// No zebra striping, no card wrapper, no pagination. When rows exceed maxRows
// the table shows the top N and states how many more there are, because a
// supervisor comparing eight stations wants to know there are thirty rather
// than to page through them.
//
// Numeric columns are right-aligned in the mono face with tabular figures. That
// is a legibility requirement rather than a style choice: a column of
// proportional digits cannot be read at a glance and this product is read at a
// glance.

import type { ReactNode } from 'react';

export interface Column<Row> {
  key: string;
  header: string;
  numeric?: boolean;
  width?: string;
  render: (row: Row) => ReactNode;
  sortValue?: (row: Row) => number | string;
}

export function DataTable<Row>({
  columns,
  rows,
  density = 'compact',
  maxRows,
  onRowClick,
  selectedKey,
  rowKey,
  emptyNote,
  caption,
}: {
  columns: Column<Row>[];
  rows: Row[];
  density?: 'compact' | 'regular';
  maxRows?: number;
  onRowClick?: (row: Row) => void;
  selectedKey?: string;
  rowKey: (row: Row) => string;
  emptyNote?: string;
  caption?: string;
}) {
  const height = density === 'compact' ? 'h-[28px]' : 'h-[36px]';
  const shown = maxRows ? rows.slice(0, maxRows) : rows;
  const hidden = rows.length - shown.length;
  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full border-collapse text-body">
        {caption ? (
          <caption className="pb-2 text-left text-small text-ink-3">
            {caption}
          </caption>
        ) : null}
        <thead>
          <tr className="bg-paper-sunk">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                style={column.width ? { width: column.width } : undefined}
                className={`border-b border-rule px-3 py-2 text-label font-medium text-ink-2 ${
                  column.numeric ? 'text-right' : 'text-left'
                }`}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-3 py-3 text-small text-ink-3"
              >
                {emptyNote ?? 'Nothing to show.'}
              </td>
            </tr>
          ) : (
            shown.map((row) => {
              const key = rowKey(row);
              const selected = key === selectedKey;
              return (
                <tr
                  key={key}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onKeyDown={
                    onRowClick
                      ? (event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            onRowClick(row);
                          }
                        }
                      : undefined
                  }
                  tabIndex={onRowClick ? 0 : undefined}
                  className={`${height} border-b border-rule ${
                    onRowClick ? 'cursor-pointer hover:bg-paper-sunk' : ''
                  } ${selected ? 'border-l-2 border-l-accent bg-accent-quiet' : ''}`}
                >
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={`px-3 py-1 align-middle ${
                        column.numeric ? 'numeral text-right' : 'text-left'
                      }`}
                    >
                      {column.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
      {hidden > 0 ? (
        <p className="px-3 py-2 text-small text-ink-3">
          {hidden} more not shown.
        </p>
      ) : null}
    </div>
  );
}
