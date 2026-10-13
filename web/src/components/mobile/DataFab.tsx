"use client";

import { useRef, useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";

interface DataFabProps {
	onClick: () => void;
	active?: boolean;
	className?: string;
}

export function DataFab({ onClick, active = false, className }: DataFabProps) {
	const { t } = useTranslation();
	const [pos, setPos] = useState({ x: -1, y: -1 }); // -1 = use CSS default
	const dragRef = useRef({ startX: 0, startY: 0, startPosX: 0, startPosY: 0, moved: false });

	const getDefault = () => ({
		x: (typeof window !== "undefined" ? window.innerWidth : 375) - 12 - 48,
		y: (typeof window !== "undefined" ? window.innerHeight : 667) - 80 - 48,
	});

	const onTouchStart = useCallback((e: React.TouchEvent) => {
		const t = e.touches[0];
		const cur = pos.x < 0 ? getDefault() : pos;
		dragRef.current = { startX: t.clientX, startY: t.clientY, startPosX: cur.x, startPosY: cur.y, moved: false };
	}, [pos]);

	const onTouchMove = useCallback((e: React.TouchEvent) => {
		const t = e.touches[0];
		const dx = t.clientX - dragRef.current.startX;
		const dy = t.clientY - dragRef.current.startY;
		if (Math.abs(dx) > 4 || Math.abs(dy) > 4) dragRef.current.moved = true;
		if (!dragRef.current.moved) return;
		e.preventDefault();
		const vw = window.innerWidth;
		const vh = window.innerHeight;
		setPos({
			x: Math.max(4, Math.min(vw - 52, dragRef.current.startPosX + dx)),
			y: Math.max(4, Math.min(vh - 52, dragRef.current.startPosY + dy)),
		});
	}, []);

	const onTouchEnd = useCallback(() => {
		if (!dragRef.current.moved) { onClick(); return; }
		// Snap to nearest left/right edge
		const vw = window.innerWidth;
		setPos(prev => ({
			x: prev.x < vw / 2 ? 12 : vw - 12 - 48,
			y: prev.y,
		}));
	}, [onClick]);

	const style = pos.x >= 0
		? { left: pos.x, top: pos.y, right: "auto", bottom: "auto" }
		: { right: 12, bottom: 80 };

	return (
		<button
			type="button"
			onTouchStart={onTouchStart}
			onTouchMove={onTouchMove}
			onTouchEnd={onTouchEnd}
			onClick={(e) => {
				if (dragRef.current.moved) { e.preventDefault(); dragRef.current.moved = false; return; }
				onClick();
			}}
			aria-label={t("mobile.fab.aria")}
			aria-pressed={active}
			style={style}
			className={cn(
				"fixed z-30 flex h-12 w-12 items-center justify-center rounded-full touch-none select-none",
				"bg-insurance-gold text-insurance-blue-dark",
				"shadow-[0_4px_16px_rgba(201,168,76,0.4)]",
				"active:scale-95",
				"transition-[left,right] duration-300 ease-out",
				"lg:hidden",
				className,
			)}
		>
			<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round">
				<rect x="3" y="3" width="18" height="18" rx="2" />
				<line x1="9" y1="3" x2="9" y2="21" />
				<line x1="3" y1="9" x2="9" y2="9" />
				<line x1="3" y1="15" x2="9" y2="15" />
				<line x1="13" y1="8" x2="19" y2="8" />
				<line x1="13" y1="13" x2="19" y2="13" />
				<line x1="13" y1="18" x2="17" y2="18" />
			</svg>
		</button>
	);
}
