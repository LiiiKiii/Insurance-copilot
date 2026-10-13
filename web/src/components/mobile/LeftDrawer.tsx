"use client";

import * as React from "react";
import { Drawer as DrawerPrimitive } from "vaul";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";

interface LeftDrawerProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	children: React.ReactNode;
	title?: string;
	className?: string;
}

export function LeftDrawer({
	open,
	onOpenChange,
	children,
	title,
	className,
}: LeftDrawerProps) {
	const { t } = useTranslation();
	const resolvedTitle = title ?? t("mobile.drawer.title");
	const debug = process.env.NEXT_PUBLIC_DEBUG_MOBILE === "1";

	// Auto-close on crossing to lg breakpoint — drawer is mobile-only
	React.useEffect(() => {
		const mql = window.matchMedia("(min-width: 1024px)");
		const onChange = (e: MediaQueryListEvent | MediaQueryList) => {
			if (e.matches && open) {
				if (debug) console.debug("[LeftDrawer] auto-close on lg+");
				onOpenChange(false);
			}
		};
		onChange(mql);
		mql.addEventListener("change", onChange);
		return () => mql.removeEventListener("change", onChange);
	}, [open, onOpenChange, debug]);

	// Don't mount on desktop — avoids stale portal + overlay when drawer state drifts
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
		if (debug) console.debug("[LeftDrawer]", next ? "open" : "close");
		onOpenChange(next);
	};

	return (
		<DrawerPrimitive.Root
			open={open}
			onOpenChange={handleOpenChange}
			direction="left"
		>
			<DrawerPrimitive.Portal>
				<DrawerPrimitive.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
				<DrawerPrimitive.Content
					className={cn(
						"fixed inset-y-0 left-0 z-50 flex h-full w-[min(280px,85vw)] flex-col outline-none overflow-hidden",
						"bg-gradient-to-b from-insurance-blue-dark via-insurance-blue to-[#102640]",
						"border-r border-insurance-gold/20",
						className,
					)}
				>
					<div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-insurance-gold-dark via-insurance-gold-light to-insurance-gold" />
					<DrawerPrimitive.Title className="sr-only">
						{resolvedTitle}
					</DrawerPrimitive.Title>
					<DrawerPrimitive.Description className="sr-only">
						{t("mobile.drawer.description")}
					</DrawerPrimitive.Description>
					{children}
				</DrawerPrimitive.Content>
			</DrawerPrimitive.Portal>
		</DrawerPrimitive.Root>
	);
}
