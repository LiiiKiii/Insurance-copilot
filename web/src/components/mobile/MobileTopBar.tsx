"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";

interface MobileTopBarProps {
	title: string;
	subtitle?: string;
	onMenuClick: () => void;
	rightSlot?: ReactNode;
	className?: string;
}

export function MobileTopBar({
	title,
	subtitle,
	onMenuClick,
	rightSlot,
	className,
}: MobileTopBarProps) {
	const { t } = useTranslation();
	return (
		<header
			className={cn(
				"sticky top-0 z-40 h-14 lg:hidden",
				"bg-insurance-blue-dark/90 backdrop-blur-xl",
				"border-b border-white/5",
				className,
			)}
		>
			<div className="page-gold-stripe absolute inset-x-0 bottom-0 h-[1px]" />
			<div className="relative flex h-full items-center justify-between gap-2 px-3">
				<button
					onClick={onMenuClick}
					aria-label={t("mobileTopBar.menu.aria")}
					className="flex h-11 w-11 items-center justify-center -ml-1.5 rounded-lg text-white/80 hover:text-white hover:bg-white/10 active:bg-white/15 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-insurance-gold"
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						width="22"
						height="22"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						strokeWidth="2"
						strokeLinecap="round"
						strokeLinejoin="round"
					>
						<line x1="4" y1="7" x2="20" y2="7" />
						<line x1="4" y1="12" x2="20" y2="12" />
						<line x1="4" y1="17" x2="20" y2="17" />
					</svg>
				</button>

				<div className="flex-1 min-w-0 text-center">
					<h1 className="font-display text-base font-semibold text-white tracking-tight truncate leading-tight">
						{title}
					</h1>
					{subtitle && (
						<p className="text-[10px] text-insurance-gold-light truncate leading-tight">
							{subtitle}
						</p>
					)}
				</div>

				<div className="flex items-center gap-1 min-w-[44px] justify-end">
					{rightSlot}
				</div>
			</div>
		</header>
	);
}
