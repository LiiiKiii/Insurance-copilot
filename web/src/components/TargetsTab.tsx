"use client";

import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { KPIRingCard } from "@/components/KPIRingCard";
import { TeamMemberEditModal } from "@/components/TeamMemberEditModal";
import { useTranslation, type MessageKey } from "@/lib/i18n";

/* ─── Types ─── */

interface TeamMember {
	agent_id: string;
	name_zh: string;
	nickname: string;
	tier: string;
	rank: string;
	sub_count: number;
}

interface Target {
	id: string;
	agent_id: string;
	metric_key: string;
	metric_label: string;
	target_value: number;
	unit: string;
}

interface Metric {
	current: number | null;
	target: number | null;
	unit: string;
	rate?: number | null;
	label?: string;
}

interface Competition {
	id: string;
	name: string;
	type: string;
	target_value: number | null;
	current_value: number | null;
	gap: number | null;
	unit: string;
	deadline: string;
	tags: string[];
	days_remaining?: number;
	feasibility_hint?: string;
	urgency_level?: string;
}

/* ─── Constants ─── */

const TIER_LABEL_KEY: Record<string, MessageKey> = {
	director: "rank.director",
	team_lead: "rank.teamLead",
	senior_agent: "rank.seniorAgent",
	agent: "rank.agent",
};

// Backend-side feasibility-hint enum → translation key. Mirrors the
// CompetitionTab map; unknown values fall through to verbatim render.
const STATUS_KEY: Record<string, MessageKey> = {
	"Achieved": "status.met",
	"Covered": "status.covered",
	"Achievable": "status.achievable",
	"Challenging": "status.challenging",
	"Very difficult": "status.difficult",
};

const TIER_COLORS: Record<string, string> = {
	director:
		"bg-purple-100 text-purple-700 dark:bg-purple-500/10 dark:text-purple-400",
	team_lead: "bg-blue-100 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400",
	senior_agent:
		"bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
	agent: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
};

const TIER_DOT_COLORS: Record<string, string> = {
	director: "bg-purple-500",
	team_lead: "bg-blue-500",
	senior_agent: "bg-emerald-500",
	agent: "bg-slate-400",
};

const CORE_METRICS = [
	"protection_premium",
	"submission_count",
	"conversion_rate",
	"new_clients",
];

/* ─── Helpers ─── */

function formatVal(v: number, unit: string): string {
	if (v == null) return "—";
	if (unit === "HKD")
		return v >= 1_000_000
			? `${(v / 1_000_000).toFixed(1)}M`
			: v >= 1000
				? `${(v / 1000).toFixed(0)}K`
				: String(v);
	if (unit === "%") return `${(v * 100).toFixed(1)}%`;
	return String(v);
}

function formatHKD(n: number | null | undefined): string {
	if (n == null) return "—";
	if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
	if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
	return n.toLocaleString();
}

function formatGap(gap: number | null | undefined, unit: string): string {
	if (gap == null) return "—";
	if (unit === "HKD") return `HKD ${formatHKD(gap)}`;
	return `${gap} ${unit}`;
}

const FEASIBILITY_STYLES: Record<string, string> = {
	Achieved: "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400",
	Covered: "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400",
	Achievable: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
	Challenging:
		"bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
	"Very difficult": "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400",
};

/* ─── SVG Icons (no emoji) ─── */

function IconTarget({ className }: { className?: string }) {
	return (
		<svg
			width="14"
			height="14"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			strokeWidth="2"
			strokeLinecap="round"
			strokeLinejoin="round"
			className={className}
		>
			<circle cx="12" cy="12" r="10" />
			<circle cx="12" cy="12" r="6" />
			<circle cx="12" cy="12" r="2" />
		</svg>
	);
}

function IconUsers({ className }: { className?: string }) {
	return (
		<svg
			width="14"
			height="14"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			strokeWidth="2"
			strokeLinecap="round"
			strokeLinejoin="round"
			className={className}
		>
			<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
			<circle cx="9" cy="7" r="4" />
			<path d="M22 21v-2a4 4 0 0 0-3-3.87" />
			<path d="M16 3.13a4 4 0 0 1 0 7.75" />
		</svg>
	);
}

function IconChevron({
	open,
	className,
}: {
	open: boolean;
	className?: string;
}) {
	return (
		<svg
			width="14"
			height="14"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			strokeWidth="2"
			strokeLinecap="round"
			strokeLinejoin="round"
			className={cn(
				"transition-transform duration-200",
				open ? "rotate-90" : "",
				className,
			)}
		>
			<polyline points="9 18 15 12 9 6" />
		</svg>
	);
}

/* ─── Compact Competition Row ─── */

function CompetitionRow({ comp }: { comp: Competition }) {
	const { t } = useTranslation();
	const days = comp.days_remaining;
	const progress =
		comp.target_value && comp.current_value
			? Math.min((comp.current_value / comp.target_value) * 100, 100)
			: 0;

	return (
		<div className="flex items-center gap-3 px-3 py-2 rounded-lg border border-slate-200/60 dark:border-slate-700/50 bg-white dark:bg-slate-800/30 hover:shadow-sm transition-shadow">
			<div className="flex-1 min-w-0">
				<div className="flex items-center gap-2">
					<span className="text-xs font-medium text-slate-800 dark:text-white truncate">
						{comp.name}
					</span>
					{comp.feasibility_hint && (
						<span
							className={cn(
								"text-[9px] px-1.5 py-0.5 rounded-full font-medium shrink-0",
								FEASIBILITY_STYLES[comp.feasibility_hint] ||
									"bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
							)}
						>
							{STATUS_KEY[comp.feasibility_hint] ? t(STATUS_KEY[comp.feasibility_hint]) : comp.feasibility_hint}
						</span>
					)}
				</div>
				{comp.gap !== null && comp.gap > 0 && (
					<div className="flex items-center gap-3 mt-1">
						<span className="text-[10px] text-slate-500 dark:text-slate-400">
							{t('metric.gap')}{" "}
							<span className="font-mono font-bold text-slate-700 dark:text-slate-200">
								{formatGap(comp.gap, comp.unit)}
							</span>
						</span>
						<div className="flex-1 h-1 bg-slate-100 dark:bg-slate-700/50 rounded-full overflow-hidden max-w-[80px]">
							<div
								className={cn(
									"h-full rounded-full",
									progress >= 80
										? "bg-emerald-500"
										: progress >= 50
											? "bg-amber-500"
											: "bg-red-500",
								)}
								style={{ width: `${progress}%` }}
							/>
						</div>
						<span className="text-[9px] font-mono text-slate-400">
							{progress.toFixed(0)}%
						</span>
					</div>
				)}
			</div>
			<div className="text-right shrink-0">
				<div
					className={cn(
						"text-lg font-bold font-mono tabular-nums",
						comp.urgency_level === "critical"
							? "text-red-600 dark:text-red-400"
							: comp.urgency_level === "important"
								? "text-amber-600 dark:text-amber-400"
								: "text-slate-600 dark:text-slate-300",
					)}
				>
					{days ?? "--"}
				</div>
				<div className="text-[9px] text-slate-400">{t('metric.days')}</div>
			</div>
		</div>
	);
}

/* ─── Mini Progress Bar (6px) ─── */

function MiniProgressBar({ rate, label }: { rate: number; label: string }) {
	const pct = Math.min(rate * 100, 100);
	return (
		<div className="flex items-center gap-1 text-[9px] flex-1 min-w-0">
			<span className="text-slate-400 shrink-0">{label}</span>
			<div className="flex-1 h-1 bg-slate-100 dark:bg-slate-700/50 rounded-full overflow-hidden min-w-[20px]">
				<div
					className={cn(
						"h-full rounded-full",
						pct >= 80
							? "bg-emerald-500"
							: pct >= 50
								? "bg-amber-500"
								: "bg-red-500",
					)}
					style={{ width: `${pct}%` }}
				/>
			</div>
			<span
				className={cn(
					"shrink-0 font-mono font-semibold",
					pct >= 80
						? "text-emerald-600"
						: pct >= 50
							? "text-amber-600"
							: "text-red-600",
				)}
			>
				{pct.toFixed(0)}%
			</span>
		</div>
	);
}

/* ─── Team Member Expanded Detail (read-only, editing via modal) ─── */

function MemberDetail({ memberId }: { memberId: string }) {
	const { t } = useTranslation();
	const [targets, setTargets] = useState<Target[]>([]);
	const [metrics, setMetrics] = useState<Record<string, Metric>>({});
	const [competitions, setCompetitions] = useState<Competition[]>([]);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		let cancelled = false;
		setLoading(true);
		Promise.all([
			fetch(`/api/performance?agent_id=${memberId}`)
				.then((r) => r.json())
				.catch(() => ({ metrics: {} })),
			fetch(`/api/targets?agent_id=${memberId}`)
				.then((r) => r.json())
				.catch(() => ({ data: [] })),
			fetch(`/api/competitions?agent_id=${memberId}`)
				.then((r) => r.json())
				.catch(() => ({ competitions: [] })),
		]).then(([perfData, targetsData, compData]) => {
			if (cancelled) return;
			setMetrics(perfData.metrics || {});
			setTargets(Array.isArray(targetsData.data) ? targetsData.data : []);
			setCompetitions(compData.competitions || []);
			setLoading(false);
		});
		return () => {
			cancelled = true;
		};
	}, [memberId]);

	if (loading) {
		return (
			<div className="py-3 space-y-2">
				{[1, 2].map((i) => (
					<div
						key={i}
						className="h-6 bg-slate-100 dark:bg-slate-800 rounded animate-pulse"
					/>
				))}
			</div>
		);
	}

	// Only real competitions belong in this view (honors have their own tab).
	const comps = competitions.filter((c) => c.type === 'competition');
	const activeComps = comps.filter((c) => c.gap !== null && c.gap > 0);
	const completedComps = comps.filter((c) => c.gap !== null && c.gap <= 0);

	return (
		<div className="pt-3 space-y-3 border-t border-slate-100 dark:border-slate-800 mt-3">
			{/* Targets table - read-only with current/target display */}
			{targets.length > 0 && (
				<div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-hidden">
					<table className="w-full text-xs">
						<thead>
							<tr className="bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400">
								<th className="text-left px-3 py-1.5">{t('tab.targets.col.metricHeader')}</th>
								<th className="text-right px-3 py-1.5">{t('tab.targets.col.currentTarget')}</th>
								<th className="text-right px-3 py-1.5">{t('tab.targets.col.achieved')}</th>
							</tr>
						</thead>
						<tbody>
							{targets.map((target) => {
								const m = metrics[target.metric_key];
								const current = m?.current ?? 0;
								const rate = target.target_value > 0 ? current / target.target_value : 0;
								return (
									<tr
										key={target.id}
										className="border-t border-slate-100 dark:border-slate-800"
									>
										<td className="px-3 py-1.5 text-slate-700 dark:text-slate-200 truncate max-w-[100px]">
											{target.metric_label || target.metric_key}
										</td>
										<td className="px-3 py-1.5 text-right font-mono text-slate-600 dark:text-slate-300">
											{target.unit === "HKD" ? "HKD " : ""}
											{formatVal(current, target.unit)} /{" "}
											{formatVal(target.target_value, target.unit)}
										</td>
										<td className="px-3 py-1.5 text-right">
											<span
												className={cn(
													"font-mono font-semibold",
													rate >= 0.8
														? "text-emerald-600"
														: rate >= 0.5
															? "text-amber-600"
															: "text-red-600",
												)}
											>
												{(rate * 100).toFixed(0)}%
											</span>
										</td>
									</tr>
								);
							})}
						</tbody>
					</table>
				</div>
			)}

			{/* Competitions with current/target/gap format */}
			{activeComps.length > 0 && (
				<div>
					<div className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1.5 px-1">
						{t('tab.competition.activeHeading', { count: activeComps.length })}
					</div>
					<div className="space-y-1.5">
						{activeComps.map((c) => (
							<CompetitionRowEnhanced key={c.id} comp={c} />
						))}
					</div>
				</div>
			)}
			{completedComps.length > 0 && (
				<div>
					<div className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1.5 px-1">
						{t('tab.competition.completedHeading', { count: completedComps.length })}
					</div>
					<div className="space-y-1">
						{completedComps.map((c) => (
							<div
								key={c.id}
								className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-50/50 dark:bg-emerald-500/5 border border-emerald-200/50 dark:border-emerald-500/10"
							>
								<svg
									width="12"
									height="12"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									strokeWidth="2.5"
									strokeLinecap="round"
									strokeLinejoin="round"
									className="text-emerald-500 shrink-0"
								>
									<polyline points="20 6 9 17 4 12" />
								</svg>
								<span className="text-[11px] text-emerald-700 dark:text-emerald-400 font-medium truncate">
									{c.name}
								</span>
							</div>
						))}
					</div>
				</div>
			)}
			{competitions.length === 0 && targets.length === 0 && (
				<div className="text-xs text-slate-400 text-center py-2">{t('tab.targets.empty')}</div>
			)}
		</div>
	);
}

/* ─── Enhanced Competition Row with current/target/gap ─── */

function CompetitionRowEnhanced({ comp }: { comp: Competition }) {
	const { t } = useTranslation();
	const days = comp.days_remaining;
	const progress =
		comp.target_value && comp.current_value
			? Math.min((comp.current_value / comp.target_value) * 100, 100)
			: 0;

	return (
		<div className="flex items-center gap-3 px-3 py-2 rounded-lg border border-slate-200/60 dark:border-slate-700/50 bg-white dark:bg-slate-800/30 hover:shadow-sm transition-shadow">
			<div className="flex-1 min-w-0">
				<div className="flex items-center gap-2">
					<span className="text-xs font-medium text-slate-800 dark:text-white truncate">
						{comp.name}
					</span>
					{comp.feasibility_hint && (
						<span
							className={cn(
								"text-[9px] px-1.5 py-0.5 rounded-full font-medium shrink-0",
								FEASIBILITY_STYLES[comp.feasibility_hint] ||
									"bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
							)}
						>
							{STATUS_KEY[comp.feasibility_hint] ? t(STATUS_KEY[comp.feasibility_hint]) : comp.feasibility_hint}
						</span>
					)}
				</div>
				<div className="flex items-center gap-3 mt-1">
					<span className="text-[10px] text-slate-500 dark:text-slate-400 font-mono">
						{comp.unit === "HKD" ? "HKD " : ""}
						{formatHKD(comp.current_value ?? 0)} /{" "}
						{formatHKD(comp.target_value ?? 0)}
					</span>
					{comp.gap !== null && comp.gap > 0 && (
						<span className="text-[10px] text-red-500 font-medium">
							{t('tab.targets.competition.gap', { amount: formatGap(comp.gap, comp.unit) })}
						</span>
					)}
					<div className="flex-1 h-1 bg-slate-100 dark:bg-slate-700/50 rounded-full overflow-hidden max-w-[60px]">
						<div
							className={cn(
								"h-full rounded-full",
								progress >= 80
									? "bg-emerald-500"
									: progress >= 50
										? "bg-amber-500"
										: "bg-red-500",
							)}
							style={{ width: `${progress}%` }}
						/>
					</div>
					<span className="text-[9px] font-mono text-slate-400">
						{progress.toFixed(0)}%
					</span>
				</div>
			</div>
			<div className="text-right shrink-0">
				<div
					className={cn(
						"text-lg font-bold font-mono tabular-nums",
						(days ?? 999) <= 14
							? "text-red-600 dark:text-red-400"
							: (days ?? 999) <= 30
								? "text-amber-600 dark:text-amber-400"
								: "text-slate-600 dark:text-slate-300",
					)}
				>
					{days ?? "--"}
				</div>
				<div className="text-[9px] text-slate-400">{t('metric.days')}</div>
			</div>
		</div>
	);
}

/* ─── Pencil Edit Icon (larger for card button) ─── */

function IconPencil({ className }: { className?: string }) {
	return (
		<svg
			width="14"
			height="14"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			strokeWidth="2"
			strokeLinecap="round"
			strokeLinejoin="round"
			className={className}
		>
			<path d="M17 3a2.85 2.85 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
			<path d="m15 5 4 4" />
		</svg>
	);
}

/* ─── Team Member Card ─── */

function TeamMemberCard({
	member,
	metrics,
	callerId,
	onTargetSaved,
}: {
	member: TeamMember;
	metrics: Record<string, Metric>;
	callerId: string;
	onTargetSaved: () => void;
}) {
	const { t } = useTranslation();
	const [expanded, setExpanded] = useState(false);
	const [subTeam, setSubTeam] = useState<TeamMember[]>([]);
	const [subExpanded, setSubExpanded] = useState(false);
	const [subMetrics, setSubMetrics] = useState<
		Record<string, Record<string, Metric>>
	>({});
	const [editModalOpen, setEditModalOpen] = useState(false);

	const computeRate = (m: Metric | undefined): number => {
		if (!m) return 0;
		if (m.rate != null) return m.rate;
		if (m.current == null || m.target == null || m.target <= 0) return 0;
		return m.current / m.target;
	};
	const premiumRate = computeRate(metrics["protection_premium"]);
	const countRate = computeRate(metrics["submission_count"]);

	const loadSubTeam = useCallback(() => {
		if (subTeam.length > 0 || member.sub_count === 0) return;
		fetch(`/api/my-team?agent_id=${member.agent_id}`)
			.then((r) => r.json())
			.then((d) => {
				if (d?.ok && Array.isArray(d?.data?.team)) {
					setSubTeam(d.data.team);
					// Load metrics for each sub-member
					d.data.team.forEach((sm: TeamMember) => {
						fetch(`/api/performance?agent_id=${sm.agent_id}`)
							.then((r) => r.json())
							.then((pd) => {
								setSubMetrics((prev) => ({
									...prev,
									[sm.agent_id]: pd?.metrics || {},
								}));
							})
							.catch(() => {});
					});
				}
			})
			.catch(() => {});
	}, [member.agent_id, member.sub_count, subTeam.length]);

	return (
		<>
			<div className="rounded-xl border border-slate-200 dark:border-slate-700/50 bg-white dark:bg-slate-800/50 hover:shadow-md transition-shadow">
				{/* Card header */}
				<div className="flex items-center gap-3 px-4 py-3">
					{/* Avatar */}
					<button
						onClick={() => setExpanded(!expanded)}
						className={cn(
							"w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold text-white shrink-0 cursor-pointer transition-opacity hover:opacity-80",
							TIER_DOT_COLORS[member.tier] || "bg-slate-400",
						)}
					>
						{(member.name_zh || member.agent_id)[0]}
					</button>
					{/* Info column */}
					<div className="flex-1 min-w-0">
						{/* Row 1: name + tier + edit */}
						<div className="flex items-center gap-1.5">
							<button
								onClick={() => setExpanded(!expanded)}
								className="font-medium text-sm text-slate-800 dark:text-white truncate cursor-pointer hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
							>
								{member.name_zh || member.agent_id}
							</button>
							<span
								className={cn(
									"shrink-0 whitespace-nowrap text-[9px] px-1.5 py-px rounded-full font-medium",
									TIER_COLORS[member.tier],
								)}
							>
								{TIER_LABEL_KEY[member.tier] ? t(TIER_LABEL_KEY[member.tier]) : member.tier}
							</span>
							<button
								onClick={(e) => {
									e.stopPropagation();
									setEditModalOpen(true);
								}}
								className="ml-auto p-1 rounded text-slate-300 hover:text-blue-600 hover:bg-slate-100 dark:hover:bg-blue-500/10 dark:hover:text-blue-400 transition-colors cursor-pointer shrink-0"
								title={t('tab.targets.editAria')}
							>
								<IconPencil />
							</button>
						</div>
						{/* Row 2: progress bars inline */}
						<div className="flex items-center gap-3 mt-1">
							<span className="text-[10px] text-slate-400 font-mono">
								{member.agent_id}
							</span>
							<div className="flex-1 flex items-center gap-2">
								<MiniProgressBar rate={premiumRate} label={t('tab.targets.metric.premium')} />
								<MiniProgressBar rate={countRate} label={t('tab.targets.metric.count')} />
							</div>
						</div>
					</div>
				</div>

				{/* Expanded detail */}
				<div
					className={cn(
						"overflow-hidden transition-all duration-300",
						expanded ? "max-h-[2000px] opacity-100" : "max-h-0 opacity-0",
					)}
				>
					<div className="px-4 pb-4">
						{/* Sub-team button */}
						{member.sub_count > 0 && (
							<button
								onClick={(e) => {
									e.stopPropagation();
									setSubExpanded(!subExpanded);
									loadSubTeam();
								}}
								className="mb-2 text-[11px] text-blue-600 dark:text-blue-400 hover:underline cursor-pointer flex items-center gap-1"
							>
								<IconUsers className="w-3 h-3" />
								{t('tab.targets.viewTeam', { count: member.sub_count })}
								<IconChevron open={subExpanded} className="w-3 h-3" />
							</button>
						)}

						{/* Sub-team members (indented) */}
						{subExpanded && subTeam.length > 0 && (
							<div className="ml-4 mb-3 space-y-2 border-l-2 border-slate-200 dark:border-slate-700 pl-3">
								{subTeam.map((sm) => {
									const smMetrics = subMetrics[sm.agent_id] || {};
									const smPremRate = smMetrics["protection_premium"]?.rate ?? 0;
									const smCountRate = smMetrics["submission_count"]?.rate ?? 0;
									return (
										<div
											key={sm.agent_id}
											className="flex items-center gap-2 py-1.5"
										>
											<div
												className={cn(
													"w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-bold text-white shrink-0",
													TIER_DOT_COLORS[sm.tier] || "bg-slate-400",
												)}
											>
												{(sm.name_zh || sm.agent_id)[0]}
											</div>
											<div className="flex-1 min-w-0">
												<div className="flex items-center gap-1.5">
													<span className="text-xs font-medium text-slate-700 dark:text-slate-200 truncate">
														{sm.name_zh || sm.agent_id}
													</span>
													<span
														className={cn(
															"text-[8px] px-1 py-0.5 rounded-full font-medium whitespace-nowrap shrink-0",
															TIER_COLORS[sm.tier],
														)}
													>
														{TIER_LABEL_KEY[sm.tier] ? t(TIER_LABEL_KEY[sm.tier]) : sm.tier}
													</span>
												</div>
											</div>
											<div className="w-28 shrink-0 space-y-0.5">
												<MiniProgressBar rate={smPremRate} label={t('tab.targets.metric.premium')} />
												<MiniProgressBar rate={smCountRate} label={t('tab.targets.metric.count')} />
											</div>
										</div>
									);
								})}
							</div>
						)}

						{expanded && <MemberDetail memberId={member.agent_id} />}
					</div>
				</div>
			</div>

			{/* Edit Modal */}
			{editModalOpen && (
				<TeamMemberEditModal
					agentId={member.agent_id}
					callerAgentId={callerId}
					memberName={member.name_zh || member.agent_id}
					onClose={() => setEditModalOpen(false)}
					onSave={onTargetSaved}
				/>
			)}
		</>
	);
}

/* ─── Sub-Tab: My targets ─── */

function MyGoalsTab({ agentId }: { agentId: string }) {
	const { t } = useTranslation();
	const [metrics, setMetrics] = useState<Record<string, Metric>>({});
	const [targets, setTargets] = useState<Target[]>([]);
	const [competitions, setCompetitions] = useState<Competition[]>([]);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		let cancelled = false;
		setLoading(true);
		Promise.all([
			fetch(`/api/performance?agent_id=${agentId}`)
				.then((r) => r.json())
				.catch(() => ({ metrics: {} })),
			fetch(`/api/targets?agent_id=${agentId}`)
				.then((r) => r.json())
				.catch(() => ({ data: [] })),
			fetch(`/api/competitions?agent_id=${agentId}`)
				.then((r) => r.json())
				.catch(() => ({ competitions: [] })),
		]).then(([perfData, targetsData, compData]) => {
			if (cancelled) return;
			setMetrics(perfData?.metrics || {});
			setTargets(Array.isArray(targetsData?.data) ? targetsData.data : []);
			setCompetitions(
				Array.isArray(compData?.competitions) ? compData.competitions : [],
			);
			setLoading(false);
		});
		return () => {
			cancelled = true;
		};
	}, [agentId]);

	if (loading) {
		return (
			<div className="space-y-3">
				<div className="grid grid-cols-2 gap-3">
					{[1, 2, 3, 4].map((i) => (
						<div
							key={i}
							className="h-28 bg-slate-100 dark:bg-slate-800 rounded-xl animate-pulse"
						/>
					))}
				</div>
				{[1, 2].map((i) => (
					<div
						key={i}
						className="h-16 bg-slate-100 dark:bg-slate-800 rounded-xl animate-pulse"
					/>
				))}
			</div>
		);
	}

	// Only real competitions belong in this view (honors have their own tab).
	const comps = competitions.filter((c) => c.type === 'competition');
	const activeComps = comps.filter((c) => c.gap !== null && c.gap > 0);
	const completedComps = comps.filter((c) => c.gap !== null && c.gap <= 0);

	return (
		<div className="space-y-4">
			{/* KPI Ring Cards - 2x2 grid */}
			<div className="grid grid-cols-2 gap-3">
				{CORE_METRICS.map((key) => {
					const m = metrics[key];
					const target = targets.find((tg) => tg.metric_key === key);
					if (!m) return null;
					const targetValue = target?.target_value ?? m.target;
					const rate =
						targetValue != null && targetValue > 0 && m.current != null
							? m.current / targetValue
							: 0;
					const fallbackLabel =
						key === "submission_count"
							? t('tab.performance.metric.submissionCount')
							: key === "conversion_rate"
								? t('tab.targets.metric.conversionRate')
								: key === "new_clients"
									? t('tab.performance.metric.newClients')
									: key;
					return (
						<KPIRingCard
							key={key}
							label={target?.metric_label || m.label || fallbackLabel}
							current={m.current}
							target={targetValue}
							unit={m.unit}
							rate={rate}
							trend={rate >= 0.8 ? "up" : rate < 0.5 ? "down" : "flat"}
							size="sm"
						/>
					);
				})}
			</div>

			{/* Competitions - compact rows */}
			{activeComps.length > 0 && (
				<div>
					<div className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-2 px-1">
						{t('tab.competition.activeHeading', { count: activeComps.length })}
					</div>
					<div className="space-y-2">
						{activeComps.map((c) => (
							<CompetitionRow key={c.id} comp={c} />
						))}
					</div>
				</div>
			)}

			{completedComps.length > 0 && (
				<div>
					<div className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1.5 px-1">
						{t('tab.competition.completedHeading', { count: completedComps.length })}
					</div>
					<div className="space-y-1">
						{completedComps.map((c) => (
							<div
								key={c.id}
								className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-50/50 dark:bg-emerald-500/5 border border-emerald-200/50 dark:border-emerald-500/10"
							>
								<svg
									width="12"
									height="12"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									strokeWidth="2.5"
									strokeLinecap="round"
									strokeLinejoin="round"
									className="text-emerald-500 shrink-0"
								>
									<polyline points="20 6 9 17 4 12" />
								</svg>
								<span className="text-[11px] text-emerald-700 dark:text-emerald-400 font-medium truncate">
									{c.name}
								</span>
							</div>
						))}
					</div>
				</div>
			)}

			{competitions.length === 0 && Object.keys(metrics).length === 0 && (
				<div className="flex items-center justify-center h-24 text-slate-400 text-sm">
					{t('tab.targets.empty.my')}
				</div>
			)}
		</div>
	);
}

/* ─── Sub-Tab: Team targets ─── */

function TeamGoalsTab({ agentId }: { agentId: string }) {
	const { t } = useTranslation();
	const [team, setTeam] = useState<TeamMember[]>([]);
	const [memberMetrics, setMemberMetrics] = useState<
		Record<string, Record<string, Metric>>
	>({});
	const [loading, setLoading] = useState(true);
	const [refreshKey, setRefreshKey] = useState(0);

	// Load team list
	useEffect(() => {
		let cancelled = false;
		setLoading(true);
		fetch(`/api/my-team?agent_id=${agentId}`)
			.then((r) => r.json())
			.then((d) => {
				if (cancelled) return;
				if (d?.ok && Array.isArray(d?.data?.team)) {
					setTeam(d.data.team);
					// Load performance for each member in parallel
					d.data.team.forEach((m: TeamMember) => {
						fetch(`/api/performance?agent_id=${m.agent_id}`)
							.then((r) => r.json())
							.then((pd) => {
								if (cancelled) return;
								setMemberMetrics((prev) => ({
									...prev,
									[m.agent_id]: pd?.metrics || {},
								}));
							})
							.catch(() => {});
					});
				}
				setLoading(false);
			})
			.catch(() => {
				if (!cancelled) setLoading(false);
			});
		return () => {
			cancelled = true;
		};
	}, [agentId, refreshKey]);

	if (loading) {
		return (
			<div className="space-y-3">
				<div className="h-16 bg-slate-100 dark:bg-slate-800 rounded-xl animate-pulse" />
				{[1, 2, 3].map((i) => (
					<div
						key={i}
						className="h-20 bg-slate-100 dark:bg-slate-800 rounded-xl animate-pulse"
					/>
				))}
			</div>
		);
	}

	if (team.length === 0) {
		return (
			<div className="flex flex-col items-center justify-center h-32 text-slate-400">
				<IconUsers className="w-8 h-8 mb-2 opacity-30" />
				<p className="text-sm">{t('tab.targets.team.empty')}</p>
				<p className="text-xs mt-1">{t('tab.targets.team.emptyHint')}</p>
			</div>
		);
	}

	// Team summary stats
	let totalPremiumCurrent = 0,
		totalPremiumTarget = 0;
	let totalCountCurrent = 0,
		totalCountTarget = 0;
	let memberCount = 0;
	let totalRate = 0;

	team.forEach((m) => {
		const mm = memberMetrics[m.agent_id];
		if (!mm) return;
		const pp = mm["protection_premium"];
		const sc = mm["submission_count"];
		if (pp && pp.current != null && pp.target != null) {
			totalPremiumCurrent += pp.current;
			totalPremiumTarget += pp.target;
		}
		if (sc && sc.current != null && sc.target != null) {
			totalCountCurrent += sc.current;
			totalCountTarget += sc.target;
		}
		// Average rate across core metrics
		let mRate = 0,
			mCount = 0;
		CORE_METRICS.forEach((k) => {
			const metric = mm[k];
			if (
				metric &&
				metric.current != null &&
				metric.target != null &&
				metric.target > 0
			) {
				mRate += metric.current / metric.target;
				mCount++;
			}
		});
		if (mCount > 0) {
			totalRate += mRate / mCount;
			memberCount++;
		}
	});

	const avgRate = memberCount > 0 ? totalRate / memberCount : 0;

	return (
		<div className="space-y-4">
			{/* Team summary */}
			<div className="grid grid-cols-3 gap-2">
				<div className="rounded-xl border border-slate-200 dark:border-slate-700/50 bg-white dark:bg-slate-800/50 p-3 text-center">
					<div className="text-[10px] text-slate-500 dark:text-slate-400">
						{t('tab.targets.team.totalPremium')}
					</div>
					<div className="text-sm font-bold font-mono text-slate-800 dark:text-white mt-1">
						{formatHKD(totalPremiumCurrent)}
					</div>
					<div className="text-[9px] text-slate-400">
						/ {formatHKD(totalPremiumTarget)}
					</div>
				</div>
				<div className="rounded-xl border border-slate-200 dark:border-slate-700/50 bg-white dark:bg-slate-800/50 p-3 text-center">
					<div className="text-[10px] text-slate-500 dark:text-slate-400">
						{t('tab.targets.team.totalCount')}
					</div>
					<div className="text-sm font-bold font-mono text-slate-800 dark:text-white mt-1">
						{totalCountCurrent}
					</div>
					<div className="text-[9px] text-slate-400">/ {totalCountTarget}</div>
				</div>
				<div className="rounded-xl border border-slate-200 dark:border-slate-700/50 bg-white dark:bg-slate-800/50 p-3 text-center">
					<div className="text-[10px] text-slate-500 dark:text-slate-400">
						{t('tab.targets.team.avgAchievement')}
					</div>
					<div
						className={cn(
							"text-sm font-bold font-mono mt-1",
							avgRate >= 0.8
								? "text-emerald-600"
								: avgRate >= 0.5
									? "text-amber-600"
									: "text-red-600",
						)}
					>
						{(avgRate * 100).toFixed(0)}%
					</div>
					<div className="text-[9px] text-slate-400">{t('tab.targets.team.peopleCount', { count: team.length })}</div>
				</div>
			</div>

			{/* Team member cards */}
			<div className="space-y-2">
				{team.map((m) => (
					<TeamMemberCard
						key={m.agent_id}
						member={m}
						metrics={memberMetrics[m.agent_id] || {}}
						callerId={agentId}
						onTargetSaved={() => setRefreshKey((k) => k + 1)}
					/>
				))}
			</div>
		</div>
	);
}

/* ─── Main TargetsTab ─── */

interface TargetsTabProps {
	agentId: string;
}

type SubTab = "my" | "team";

export function TargetsTab({ agentId }: TargetsTabProps) {
	const [activeTab, setActiveTab] = useState<SubTab>("my");

	return (
		<div className="p-4 space-y-4">
			<div className="grid grid-cols-2 rounded-lg bg-slate-100 p-1 dark:bg-slate-800">
				<button
					type="button"
					onClick={() => setActiveTab("my")}
					className={cn(
						"flex items-center justify-center gap-2 rounded-md px-3 py-2 text-xs font-medium transition-colors",
						activeTab === "my"
							? "bg-white text-insurance-blue shadow-sm dark:bg-slate-700 dark:text-white"
							: "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200",
					)}
				>
					<IconTarget />
					My Targets
				</button>
				<button
					type="button"
					onClick={() => setActiveTab("team")}
					className={cn(
						"flex items-center justify-center gap-2 rounded-md px-3 py-2 text-xs font-medium transition-colors",
						activeTab === "team"
							? "bg-white text-insurance-blue shadow-sm dark:bg-slate-700 dark:text-white"
							: "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200",
					)}
				>
					<IconUsers />
					Team Targets
				</button>
			</div>

			{activeTab === "my" ? (
				<MyGoalsTab agentId={agentId} />
			) : (
				<TeamGoalsTab agentId={agentId} />
			)}
		</div>
	);
}
