"use client";

import * as React from "react";
import { Drawer as DrawerPrimitive } from "vaul";
import { cn } from "@/lib/utils";
import { PerformanceTab } from "../PerformanceTab";
import { CompetitionTab } from "../CompetitionTab";
import { HonorsTab } from "../HonorsTab";
import { useTranslation, type MessageKey } from "@/lib/i18n";

export type DataTabKey = "performance" | "competition" | "honors";

interface DataBottomSheetProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	agentId: string;
	activeTab: DataTabKey;
	onActiveTabChange: (tab: DataTabKey) => void;
}

const TABS: Array<{ key: DataTabKey; labelKey: MessageKey; icon: React.ReactNode }> = [
	{
		key: "competition",
		labelKey: "tab.competition",
		icon: (
			<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
				<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" />
				<path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" />
				<path d="M4 22h16" />
				<path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22" />
				<path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22" />
				<path d="M18 2H6v7a6 6 0 0 0 12 0V2Z" />
			</svg>
		),
	},
	{
		key: "honors",
		labelKey: "tab.honors",
		icon: (
			<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
				<circle cx="12" cy="8" r="7" />
				<polyline points="8.21 13.89 7 22 12 19 17 22 15.79 13.88" />
			</svg>
		),
	},
	{
		key: "performance",
		labelKey: "tab.targets",
		icon: (
			<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
				<circle cx="12" cy="12" r="10" />
				<circle cx="12" cy="12" r="6" />
				<circle cx="12" cy="12" r="2" />
			</svg>
		),
	},
];

export function DataBottomSheet({
	open,
	onOpenChange,
	agentId,
	activeTab,
	onActiveTabChange,
}: DataBottomSheetProps) {
	const { t } = useTranslation();
	const snapPoints = [0.3, 0.6, 0.9];
	const [snap, setSnap] = React.useState<number | string | null>(0.6);

	const debug = process.env.NEXT_PUBLIC_DEBUG_MOBILE === "1";

	// Auto-close on crossing to lg — sheet is mobile-only
	React.useEffect(() => {
		const mql = window.matchMedia("(min-width: 1024px)");
		const onChange = () => {
			if (mql.matches && open) onOpenChange(false);
		};
		onChange();
		mql.addEventListener("change", onChange);
		return () => mql.removeEventListener("change", onChange);
	}, [open, onOpenChange]);

	// Don't mount on desktop
	const [isDesktop, setIsDesktop] = React.useState(false);
	React.useEffect(() => {
		const mql = window.matchMedia("(min-width: 1024px)");
		const update = () => setIsDesktop(mql.matches);
		update();
		mql.addEventListener("change", update);
		return () => mql.removeEventListener("change", update);
	}, []);

	if (isDesktop) return null;

	const handleOpenChange = (next: boolean) => {
		if (debug) console.debug("[DataBottomSheet]", next ? "open" : "close");
		if (next) setSnap(0.6);
		onOpenChange(next);
	};

	return (
		<DrawerPrimitive.Root
			open={open}
			onOpenChange={handleOpenChange}
			snapPoints={snapPoints}
			activeSnapPoint={snap}
			setActiveSnapPoint={(s) => {
				if (debug) console.debug("[DataBottomSheet] snap", s);
				setSnap(s);
			}}
		>
			<DrawerPrimitive.Portal>
				<DrawerPrimitive.Overlay className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm" />
				<DrawerPrimitive.Content
					className={cn(
						"fixed inset-x-0 bottom-0 z-50 flex flex-col outline-none",
						"h-[96vh] h-[96dvh] rounded-t-3xl",
						"bg-white dark:bg-slate-900",
						"border-t border-insurance-gold/30",
						"shadow-[0_-24px_55px_rgba(15,23,42,0.2)]",
					)}
				>
					<DrawerPrimitive.Title className="sr-only">
						{t("mobile.bottomSheet.title")}
					</DrawerPrimitive.Title>
					<DrawerPrimitive.Description className="sr-only">
						{t("mobile.bottomSheet.description")}
					</DrawerPrimitive.Description>

					{/* Drag handle */}
					<div className="mx-auto mt-2 mb-1 h-1 w-10 shrink-0 rounded-full bg-insurance-gold/40" />

					{/* Tab header */}
					<div className="flex shrink-0 border-b border-slate-200/70 dark:border-slate-700/50">
						{TABS.map((tab) => (
							<button
								key={tab.key}
								onClick={() => {
									if (debug) console.debug("[DataBottomSheet] tab", tab.key);
									onActiveTabChange(tab.key);
								}}
								className={cn(
									"flex-1 min-h-11 px-2 py-3 text-xs font-semibold transition-colors cursor-pointer",
									"flex items-center justify-center gap-1.5",
									activeTab === tab.key
										? "text-insurance-blue dark:text-insurance-gold border-b-2 border-insurance-blue dark:border-insurance-gold"
										: "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300",
								)}
							>
								{tab.icon}
								{t(tab.labelKey)}
							</button>
						))}
					</div>

					{/* Tab content — bottom padding = OS safe-area (iOS home indicator) + 4rem
					    buffer for mobile browser chrome (URL bar / tab switcher) which often
					    overlays content without being reported by env(safe-area-inset-bottom). */}
					<div className="flex-1 min-h-0 overflow-y-auto overscroll-contain pb-[calc(env(safe-area-inset-bottom)+4rem)]">
						{activeTab === "performance" && <PerformanceTab agentId={agentId} />}
						{activeTab === "honors" && <HonorsTab agentId={agentId} />}
						{activeTab === "competition" && <CompetitionTab agentId={agentId} />}
					</div>
				</DrawerPrimitive.Content>
			</DrawerPrimitive.Portal>
		</DrawerPrimitive.Root>
	);
}
