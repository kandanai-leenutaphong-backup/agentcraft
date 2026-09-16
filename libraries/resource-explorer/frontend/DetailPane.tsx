import { RowsTable } from "./RowsTable.js";
import { StatusNote } from "./StatusNote.js";
import {
  LOADING_LABEL,
  coordinateLabel,
  detailValueText,
  metricLabel,
  SOURCE_TYPE_LABEL,
} from "./status.js";
import type { ContentResponse, ResourceResponse, TreeNode } from "./wire.js";

/**
 * One source's pane: what it is, what was measured just now, and a preview.
 *
 * ADAPTED from `resource_explorer/frontend/src/components/DetailPane.tsx`. See
 * PROVENANCE.md. Tailwind classes become scoped ones; the ARM-properties and
 * blob-rendering sections are dropped; the connector identity, the capability
 * list, the configuration keys and the provenance line are added.
 *
 * Every number on this pane came back from the call whose timestamp is at the
 * bottom of it. Nothing is carried over from a previous read or a document.
 */

export interface DetailPaneProps {
  node: TreeNode | null;
  resource: ResourceResponse | null;
  content: ContentResponse | null;
  resourceLoading: boolean;
  contentLoading: boolean;
  resourceFailure: string | null;
  contentFailure: string | null;
  onRetryResource: () => void;
  onRetryContent: () => void;
  onLoadContent: () => void;
  /** The use case this node hangs under. Two use cases may name a slot alike. */
  useCase: string;
}

/**
 * The pane's own heading, carried into every branch below.
 *
 * Both use cases declare a slot called "Retrieval index". Without the owner on
 * the pane, the two are indistinguishable to anyone reading it away from the
 * tree — by keyboard, or with the tree scrolled off a narrow screen.
 */
function Head({ node, useCase }: { node: TreeNode; useCase: string }) {
  const eyebrow =
    node.kind === "source"
      ? node.sourceType
        ? SOURCE_TYPE_LABEL[node.sourceType]
        : "Source"
      : "Use case";
  return (
    <header className="inv-detail-head">
      <span className="inv-eyebrow">{eyebrow}</span>
      <h2>{node.label}</h2>
      {node.kind === "source" && useCase ? (
        <p className="inv-breadcrumb">
          Use case: <b>{useCase}</b>
        </p>
      ) : null}
    </header>
  );
}

/** What a screen reader hears when it lands on the pane rather than the tree. */
function paneName(node: TreeNode, useCase: string): string {
  return node.kind === "source" && useCase ? `${node.label}, ${useCase}` : node.label;
}

function Coordinates({ resource }: { resource: ResourceResponse }) {
  const entries = Object.entries(resource.coordinates);
  if (entries.length === 0) return null;
  return (
    <dl className="inv-kv">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt>{coordinateLabel(key)}</dt>
          <dd>{detailValueText(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function Metrics({ resource }: { resource: ResourceResponse }) {
  const entries = Object.entries(resource.metrics);
  if (entries.length === 0) {
    return (
      <p className="inv-muted">
        No count was returned by this call. An absent measurement is left absent
        rather than shown as zero.
      </p>
    );
  }
  return (
    <div className="inv-metrics">
      {entries.map(([key, value]) => (
        <div key={key}>
          <b>{detailValueText(value)}</b>
          <span>{metricLabel(key)}</span>
        </div>
      ))}
    </div>
  );
}

export function DetailPane({
  node,
  resource,
  content,
  resourceLoading,
  contentLoading,
  resourceFailure,
  contentFailure,
  onRetryResource,
  onRetryContent,
  onLoadContent,
  useCase,
}: DetailPaneProps) {
  if (node === null) {
    return (
      <div className="inv-detail inv-detail-empty">
        <b>Pick a source</b>
        <p>
          Expand a use case in the tree and select one of its sources to read its
          live metadata and a bounded preview.
        </p>
      </div>
    );
  }

  if (node.kind !== "source") {
    const summary = node.detail?.summary;
    return (
      <section className="inv-detail" aria-label={paneName(node, useCase)}>
        <Head node={node} useCase={useCase} />
        {typeof summary === "string" && summary ? <p>{summary}</p> : null}
        <p className="inv-muted">
          Select one of its sources to read metadata and preview its contents.
        </p>
      </section>
    );
  }

  if (node.enabled === false) {
    return (
      <section className="inv-detail" aria-label={paneName(node, useCase)}>
        <Head node={node} useCase={useCase} />
        <p className="inv-notice" data-state="disabled">
          Switched off for this browser session. No metadata or preview is read
          while it is off, and the server refuses the call rather than trusting
          this page to skip it. Turn it back on with the switch beside it in the
          tree, or press <kbd>t</kbd> with the row focused.
        </p>
      </section>
    );
  }

  if (!node.configured) {
    return (
      <section className="inv-detail" aria-label={paneName(node, useCase)}>
        <Head node={node} useCase={useCase} />
        <StatusNote status="unconfigured" cause={node.error} />
        <p className="inv-muted">
          Nothing was probed. This slot is declared and has no coordinates, which
          is a report about the deployment rather than a failed call.
        </p>
      </section>
    );
  }

  return (
    <section className="inv-detail" aria-label={paneName(node, useCase)}>
      <Head node={node} useCase={useCase} />

      {resourceFailure !== null ? (
        <StatusNote
          status="unavailable"
          cause={resourceFailure}
          onRetry={onRetryResource}
          retrying={resourceLoading}
        />
      ) : null}

      {resourceLoading && resource === null ? (
        <p className="inv-muted" role="status">
          {LOADING_LABEL}
        </p>
      ) : null}

      {resource !== null ? (
        <>
          {resource.holds ? <p>{resource.holds}</p> : null}

          {resource.status !== "ok" ? (
            <StatusNote
              status={resource.status}
              cause={resource.error}
              onRetry={onRetryResource}
              retrying={resourceLoading}
            />
          ) : null}

          <section className="inv-section" aria-label="Measured now">
            <h3>Measured now</h3>
            <Metrics resource={resource} />
          </section>

          <section className="inv-section" aria-label="Coordinates">
            <h3>Coordinates</h3>
            <Coordinates resource={resource} />
          </section>

          <section className="inv-section" aria-label="Connector">
            <h3>Connector</h3>
            <dl className="inv-kv">
              <div>
                <dt>Name</dt>
                <dd>{resource.connector.name}</dd>
              </div>
              <div>
                <dt>Id</dt>
                <dd>{resource.connector.id}</dd>
              </div>
              {resource.connector.reachedBy ? (
                <div>
                  <dt>Reached by</dt>
                  <dd>
                    <code>{resource.connector.reachedBy}</code>
                  </dd>
                </div>
              ) : null}
            </dl>
            {resource.capabilities.length > 0 ? (
              <p className="inv-chips">
                {resource.capabilities.map((capability) => (
                  <span key={capability} className="inv-tag">
                    {capability}
                  </span>
                ))}
              </p>
            ) : null}
            {resource.settings.length > 0 ? (
              <p className="inv-muted">
                Configured by: {resource.settings.join(", ")}
              </p>
            ) : null}
          </section>

          {resource.schemaFields !== null && resource.schemaFields.length > 0 ? (
            <section className="inv-section" aria-label="Schema">
              <h3>Schema ({resource.schemaFields.length})</h3>
              <div className="inv-schema">
                {resource.schemaFields.map((field) => (
                  <span key={field.name}>
                    <b>{field.name}</b>
                    <i>{field.type}</i>
                  </span>
                ))}
              </div>
            </section>
          ) : null}

          <p className="inv-provenance">{resource.provenance}</p>
          <p className="inv-observed">Read at {resource.observedAt}</p>
        </>
      ) : null}

      <section className="inv-section" aria-label="Preview">
        <h3>Preview</h3>
        {!node.hasContent ? <p className="inv-muted">Metadata only. Row access is not authorized.</p> : <>
        {contentFailure !== null ? (
          <StatusNote
            status="unavailable"
            cause={contentFailure}
            onRetry={onRetryContent}
            retrying={contentLoading}
          />
        ) : null}
        {contentLoading ? (
          <p className="inv-muted" role="status">
            {LOADING_LABEL}
          </p>
        ) : null}
        {content === null && !contentLoading && contentFailure === null ? (
          <button type="button" className="inv-button" onClick={onLoadContent}>
            Preview contents
          </button>
        ) : null}
        {content !== null && content.rows !== null && content.rows.length > 0 ? (
          <>
            <RowsTable
              rows={content.rows}
              columns={content.columns}
              rowLimit={content.rowLimit}
              sampleOf={content.sampleOf}
              truncated={content.truncated}
              notes={content.sampleNotes}
              caption={`Bounded preview of ${node.label}`}
            />
            <p className="inv-provenance">{content.provenance}</p>
            <p className="inv-observed">Read at {content.observedAt}</p>
          </>
        ) : null}
        {content !== null && (content.rows === null || content.rows.length === 0) ? (
          <StatusNote
            status={content.status}
            cause={content.error}
            onRetry={onRetryContent}
            retrying={contentLoading}
          />
        ) : null}
        </>}
      </section>
    </section>
  );
}
