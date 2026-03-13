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
      // const resp = await fetch("/api/subscribe", {
      //   method: "POST",
      //   body: JSON.stringify({ email }),
      // });

      // Simulated success for MVP
      await new Promise((resolve) => setTimeout(resolve, 500));
      setStatus("success");
      setEmail("");
    } catch {
      setStatus("error");
    }
  };

  if (status === "success") {
    return (
      <div className="text-center">
        <p className="text-green-600 font-medium">You're in! Check your inbox Tuesday.</p>
      </div>
    );
  }

  return (
    <div>
      <h3 className="text-lg font-semibold">Get the weekly list in your inbox</h3>
      <p className="text-sm text-gray-500 mt-1">
        Every Tuesday: the top trending Bay Area restaurants, sourced from social media data.
      </p>
      <div className="flex gap-2 mt-4">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@email.com"
          className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent"
        />
        <button
          onClick={handleSubmit}
          disabled={status === "loading" || !email}
          className="px-4 py-2 bg-orange-500 text-white rounded-lg text-sm font-medium hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
