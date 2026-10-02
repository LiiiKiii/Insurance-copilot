"use client";

import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";

interface KPIRingCardProps {
	label: string;
	current: number | null;
	target: number | null;
	unit: string;
	rate: number; // 0-1
	trend?: "up" | "down" | "flat";
	size?: "sm" | "md";
}

function formatValue(value: number | null | undefined, unit: string): string {
	if (value == null || Number.isNaN(value)) return "—";
	if (unit === "HKD") {
		if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
		if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
		return value.toLocaleString();
	}
	if (unit === "%") return `${(value * 100).toFixed(1)}%`;
	return value.toLocaleString();
}

function TrendArrow({ trend }: { trend: "up" | "down" | "flat" }) {
	if (trend === "up") {
		return (
			<svg
				width="12"
				height="12"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				strokeWidth="2.5"
				strokeLinecap="round"
				strokeLinejoin="round"
				className="text-emerald-500"
			>
				<line x1="12" y1="19" x2="12" y2="5" />
				<polyline points="5 12 12 5 19 12" />
			</svg>
		);
	}
	if (trend === "down") {
		return (
			<svg
				width="12"
				height="12"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				strokeWidth="2.5"
				strokeLinecap="round"
				strokeLinejoin="round"
				className="text-red-500"
			>
				<line x1="12" y1="5" x2="12" y2="19" />
				<polyline points="19 12 12 19 5 12" />
			</svg>
		);
	}
	return (
		<svg
			width="12"
			height="12"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			strokeWidth="2.5"
			strokeLinecap="round"
			strokeLinejoin="round"
			className="text-slate-400"
		>
			<line x1="5" y1="12" x2="19" y2="12" />
		</svg>
	);
}

export function KPIRingCard({
	label,
	current,
	target,
	unit,
	rate,
	trend,
	size = "md",
}: KPIRingCardProps) {
	const { t } = useTranslation();
	// Without a target, show a plain current-value card with no ring, so it is not misread as "far behind"
	const hasTarget = target != null && target > 0;

	const ringSize = size === "sm" ? 56 : 72;
	const strokeWidth = size === "sm" ? 5 : 6;
	const radius = (ringSize - strokeWidth) / 2;
	const circumference = 2 * Math.PI * radius;

	const pct = Math.min(rate * 100, 100);
	const offset = circumference * (1 - pct / 100);

	const ringColor =
		pct >= 80
			? "stroke-emerald-500"
			: pct >= 50
				? "stroke-amber-500"
				: "stroke-red-500";

	const bgRingColor = "stroke-slate-200 dark:stroke-slate-700";

	return (
		<div className="flex flex-col items-center gap-2 p-3 rounded-xl border border-slate-200 dark:border-slate-700/50 bg-white dark:bg-slate-800/50 hover:shadow-md transition-shadow">
			{hasTarget ? (
				/* Ring + percentage */
				<div className="relative">
					<svg width={ringSize} height={ringSize} className="-rotate-90">
						<circle
							cx={ringSize / 2}
							cy={ringSize / 2}
							r={radius}
							fill="none"
							strokeWidth={strokeWidth}
							className={bgRingColor}
						/>
						<circle
							cx={ringSize / 2}
							cy={ringSize / 2}
							r={radius}
							fill="none"
							strokeWidth={strokeWidth}
							strokeDasharray={circumference}
							strokeDashoffset={offset}
							strokeLinecap="round"
							className={cn(ringColor, "transition-all duration-700")}
						/>
					</svg>
					<div className="absolute inset-0 flex items-center justify-center">
						<span
							className={cn(
								"font-bold font-mono",
								size === "sm" ? "text-xs" : "text-sm",
								pct >= 80
									? "text-emerald-600 dark:text-emerald-400"
									: pct >= 50
										? "text-amber-600 dark:text-amber-400"
										: "text-red-600 dark:text-red-400",
							)}
						>
							{pct.toFixed(0)}%
						</span>
					</div>
				</div>
			) : (
				/* No target: large current value, no ring or percentage */
				<div
					className="flex items-center justify-center"
					style={{ width: ringSize, height: ringSize }}
				>
					<span
						className={cn(
							"font-bold font-mono text-slate-700 dark:text-slate-200",
							size === "sm" ? "text-base" : "text-lg",
						)}
					>
						{formatValue(current, unit)}
					</span>
				</div>
			)}

			{/* Label */}
			<div className="text-center min-w-0">
				<div className="text-[11px] text-slate-500 dark:text-slate-400 truncate max-w-[90px]">
					{label}
				</div>
				{hasTarget ? (
					<>
						<div className="flex items-center justify-center gap-1 mt-0.5">
							<span className="text-sm font-bold text-slate-800 dark:text-slate-100">
								{formatValue(current, unit)}
							</span>
							{trend && <TrendArrow trend={trend} />}
						</div>
						<div className="text-[10px] text-slate-400 dark:text-slate-500">
							/ {formatValue(target, unit)}
						</div>
					</>
				) : (
					<div className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">
						{t('kpi.noTarget')}
					</div>
				)}
			</div>
		</div>
	);
}
