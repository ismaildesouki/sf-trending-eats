"use client";

import { useState, useMemo } from "react";

interface SourceLink {
  platform: string;
  url: string;
  plays?: number;
  likes?: number;
}

interface Restaurant {
  rank: number;
  name: string;
  neighborhood: string | null;
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
};

const PLATFORM_ICONS: Record<string, string> = {
  tiktok: "♪",
  instagram: "◎",
  yelp: "★",
  reddit: "◆",
};

const PLATFORM_BADGE_STYLES: Record<string, string> = {
  yelp: "bg-red-100/80 text-red-700 border-red-200/60",
  reddit: "bg-orange-100/80 text-orange-700 border-orange-200/60",
  threads: "bg-gray-100/80 text-gray-700 border-gray-200/60",
  google: "bg-blue-100/80 text-blue-700 border-blue-200/60",
  trends: "bg-green-100/80 text-green-700 border-green-200/60",
  tiktok: "bg-pink-100/80 text-pink-700 border-pink-200/60",
  instagram: "bg-purple-100/80 text-purple-700 border-purple-200/60",
};

const PLATFORM_LINK_STYLES: Record<string, string> = {
  tiktok: "text-pink-600 hover:text-pink-700 hover:bg-pink-50",
  instagram: "text-purple-600 hover:text-purple-700 hover:bg-purple-50",
  yelp: "text-red-600 hover:text-red-700 hover:bg-red-50",
  reddit: "text-orange-600 hover:text-orange-700 hover:bg-orange-50",
};

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toString();
}

function ScoreBadge({ score, rank }: { score: number; rank: number }) {
  const hot = rank <= 3;
  const warm = rank <= 10;
  return (
    <div className={`
      flex flex-col items-center justify-center w-14 h-14 rounded-xl shrink-0
      ${hot ? "bg-orange-500 text-white" : warm ? "bg-orange-100 text-orange-700" : "bg-gray-100 text-gray-600"}
    `}>
      <span className={`text-lg font-bold leading-none tabular-nums ${hot ? "" : ""}`}>
        {score}
      </span>
      <span className={`text-[10px] font-medium leading-none mt-0.5 ${hot ? "text-orange-100" : warm ? "text-orange-500" : "text-gray-400"}`}>
        score
      </span>
    </div>
  );
}

export function TrendingList({ restaurants }: { restaurants: Restaurant[] }) {
  const [filterCuisine, setFilterCuisine] = useState<string>("all");
  const [filterNeighborhood, setFilterNeighborhood] = useState<string>("all");
  const [filterPlatform, setFilterPlatform] = useState<string>("all");

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

  const filtered = useMemo(() => {
    return restaurants.filter((r) => {
      if (filterCuisine !== "all" && r.cuisine_type !== filterCuisine)
        return false;
      if (filterNeighborhood !== "all" && r.neighborhood !== filterNeighborhood)
        return false;
      if (filterPlatform !== "all" && !r.platforms_active.includes(filterPlatform))
        return false;
      return true;
    });
  }, [restaurants, filterCuisine, filterNeighborhood, filterPlatform]);

  const hasFilters =
    filterCuisine !== "all" ||
    filterNeighborhood !== "all" ||
    filterPlatform !== "all";

  return (
    <div>
      {/* Filter bar */}
      <div className="sticky top-0 z-10 bg-[#fefcf9]/95 backdrop-blur-sm pb-4 pt-2 -mx-4 px-4 sm:-mx-6 sm:px-6">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-gray-400 mr-1">Filter:</span>
          <select
            value={filterCuisine}
            onChange={(e) => setFilterCuisine(e.target.value)}
            className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-orange-400 text-gray-700"
          >
            <option value="all">All Cuisines</option>
            {cuisines.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>

          <select
            value={filterNeighborhood}
            onChange={(e) => setFilterNeighborhood(e.target.value)}
            className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-orange-400 text-gray-700"
          >
            <option value="all">All Neighborhoods</option>
            {neighborhoods.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>

          <select
            value={filterPlatform}
            onChange={(e) => setFilterPlatform(e.target.value)}
            className="px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-orange-400 text-gray-700"
          >
            <option value="all">All Platforms</option>
            {platforms.map((p) => (
              <option key={p} value={p}>{PLATFORM_LABELS[p] || p}</option>
            ))}
          </select>

          {hasFilters && (
            <button
              onClick={() => {
                setFilterCuisine("all");
                setFilterNeighborhood("all");
                setFilterPlatform("all");
              }}
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

                  {/* Platform badges + Source links row */}
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
                          {PLATFORM_LABELS[s.platform] || s.platform}
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
