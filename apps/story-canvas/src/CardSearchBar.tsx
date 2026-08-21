import { useEffect, useMemo, useRef, useState } from "react";
import { searchCards, type CardSearchResult } from "./cardSearch";
import type { GraphNode } from "./domain";

export function CardSearchBar({
  nodes,
  onSelect,
  onQueryChange,
}: {
  nodes: GraphNode[];
  onSelect: (result: CardSearchResult) => void;
  onQueryChange?: (query: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const results = useMemo(() => searchCards(nodes, query), [nodes, query]);

  useEffect(() => {
    onQueryChange?.(query);
  }, [query, onQueryChange]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as HTMLElement)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const pick = (r: CardSearchResult) => {
    onSelect(r);
    setOpen(false);
    setQuery("");
  };

  return (
    <div className="sc-card-search" ref={wrapRef}>
      <input
        ref={inputRef}
        type="search"
        className="sc-card-search-input"
        placeholder="Find card… #2, rekindle, beat"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((i) => Math.min(results.length - 1, i + 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((i) => Math.max(0, i - 1));
          } else if (e.key === "Enter" && results[active]) {
            e.preventDefault();
            pick(results[active]);
          } else if (e.key === "Escape") {
            setOpen(false);
            inputRef.current?.blur();
          }
        }}
      />
      {open && query.trim() && (
        <ul className="sc-card-search-results" role="listbox">
          {results.length === 0 && (
            <li className="sc-card-search-empty">No cards match “{query.trim()}”</li>
          )}
          {results.map((r, i) => (
            <li key={r.node.id}>
              <button
                type="button"
                className={i === active ? "active" : ""}
                role="option"
                aria-selected={i === active}
                onMouseEnter={() => setActive(i)}
                onClick={() => pick(r)}
              >
                <span className="sc-card-search-label">{r.label}</span>
                <span className="sc-card-search-title">{r.node.title}</span>
                <span className="sc-card-search-snippet">{r.snippet}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
