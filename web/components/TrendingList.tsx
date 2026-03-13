"use client";

interface Restaurant {
  rank: number;
  name: string;
  neighborhood: string | null;
  cuisine_type: string | null;
  score: number;
  trending_reason: string | null;
  platforms_active: string[];
}

const PLATFORM_LABELS: Record<string, string> = {
  yelp: "Yelp",
  reddit: "Reddit",
  threads: "Threads",
  google: "Google",
  trends: "Search",
};

const PLATFORM_COLORS: Record<string, string> = {
  yelp: "bg-red-50 text-red-700",
  reddit: "bg-orange-50 text-orange-700",
  threads: "bg-gray-100 text-gray-700",
  google: "bg-blue-50 text-blue-700",
  trends: "bg-green-50 text-green-700",
};

export function TrendingList({ restaurants }: { restaurants: Restaurant[] }) {
  return (
    <div className="space-y-6">
      {restaurants.map((r) => (
        <article
          key={r.rank}
          className="group rounded-lg border border-gray-100 p-5 hover:border-gray-200 transition-colors"
        >
          <div className="flex items-start gap-4">
            {/* Rank */}
            <span className="text-2xl font-bold text-orange-500 tabular-nums leading-none mt-1">
              {r.rank}
            </span>

            <div className="flex-1 min-w-0">
              {/* Name and meta */}
              <h2 className="text-lg font-semibold leading-tight">
                {r.name}
              </h2>
              <p className="text-sm text-gray-500 mt-1">
                {[r.neighborhood, r.cuisine_type].filter(Boolean).join(" · ")}
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
  );
}
