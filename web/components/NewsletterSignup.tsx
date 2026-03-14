"use client";

import { useState } from "react";

export function NewsletterSignup() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");

  const handleSubmit = async (e: React.MouseEvent) => {
    e.preventDefault();
    if (!email) return;

    setStatus("loading");

    try {
      // TODO: Replace with actual Beehiiv subscribe endpoint
      await new Promise((resolve) => setTimeout(resolve, 500));
      setStatus("success");
      setEmail("");
    } catch {
      setStatus("error");
    }
  };

  if (status === "success") {
    return (
      <div className="text-center py-4">
        <p className="text-green-600 font-medium">You're in! Check your inbox Tuesday.</p>
      </div>
    );
  }

  return (
    <div className="bg-gradient-to-br from-orange-50 to-amber-50/50 rounded-2xl p-6 sm:p-8">
      <h3 className="text-lg font-semibold text-gray-900">
        Get the weekly list in your inbox
      </h3>
      <p className="text-sm text-gray-500 mt-1">
        Every Tuesday: the top trending Bay Area restaurants, sourced from social media data.
      </p>
      <div className="flex gap-2 mt-4">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@email.com"
          className="flex-1 px-4 py-2.5 border border-gray-200 rounded-xl text-sm bg-white focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent"
        />
        <button
          onClick={handleSubmit}
          disabled={status === "loading" || !email}
          className="px-5 py-2.5 bg-orange-500 text-white rounded-xl text-sm font-semibold hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm shadow-orange-200"
        >
          {status === "loading" ? "..." : "Subscribe"}
        </button>
      </div>
      {status === "error" && (
        <p className="text-red-500 text-sm mt-2">Something went wrong. Please try again.</p>
      )}
    </div>
  );
}
