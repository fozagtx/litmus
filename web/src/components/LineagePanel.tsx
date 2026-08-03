import { useState } from 'react';
import { Link } from 'react-router-dom';
import { IconChevronRight } from '@tabler/icons-react';
import { firstWords } from '../lib/format';
import type { AssetSummary, Lineage, LineageNode } from '../lib/types';
import { Card } from './ui';
import { HashChip } from './HashChip';

interface NormalNode {
  asset_id: string;
  prompt?: string;
}

function normalize(node: LineageNode): NormalNode {
  return typeof node === 'string' ? { asset_id: node } : node;
}

function NodeRow({
  node,
  depth,
  label,
  self = false,
}: {
  node: NormalNode;
  depth: number;
  label: string;
  self?: boolean;
}) {
  const body = (
    <span className="flex min-w-0 items-center gap-2">
      <span className="w-16 shrink-0 text-13 text-ink-2">{label}</span>
      <HashChip value={node.asset_id} head={10} tail={4} />
      {node.prompt && (
        <span className="truncate text-13 text-ink-2">{firstWords(node.prompt)}</span>
      )}
    </span>
  );
  return (
    <div className="py-1" style={{ paddingLeft: `${depth * 16}px` }}>
      {self ? (
        <span className="flex min-w-0 items-center gap-2 text-15 font-medium">{body}</span>
      ) : (
        <Link
          to={`/asset/${node.asset_id}`}
          className="flex min-w-0 items-center gap-2 text-15 transition-colors duration-150 ease-out hover:text-ink"
        >
          {body}
        </Link>
      )}
    </div>
  );
}

/** Lineage as an indented tree: parents above, discarded collapsed below. */
export function LineagePanel({
  lineage,
  current,
}: {
  lineage: Lineage;
  current: AssetSummary;
}) {
  const [showDiscarded, setShowDiscarded] = useState(false);
  const parents = (lineage?.parents ?? []).map(normalize);
  const children = (lineage?.children ?? []).map(normalize);
  const discarded = (lineage?.discarded ?? []).map(normalize);
  const selfDepth = parents.length > 0 ? 1 : 0;
  const empty = parents.length === 0 && children.length === 0 && discarded.length === 0;

  return (
    <Card className="p-5">
      <h2 className="font-display text-22 text-ink">Lineage</h2>
      <div className="mt-4">
        {parents.map((node) => (
          <NodeRow key={node.asset_id} node={node} depth={0} label="Parent" />
        ))}
        <NodeRow
          node={{ asset_id: current.asset_id, prompt: current.prompt }}
          depth={selfDepth}
          label="This asset"
          self
        />
        {children.map((node) => (
          <NodeRow key={node.asset_id} node={node} depth={selfDepth + 1} label="Child" />
        ))}
        {discarded.length > 0 && (
          <div className="pt-2" style={{ paddingLeft: `${selfDepth * 16}px` }}>
            <button
              type="button"
              onClick={() => setShowDiscarded((v) => !v)}
              aria-expanded={showDiscarded}
              className="flex items-center gap-1 text-13 text-ink-2 transition-colors duration-150 ease-out hover:text-ink"
            >
              <IconChevronRight
                size={14}
                stroke={1.75}
                aria-hidden
                className={`transition-transform duration-150 ease-out ${
                  showDiscarded ? 'rotate-90' : ''
                }`}
              />
              Discarded candidates ({discarded.length}), kept for the record
            </button>
            {showDiscarded && (
              <div className="fade-in mt-1">
                {discarded.map((node) => (
                  <NodeRow
                    key={node.asset_id}
                    node={node}
                    depth={1}
                    label="Discarded"
                  />
                ))}
              </div>
            )}
          </div>
        )}
        {empty && (
          <p className="text-13 text-ink-2">
            No parents or derivatives. This asset is the start of its line.
          </p>
        )}
      </div>
    </Card>
  );
}
