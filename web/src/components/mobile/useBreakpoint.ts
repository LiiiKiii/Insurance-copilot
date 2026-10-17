"use client";

import { useEffect, useState } from "react";

export type Breakpoint = "xs" | "sm" | "md" | "lg" | "xl" | "2xl";

const QUERIES: Array<[Breakpoint, string]> = [
	["2xl", "(min-width: 1536px)"],
	["xl", "(min-width: 1280px)"],
	["lg", "(min-width: 1024px)"],
	["md", "(min-width: 768px)"],
	["sm", "(min-width: 640px)"],
];

function detect(): Breakpoint {
	if (typeof window === "undefined") return "lg";
	for (const [name, query] of QUERIES) {
		if (window.matchMedia(query).matches) return name;
	}
	return "xs";
}

export function useBreakpoint(): Breakpoint {
	const [bp, setBp] = useState<Breakpoint>(() => detect());

	useEffect(() => {
		const debug = process.env.NEXT_PUBLIC_DEBUG_MOBILE === "1";
		const update = () => {
			setBp((prev) => {
				const next = detect();
				if (debug && prev !== next) {
					console.debug("[breakpoint]", prev, "->", next);
				}
				return next;
			});
		};
		update();
		const mqls = QUERIES.map(([, q]) => window.matchMedia(q));
		mqls.forEach((mql) => mql.addEventListener("change", update));
		window.addEventListener("resize", update);
		return () => {
			mqls.forEach((mql) => mql.removeEventListener("change", update));
			window.removeEventListener("resize", update);
		};
	}, []);

	return bp;
}

export function useViewportSize(): { w: number; h: number } {
	const [size, setSize] = useState(() => ({
		w: typeof window !== "undefined" ? window.innerWidth : 1280,
		h: typeof window !== "undefined" ? window.innerHeight : 800,
	}));

	useEffect(() => {
		const onResize = () => setSize({ w: window.innerWidth, h: window.innerHeight });
		onResize();
		window.addEventListener("resize", onResize);
		return () => window.removeEventListener("resize", onResize);
	}, []);

	return size;
}
