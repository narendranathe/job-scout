/**
 * ChipCloud — a multi-select chip picker with optional free-text input.
 *
 * Used by the OnboardingWizard for roles, companies, and locations
 * (Steps 2/3/4). Keeps the markup compact and the styling consistent
 * across the three pickers.
 *
 * Props:
 *   options:        Array<{value: string, label: string, sublabel?: string,
 *                          group?: string}>
 *   selected:       Set<string> or Array<string> of currently-selected values
 *   onToggle(value): called when a chip is clicked
 *   onAdd(value):   called when the free-text input submits (Enter)
 *                   — omit to disable the input
 *   onRemove(value):called when a "custom" chip's X is clicked
 *                   — only used for chips not in ``options`` (free-text)
 *   t:              theme tokens (TH[mode])
 *   placeholder:    free-text input placeholder
 *   emptyHint:      shown when options is empty
 *   maxHeight:      override the picker's max-height (default 320px)
 *
 * Behaviour notes:
 *   - Options are auto-grouped by their .group field when set. Order
 *     within a group follows the input array.
 *   - Free-text values that already exist as an option toggle the
 *     option's chip; values not in options become "tracked" chips
 *     with a remove (X) affordance.
 */
import { useMemo, useState } from "react";

export function ChipCloud({
  options = [],
  selected = [],
  onToggle,
  onAdd,
  onRemove,
  t,
  placeholder = "Type to add…",
  emptyHint = "",
  maxHeight = 320,
  searchable = false,
}) {
  const selectedSet = useMemo(
    () => (selected instanceof Set ? selected : new Set(selected)),
    [selected]
  );
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");

  // Split options into the known set and the free-text additions that
  // came in via onAdd. Free-text chips are anything in `selected` that
  // doesn't appear in `options` — they get the X affordance.
  const optionValues = useMemo(() => new Set(options.map((o) => o.value)), [options]);
  const freeText = useMemo(
    () => [...selectedSet].filter((v) => !optionValues.has(v)),
    [selectedSet, optionValues]
  );

  const filteredOptions = useMemo(() => {
    if (!query.trim()) return options;
    const q = query.trim().toLowerCase();
    return options.filter(
      (o) =>
        (o.label || "").toLowerCase().includes(q) ||
        (o.value || "").toLowerCase().includes(q) ||
        (o.sublabel || "").toLowerCase().includes(q)
    );
  }, [options, query]);

  const grouped = useMemo(() => {
    const map = new Map();
    for (const o of filteredOptions) {
      const g = o.group || "";
      if (!map.has(g)) map.set(g, []);
      map.get(g).push(o);
    }
    return [...map.entries()];
  }, [filteredOptions]);

  const handleAdd = (e) => {
    if (e?.preventDefault) e.preventDefault();
    const v = text.trim();
    if (!v) return;
    if (onAdd) onAdd(v);
    setText("");
  };

  const chipBase = (selected) => ({
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 12px",
    borderRadius: 16,
    border: `1px solid ${selected ? t.ac : t.bd}`,
    background: selected ? t.ac : t.bgS,
    color: selected ? "#fff" : t.tx,
    fontSize: 13,
    fontWeight: 500,
    cursor: "pointer",
    transition: "all .12s",
    whiteSpace: "nowrap",
  });

  return (
    <div>
      {(searchable || onAdd) && (
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          {searchable && (
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search…"
              style={{
                flex: 1,
                padding: "8px 12px",
                borderRadius: 8,
                border: `1px solid ${t.bd}`,
                background: t.bgS,
                color: t.tx,
                fontSize: 14,
                fontFamily: "inherit",
              }}
            />
          )}
          {onAdd && (
            <form
              onSubmit={handleAdd}
              style={{ display: "flex", gap: 8, flex: searchable ? "0 0 auto" : 1 }}
            >
              <input
                type="text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={placeholder}
                style={{
                  flex: 1,
                  minWidth: 180,
                  padding: "8px 12px",
                  borderRadius: 8,
                  border: `1px solid ${t.bd}`,
                  background: t.bgS,
                  color: t.tx,
                  fontSize: 14,
                  fontFamily: "inherit",
                }}
              />
              <button
                type="submit"
                style={{
                  padding: "8px 14px",
                  borderRadius: 8,
                  border: `1px solid ${t.bd}`,
                  background: t.cd,
                  color: t.tx,
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Add
              </button>
            </form>
          )}
        </div>
      )}

      <div
        style={{
          maxHeight,
          overflowY: "auto",
          padding: 12,
          borderRadius: 10,
          border: `1px solid ${t.bd}`,
          background: t.bgS,
        }}
      >
        {grouped.length === 0 && filteredOptions.length === 0 && (
          <div style={{ color: t.txM, fontSize: 13, padding: "16px 4px" }}>
            {query ? `No matches for "${query}"` : emptyHint}
          </div>
        )}

        {grouped.map(([groupName, opts]) => (
          <div key={groupName || "_"} style={{ marginBottom: 12 }}>
            {groupName && (
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: ".06em",
                  color: t.txM,
                  marginBottom: 6,
                }}
              >
                {groupName}
              </div>
            )}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {opts.map((o) => {
                const isSelected = selectedSet.has(o.value);
                return (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => onToggle?.(o.value)}
                    style={chipBase(isSelected)}
                    aria-pressed={isSelected}
                  >
                    {isSelected && (
                      <span style={{ fontSize: 11, opacity: 0.9 }}>✓</span>
                    )}
                    <span>{o.label}</span>
                    {o.sublabel && (
                      <span
                        style={{
                          fontSize: 11,
                          opacity: 0.75,
                          fontWeight: 400,
                        }}
                      >
                        {o.sublabel}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}

        {freeText.length > 0 && (
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px dashed ${t.bd}` }}>
            <div
              style={{
                fontSize: 11,
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: ".06em",
                color: t.txM,
                marginBottom: 6,
              }}
            >
              Tracked (typed)
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {freeText.map((v) => (
                <span
                  key={v}
                  style={{
                    ...chipBase(true),
                    background: t.wm,
                    borderColor: t.wm,
                    cursor: "default",
                    paddingRight: 6,
                  }}
                  title="Not currently scraped — alerts only"
                >
                  <span>{v}</span>
                  {onRemove && (
                    <button
                      type="button"
                      onClick={() => onRemove(v)}
                      aria-label={`Remove ${v}`}
                      style={{
                        background: "transparent",
                        border: 0,
                        color: "#fff",
                        cursor: "pointer",
                        padding: "0 2px",
                        fontSize: 14,
                        lineHeight: 1,
                      }}
                    >
                      ×
                    </button>
                  )}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
