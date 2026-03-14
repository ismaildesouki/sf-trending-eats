import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

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
      <body className={`${inter.className} text-gray-900 antialiased`}>
        {children}
      </body>
    </html>
  );
}
