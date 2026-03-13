import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SF Trending Eats | Bay Area Restaurant Trends",
  description:
    "Discover the Bay Area restaurants trending on social media before they blow up. Updated weekly with data from TikTok, Instagram, Reddit, and more.",
  openGraph: {
    title: "SF Trending Eats",
    description: "Bay Area restaurants trending on social media this week",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-white text-gray-900 antialiased">{children}</body>
    </html>
  );
}
