import { TrendingList } from "../components/TrendingList";
import { NewsletterSignup } from "../components/NewsletterSignup";

async function getTrendingData() {
  try {
    const data = await import("../lib/data/trending.json");
    return data.default || data;
  } catch {
    return null;
  }
}

export default async function Home() {
  const data = await getTrendingData();

  return (
    <main className="min-h-screen">
      {/* Header */}
      <header className="bg-gradient-to-b from-orange-50 to-transparent">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 pt-10 pb-8">
          <div className="flex items-center gap-3 mb-1">
            <span className="text-3xl">🔥</span>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-gray-900">
              SF Trending Eats
            </h1>
          </div>
          <p className="text-gray-500 mt-1">
            Bay Area restaurants trending on social media right now
          </p>
          {data && (
            <p className="text-xs text-gray-400 mt-3">
              Updated {new Date(data.generated_at).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })} · Tracking {data.restaurants.length} restaurants across TikTok, Instagram &amp; more
            </p>
          )}
        </div>
      </header>

      {/* Main content */}
      <div className="max-w-3xl mx-auto px-4 sm:px-6 pb-12">
        {data ? (
          <TrendingList restaurants={data.restaurants} />
        ) : (
          <div className="text-center py-16">
            <p className="text-gray-400 text-lg">
              First trending list coming soon.
            </p>
            <p className="text-gray-400 mt-2">
              Sign up below to get notified when it drops.
            </p>
          </div>
        )}

        {/* Newsletter signup */}
        <div className="mt-16 pt-8 border-t border-gray-200/60">
          <NewsletterSignup />
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-gray-100">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-8 text-center text-sm text-gray-400">
          <p>
            Tracks social media signals across TikTok, Instagram, Yelp, Reddit, and
            more to surface restaurants that are trending before mainstream food media covers them.
          </p>
          <p className="mt-3 font-medium text-gray-500">
            Built with data, not opinions.
          </p>
        </div>
      </footer>
    </main>
  );
}
