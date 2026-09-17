"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type Theatre = {
  id: number;
  name: string;
  distance_miles: number | null;
  tracked: boolean;
  is_favourite: boolean;
  upcoming: number;
};

export function TheatreToggle({ theatre }: { theatre: Theatre }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle(field: "tracked" | "isFavourite", value: boolean) {
    setPending(true);
    setError(null);
    try {
      const res = await fetch("/api/theatres", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: theatre.id, [field]: value }),
      });
      if (!res.ok) {
        setError("Save failed. Try again.");
        setPending(false);
        return;
      }
      router.refresh();
    } catch {
      setError("Save failed. Try again.");
      setPending(false);
    }
  }

  return (
    <div className="border-t border-line py-4 hover:bg-green-2">
      <div className="font-display text-lg font-bold">
        <button
          type="button"
          onClick={() => toggle("isFavourite", !theatre.is_favourite)}
          disabled={pending}
          aria-label={theatre.is_favourite ? "remove favourite" : "make favourite"}
          className={`p-0 ${theatre.is_favourite ? "text-orange" : "text-sage"} disabled:opacity-50`}
        >
          &#9670;{" "}
        </button>
        {theatre.name}
      </div>
      <div className="num mt-1 text-[13px] text-sage">
        {theatre.distance_miles !== null ? `${Math.round(theatre.distance_miles)} mi` : "unknown"}
        {" · "}
        <button
          type="button"
          onClick={() => toggle("tracked", !theatre.tracked)}
          disabled={pending}
          className="p-0 underline hover:text-orange disabled:opacity-50"
        >
          {theatre.tracked ? "tracked" : "not tracked"}
        </button>
        {" · ~56 req/day · "}
        {theatre.upcoming} upcoming
        {error && <span className="ml-2">{error}</span>}
      </div>
    </div>
  );
}
