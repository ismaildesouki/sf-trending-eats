"use client";

import { useState, useMemo, useRef, useEffect } from "react";

interface SourceLink {
  platform: string;
  url: string;
  plays?: number;
  likes?: number;
  label?: string;
}

interface Restaurant {
  rank: number;
  name: string;
  neighborhood: string | null;
  city?: string | null;
  cuisine_type: string | null;
  score: number;
  trending_reason: string | null;
  platforms_active: string[];
  image_url?: string | null;
  yelp_url?: string | null;
  price_range?: string | null;
  sources?: SourceLink[];
}

const PLATFORM_LABELS: Record<string, string> = {
  yelp: "Yelp",
  reddit: "Reddit",
  threads: "Threads",
  google: "Google",
  trends: "Search",
  tiktok: "TikTok",
  instagram: "Instagram",
  food_media: "Food Media",
};

const PLATFORM_ICONS: Record<string, string> = {
  tiktok: "♪",
  instagram: "◎",
  yelp: "★",
  reddit: "◆",
  food_media: "✎",
};

const PLATFORM_BADGE_STYLES: Record<string, string> = {
  yelp: "bg-red-100/80 text-red-700 border-red-200/60",
  reddit: "bg-orange-100/80 text-orange-700 border-orange-200/60",
  threads: "bg-gray-100/80 text-gray-700 border-gray-200/60",
  google: "bg-blue-100/80 text-blue-700 border-blue-200/60",
  trends: "bg-green-100/80 text-green-700 border-green-200/60",
  tiktok: "bg-pink-100/80 text-pink-700 border-pink-200/60",
  instagram: "bg-purple-100/80 text-purple-700 border-purple-200/60",
  food_media: "bg-emerald-100/80 text-emerald-700 border-emerald-200/60",
};

const PLATFORM_LINK_STYLES: Record<string, string> = {
  tiktok: "text-pink-600 hover:text-pink-700 hover:bg-pink-50",
  instagram: "text-purple-600 hover:text-purple-700 hover:bg-purple-50",
  yelp: "text-red-600 hover:text-red-700 hover:bg-red-50",
  reddit: "text-orange-600 hover:text-orange-700 hover:bg-orange-50",
  food_media: "text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50",
};

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toString();
}

// ── Multi-select dropdown ──────────────────────────────────
function MultiSelect({
  label,
  options,
  selected,
  onChange,
  labelMap,
}: {
  label: string;
  options: string[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  labelMap?: Record<string, string>;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const SEARCH_THRESHOLD = 8;

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  useEffect(() => {
    if (open && options.length >= SEARCH_THRESHOLD) {
      searchRef.current?.focus();
    }
  }, [open, options.length]);

  const toggle = (val: string) => {
    const next = new Set(selected);
    if (next.has(val)) next.delete(val);
    else next.add(val);
    onChange(next);
  };

  const filteredOptions = search
    ? options.filter((o) => (labelMap?.[o] || o).toLowerCase().includes(search.toLowerCase()))
    : options;

  const allSelected = filteredOptions.length > 0 && filteredOptions.every((o) => selected.has(o));

  const toggleAll = () => {
    if (allSelected) {
      const next = new Set(selected);
      filteredOptions.forEach((o) => next.delete(o));
      onChange(next);
    } else {
      const next = new Set(selected);
      filteredOptions.forEach((o) => next.add(o));
      onChange(next);
    }
  };

  const count = selected.size;
  const buttonLabel = count === 0 ? label : `${label} (${count})`;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`
          px-2.5 py-1.5 text-xs border rounded-lg bg-white
          focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-orange-400
          flex items-center gap-1
          ${count > 0 ? "border-orange-300 text-orange-700" : "border-gray-200 text-gray-700"}
        `}
      >
        {buttonLabel}
        <svg className="w-3 h-3 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-20 min-w-[200px] max-h-72 flex flex-col">
          {options.length >= SEARCH_THRESHOLD && (
            <div className="px-2 pt-2 pb-1 border-b border-gray-100">
              <input
                ref={searchRef}
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={`Search ${label.toLowerCase()}...`}
                className="w-full px-2 py-1 text-xs border border-gray-200 rounded bg-gray-50 focus:outline-none focus:ring-1 focus:ring-orange-400 focus:border-orange-400"
              />
            </div>
          )}

          {options.length >= SEARCH_THRESHOLD && (
            <button
              onClick={toggleAll}
              className="px-3 py-1.5 text-[11px] text-left text-orange-600 hover:bg-orange-50 font-medium border-b border-gray-100"
            >
              {allSelected ? "Deselect all" : "Select all"}{search ? " (filtered)" : ""}
            </button>
          )}

          <div className="overflow-y-auto py-1">
            {filteredOptions.length === 0 ? (
              <p className="px-3 py-2 text-xs text-gray-400">No matches</p>
            ) : (
              filteredOptions.map((opt) => (
                <label
                  key={opt}
                  className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-700 hover:bg-orange-50 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selected.has(opt)}
                    onChange={() => toggle(opt)}
                    className="rounded border-gray-300 text-orange-500 focus:ring-orange-400"
                  />
                  {labelMap?.[opt] || opt}
                </label>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Score badge ────────────────────────────────────────────
function ScoreBadge({ score, rank }: { score: number; rank: number }) {
  const hot = rank <= 3;
  const warm = rank <= 10;
  return (
    <div className={`
      flex flex-col items-center justify-center w-14 h-14 rounded-xl shrink-0
      ${hot ? "bg-orange-500 text-white" : warm ? "bg-orange-100 text-orange-700" : "bg-gray-100 text-gray-600"}
    `}>
      <span className="text-lg font-bold leading-none tabular-nums">
        {score}
      </span>
      <span className={`text-[10px] font-medium leading-none mt-0.5 ${hot ? "text-orange-100" : warm ? "text-orange-500" : "text-gray-400"}`}>
        score
      </span>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────
export function TrendingList({ restaurants }: { restaurants: Restaurant[] }) {
  const [filterCuisines, setFilterCuisines] = useState<Set<string>>(new Set());
  const [filterNeighborhoods, setFilterNeighborhoods] = useState<Set<string>>(new Set());
  const [filterPlatforms, setFilterPlatforms] = useState<Set<string>>(new Set());
  const [filterPrices, setFilterPrices] = useState<Set<string>>(new Set());

  const cuisines = useMemo(() => {
    const set = new Set<string>();
    restaurants.forEach((r) => r.cuisine_type && set.add(r.cuisine_type));
    return Array.from(set).sort();
  }, [restaurants]);

  const neighborhoods = useMemo(() => {
    const set = new Set<string>();
    restaurants.forEach((r) => r.neighborhood && set.add(r.neighborhood));
    return Array.from(set).sort();
  }, [restaurants]);

  const platforms = useMemo(() => {
    const set = new Set<string>();
    restaurants.forEach((r) => r.platforms_active.forEach((p) => set.add(p)));
    return Array.from(set).sort();
  }, [restaurants]);

  const prices = useMemo(() => {
    const set = new Set<string>();
    restaurants.forEach((r) => r.price_range && set.add(r.price_range));
    // Sort by $ count
    return Array.from(set).sort((a, b) => a.length - b.length || a.localeCompare(b));
  }, [restaurants]);

  const filtered = useMemo(() => {
    return restaurants.filter((r) => {
      if (filterCuisines.size > 0 && (!r.cuisine_type || !filterCuisines.has(r.cuisine_type)))
        return false;
      if (filterNeighborhoods.size > 0 && (!r.neighborhood || !filterNeighborhoods.has(r.neighborhood)))
        return false;
      if (filterPlatforms.size > 0 && !r.platforms_active.some((p) => filterPlatforms.has(p)))
        return false;
      if (filterPrices.size > 0 && (!r.price_range || !filterPrices.has(r.price_range)))
        return false;
      return true;
    });
  }, [restaurants, filterCuisines, filterNeighborhoods, filterPlatforms, filterPrices]);

  const hasFilters =
    filterCuisines.size > 0 ||
    filterNeighborhoods.size > 0 ||
    filterPlatforms.size > 0 ||
    filterPrices.size > 0;

  const clearAll = () => {
    setFilterCuisines(new Set());
    setFilterNeighborhoods(new Set());
    setFilterPlatforms(new Set());
    setFilterPrices(new Set());
  };

  return (
    <div>
      {/* Filter bar */}
      <div className="sticky top-0 z-10 bg-[#fefcf9]/95 backdrop-blur-sm pb-4 pt-2 -mx-4 px-4 sm:-mx-6 sm:px-6">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-gray-400 mr-1">Filter:</span>

          <MultiSelect
            label="Cuisine"
            options={cuisines}
            selected={filterCuisines}
            onChange={setFilterCuisines}
          />

          <MultiSelect
            label="Neighborhood"
            options={neighborhoods}
            selected={filterNeighborhoods}
            onChange={setFilterNeighborhoods}
          />

          <MultiSelect
            label="Price"
            options={prices}
            selected={filterPrices}
            onChange={setFilterPrices}
          />

          <MultiSelect
            label="Platform"
            options={platforms}
            selected={filterPlatforms}
            onChange={setFilterPlatforms}
            labelMap={PLATFORM_LABELS}
          />

          {hasFilters && (
            <button
              onClick={clearAll}
              className="px-2.5 py-1.5 text-xs text-orange-600 hover:text-orange-700 font-medium"
            >
              Clear
            </button>
          )}
        </div>

        {hasFilters && (
          <p className="text-xs text-gray-400 mt-2">
            Showing {filtered.length} of {restaurants.length}
          </p>
        )}
      </div>

      {/* Restaurant list */}
      <div className="space-y-3">
        {filtered.map((r, idx) => {
          const displayRank = hasFilters ? idx + 1 : r.rank;
          const isTop3 = displayRank <= 3;
          const isTop10 = displayRank <= 10;

          return (
            <article
              key={r.name}
              className={`
                group rounded-xl p-4 sm:p-5 transition-all duration-200
                ${isTop3
                  ? "bg-white shadow-md shadow-orange-100/50 border border-orange-100 hover:shadow-lg hover:shadow-orange-100/60"
                  : "bg-white/80 border border-gray-100 hover:bg-white hover:shadow-sm hover:border-gray-200"
                }
              `}
            >
              <div className="flex items-start gap-3 sm:gap-4">
                {/* Rank number */}
                <div className={`
                  w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5
                  ${isTop3
                    ? "bg-gradient-to-br from-orange-400 to-orange-500 text-white font-bold text-sm"
                    : isTop10
                      ? "bg-orange-50 text-orange-600 font-bold text-sm"
                      : "bg-gray-50 text-gray-400 font-semibold text-sm"
                  }
                `}>
                  {displayRank}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h2 className={`font-semibold leading-tight ${isTop3 ? "text-base sm:text-lg" : "text-base"}`}>
                        {r.name}
                      </h2>
                      <p className="text-xs text-gray-400 mt-0.5 truncate">
                        {[r.neighborhood, r.cuisine_type, r.price_range]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                    </div>

                    {/* Score badge */}
                    <ScoreBadge score={r.score} rank={displayRank} />
                  </div>

                  {/* Trending reason */}
                  {r.trending_reason && (
                    <p className="text-sm text-gray-500 mt-2 leading-relaxed">
                      {r.trending_reason}
                    </p>
                  )}

                  {/* Platform badges */}
                  <div className="flex flex-wrap items-center gap-1.5 mt-3">
                    {r.platforms_active.map((platform) => (
                      <span
                        key={platform}
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium border ${
                          PLATFORM_BADGE_STYLES[platform] || "bg-gray-100 text-gray-600 border-gray-200"
                        }`}
                      >
                        <span className="opacity-70">{PLATFORM_ICONS[platform] || ""}</span>
                        {PLATFORM_LABELS[platform] || platform}
                      </span>
                    ))}
                  </div>

                  {/* Source links */}
                  {r.sources && r.sources.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 mt-2">
                      <span className="text-[10px] uppercase tracking-wider text-gray-300 font-medium mr-0.5">
                        Sources:
                      </span>
                      {r.sources.map((s, i) => (
                        <a
                          key={i}
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`inline-flex items-center gap-0.5 text-[11px] font-medium px-1.5 py-0.5 rounded transition-colors ${
                            PLATFORM_LINK_STYLES[s.platform] ||
                            "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                          }`}
                        >
                          {s.label || PLATFORM_LABELS[s.platform] || s.platform}
                          {s.plays ? (
                            <span className="text-[10px] opacity-70">
                              {formatNumber(s.plays)}
                            </span>
                          ) : s.likes && s.likes > 0 ? (
                            <span className="text-[10px] opacity-70">
                              {formatNumber(s.likes)}
                            </span>
                          ) : null}
                          <span className="opacity-40">↗</span>
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
