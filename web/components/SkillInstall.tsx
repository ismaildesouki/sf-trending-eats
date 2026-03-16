"use client";

import { useState } from "react";

const SKILL_URL = "https://raw.githubusercontent.com/ismaildesouki/sf-trending-eats/main/.claude/skills/restaurant-finder.md";

export function SkillInstall() {
  const [copied, setCopied] = useState(false);

  const installCommand = `curl -sL "${SKILL_URL}" -o ~/.claude/skills/restaurant-finder.md --create-dirs`;

  const handleCopy = () => {
    navigator.clipboard.writeText(installCommand);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-gradient-to-br from-gray-900 to-gray-800 rounded-2xl p-6 sm:p-8 text-white">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-2xl">🤖</span>
        <h3 className="text-lg font-semibold">
          Get personalized recs with Claude
        </h3>
      </div>
      <p className="text-sm text-gray-300 mt-2 leading-relaxed">
        Install our Claude skill to get restaurant recommendations powered by the same social-media-first
        methodology behind this dashboard. Just ask Claude &ldquo;where should I eat tonight?&rdquo; and it&apos;ll
        find what&apos;s actually buzzing — no Yelp star ratings, just real cultural signals.
      </p>

      <div className="mt-5 space-y-4">
        {/* Method 1: curl */}
        <div>
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">
            Quick install (Claude Code users)
          </p>
          <div className="relative group">
            <pre className="bg-black/40 rounded-xl px-4 py-3 text-sm text-green-400 font-mono overflow-x-auto border border-gray-700/50">
              {installCommand}
            </pre>
            <button
              onClick={handleCopy}
              className="absolute top-2 right-2 px-2.5 py-1 text-[11px] font-medium bg-gray-700/80 hover:bg-gray-600 text-gray-200 rounded-md transition-colors"
            >
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
        </div>

        {/* Method 2: Manual */}
        <div>
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">
            Manual install
          </p>
          <ol className="text-sm text-gray-300 space-y-1.5 list-decimal list-inside">
            <li>
              <a
                href={SKILL_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-orange-400 hover:text-orange-300 underline underline-offset-2"
              >
                Download restaurant-finder.md
              </a>
            </li>
            <li>Save to <code className="text-xs bg-black/30 px-1.5 py-0.5 rounded font-mono">~/.claude/skills/restaurant-finder.md</code></li>
            <li>Ask Claude: &ldquo;Where should I eat in SF tonight?&rdquo;</li>
          </ol>
        </div>

        {/* What it does */}
        <div className="pt-3 border-t border-gray-700/50">
          <p className="text-xs text-gray-400">
            The skill teaches Claude to prioritize TikTok virality, food media buzz (Infatuation, Eater),
            and local creator recommendations over generic review scores. Works for any city, cuisine, or dietary need.
          </p>
        </div>
      </div>
    </div>
  );
}
