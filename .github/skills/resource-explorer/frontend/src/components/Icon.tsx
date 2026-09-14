/**
 * One glyph per node family, drawn rather than imported: eighteen shapes cover
 * the twenty-one kinds, and the kind word travels with every row's accessible
 * name so the glyph never has to carry the meaning alone.
 */

import type { JSX } from "react";

import type { IconName } from "../api/kinds";

const PATHS: Record<IconName, JSX.Element> = {
  subscription: (
    <>
      <rect x="2" y="3" width="12" height="10" rx="1.5" />
      <path d="M2 6.4h12" />
      <circle cx="4.1" cy="4.7" r="0.55" fill="currentColor" stroke="none" />
    </>
  ),
  group: <path d="M2 12.4V4.4a1 1 0 0 1 1-1h3.2l1.3 1.6H13a1 1 0 0 1 1 1v6.4a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1Z" />,
  type: (
    <>
      <path d="M8 2.4 14 5.4 8 8.4 2 5.4 8 2.4Z" />
      <path d="M2.6 8.1 8 10.8l5.4-2.7" />
      <path d="M2.6 10.9 8 13.6l5.4-2.7" />
    </>
  ),
  resource: (
    <>
      <path d="M8 2.2 13.6 5v6L8 13.8 2.4 11V5L8 2.2Z" />
      <path d="M2.6 5.1 8 7.9l5.4-2.8M8 7.9v5.7" />
    </>
  ),
  collection: (
    <>
      <path d="M6.2 3H4.4A1.2 1.2 0 0 0 3.2 4.2v7.6A1.2 1.2 0 0 0 4.4 13h1.8" />
      <path d="M9.8 3h1.8a1.2 1.2 0 0 1 1.2 1.2v7.6A1.2 1.2 0 0 1 11.6 13H9.8" />
    </>
  ),
  child: (
    <>
      <path d="M4 2.8v6.4A1.8 1.8 0 0 0 5.8 11H12" />
      <path d="m9.8 8.8 2.4 2.2-2.4 2.2" />
    </>
  ),
  properties: (
    <>
      <path d="M4.2 2.5h4.6L12 5.9v7.6H4.2Z" />
      <path d="M8.8 2.5v3.4H12" />
      <path d="M6 9h4M6 11h2.8" />
    </>
  ),
  bucket: (
    <>
      <path d="M2.8 4.8h10.4l-1.1 7.9a1 1 0 0 1-1 .8H4.9a1 1 0 0 1-1-.8L2.8 4.8Z" />
      <path d="M2.2 4.8h11.6M6.4 7.4v3.4M9.6 7.4v3.4" />
    </>
  ),
  folder: (
    <>
      <path d="M2 12.4V4.6a1 1 0 0 1 1-1h3l1.3 1.6H12a1 1 0 0 1 1 1v1" />
      <path d="m2 12.4 1.7-5a1 1 0 0 1 1-.7h9.2l-1.8 5a1 1 0 0 1-1 .7H2Z" />
    </>
  ),
  file: (
    <>
      <path d="M4.2 2.5h4.6L12 5.9v7.6H4.2Z" />
      <path d="M8.8 2.5v3.4H12" />
    </>
  ),
  database: (
    <>
      <ellipse cx="8" cy="4.2" rx="5" ry="1.9" />
      <path d="M3 4.2v7.6c0 1 2.2 1.9 5 1.9s5-.9 5-1.9V4.2" />
      <path d="M13 8c0 1-2.2 1.9-5 1.9S3 9 3 8" />
    </>
  ),
  table: (
    <>
      <rect x="2.5" y="3" width="11" height="10" rx="1" />
      <path d="M2.5 6.4h11M6.6 6.4V13" />
    </>
  ),
  graph: (
    <>
      <circle cx="4" cy="11.4" r="1.7" />
      <circle cx="12" cy="11.4" r="1.7" />
      <circle cx="8" cy="4" r="1.7" />
      <path d="M6.7 5.3 5 9.8M9.3 5.3 11 9.8M5.7 11.4h4.6" />
    </>
  ),
  index: (
    <>
      <circle cx="6.9" cy="6.9" r="3.6" />
      <path d="m9.6 9.6 3.2 3.2" />
      <path d="M5.3 6.1h3.2M5.3 7.9h2.2" />
    </>
  ),
  field: (
    <>
      <rect x="2.4" y="4.8" width="11.2" height="6.4" rx="1.4" />
      <path d="M5.2 8h5.6" />
    </>
  ),
  logs: (
    <>
      <rect x="2.6" y="2.8" width="10.8" height="10.4" rx="1.2" />
      <path d="M5.1 6h5.8M5.1 8.3h5.8M5.1 10.6h3.4" />
    </>
  ),
  repository: (
    <>
      <rect x="2.6" y="8.6" width="10.8" height="4.5" rx="1" />
      <rect x="4.2" y="4.6" width="7.6" height="3.2" rx="1" />
      <rect x="5.6" y="1.9" width="4.8" height="1.9" rx="0.8" />
    </>
  ),
  tag: (
    <>
      <path d="M2.6 7.6V3.7a1 1 0 0 1 1-1h3.9l5.9 5.9-4.9 4.9-5.9-5.9Z" />
      <circle cx="5.4" cy="5.5" r="0.9" />
    </>
  ),
};

export interface IconProps {
  name: IconName;
  className?: string;
}

export function Icon({ name, className }: IconProps): JSX.Element {
  return (
    <svg
      viewBox="0 0 16 16"
      width="16"
      height="16"
      aria-hidden="true"
      focusable="false"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className ?? "h-4 w-4 shrink-0"}
    >
      {PATHS[name]}
    </svg>
  );
}
