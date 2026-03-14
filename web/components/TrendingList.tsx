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

const PLATFORM_COLORS: Record<string, string> = {
  yelp: "bg-red-50 text-red-700",
  reddit: "bg-orange-50 text-orange-700",
  threads: "bg-gray-100 text-gray-700",
  google: "bg-blue-50 text-blue-700",
  trends: "bg-green-50 text-green-700",
  tiktok: "bg-pink-50 text-pink-700",
  instagram: "bg-purple-50 text-purple-700",
};

const PLATFORM_LINK_COLORS: Record<string, string> = {
  tiktok: "text-pink-600 hover:text-pink-800",
  instagram: "text-purple-600 hover:text-purple-800",
  yelp: "text-red-600 hover:text-red-800",
  reddit: "text-orange-600 hover:text-orange-800",
};

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toString();
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

  const filtered = useMemo(() => {
    return restaurants.filter((r) => {
      if (filterCuisine !== "all" && r.cuisine_type !== filterCuisine)
        return false;
      if (
        filterNeighborhood !== "all" &&
        r.neighborhood !== filterNeighborhood
      )
        return false;
      if (
        filterPlatform !== "all" &&
        !r.platforms_active.includes(filterPlatform)
      )
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
      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-6">
        <select
          value={filterCuisine}
          onChange={(e) => setFilterCuisine(e.target.value)}
          className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-orange-500"
        >
          <option value="all">All Cuisines</option>
          {cuisines.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>

        <select
          value={filterNeighborhood}
          onChange={(e) => setFilterNeighborhood(e.target.value)}
          className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-orange-500"
        >
          <option value="all">All Neighborhoods</option>
          {neighborhoods.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>

        <select
          value={filterPlatform}
          onChange={(e) => setFilterPlatform(e.target.value)}
          className="px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-orange-500"
        >
          <option value="all">All Platforms</option>
          <option value="tiktok">TikTok</option>
          <option value="instagram">Instagram</option>
          <option value="yelp">Yelp</option>
          <option value="reddit">Reddit</option>
        </select>

        {hasFilters && (
          <button
            onClick={() => {
              setFilterCuisine("all");
              setFilterNeighborhood("all");
              setFilterPlatform("all");
            }}
            className="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700 underline"
          >
            Clear filters
          </button>
        )}
      </div>

      <p className="text-sm text-gray-400 mb-4">
        Showing {filtered.length} of {restaurants.length} restaurants
      </p>

      {/* Restaurant list */}
      <div className="space-y-6">
        {filtered.map((r, idx) => (
          <article
            key={r.name}
            className="group rounded-lg border border-gray-100 p-5 hover:border-gray-200 transition-colors"
          >
            <div className="flex items-start gap-4">
              {/* Rank */}
              <span className="text-2xl font-bold text-orange-500 tabular-nums leading-none mt-1">
                {hasFilters ? idx + 1 : r.rank}
              </span>

              <div className="flex-1 min-w-0">
                {/* Name and meta */}
                <h2 className="text-lg font-semibold leading-tight">
                  {r.name}
                </h2>
                <p className="text-sm text-gray-500 mt-1">
                  {[r.neighborhood, r.cuisine_type, r.price_range]
                    .filter(Boolean)
                    .join(" · ")}
                </p>

                {/* Trending reason */}
                {r.trending_reason && (
                  <p className="text-sm text-gray-600 mt-3 leading-relaxed">
                    {r.trending_reason}
                  </p>
                )}

                {/* Platform badges */}
                <div className="flex flex-wrap gap-1.5 mt-3">
                  {r.platforms_active.map((platform) => (
                    <span
                      key={platform}
                      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                        PLATFORM_COLORS[platform] || "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {PLATFORM_LABELS[platform] || platform}
                    </span>
                  ))}
                </div>

                {/* Source links */}
                {r.sources && r.sources.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-50">
                    <p className="text-xs font-medium text-gray-400 mb-1.5">
                      Sources
                    </p>
                    <div className="flex flex-wrap gap-x-4 gap-y-1">
                      {r.sources.map((s, i) => (
                        <a
                          key={i}
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`text-xs underline decoration-dotted ${
                            PLATFORM_LINK_COLORS[s.platform] ||
                            "text-gray-500 hover:text-gray-700"
                          }`}
                        >
                          {PLATFORM_LABELS[s.platform] || s.platform}
                          {s.plays
                            ? ` (${formatNumber(s.plays)} plays)`
                            : s.likes
                            ? ` (${formatNumber(s.likes)} likes)`
                            : ""}
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Score */}
              <div className="text-right shrink-0">
                <div className="text-sm font-medium text-gray-400">Score</div>
                <div className="text-xl font-bold tabular-nums">{r.score}</div>
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
