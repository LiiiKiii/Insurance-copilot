"use client";

import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { MessageBubble } from "./MessageBubble";
import { ThinkingProcess } from "./ThinkingProcess";
import {
	TargetIcon,
	BarChartIcon,
	SearchIcon,
	ClipboardIcon,
	ClockIcon,
} from "./Icons";
import { DailyBriefingModal } from "./DailyBriefingModal";
import {
	fetchBriefingSummary,
	fetchTodayBriefing,
	type BriefingSummary,
	type BriefingActionItem,
} from "@/lib/briefingApi";
import type { ChatMessage, RetrievalMode } from "@/lib/chatTypes";
import { VoiceButton, type VoiceStatus } from './chat/VoiceButton'
import { FileButton } from './chat/FileButton'
import { UploadPill } from './chat/UploadPill'
import type { UploadPillState } from './chat/UploadPill'
import { useTranslation, type MessageKey } from '@/lib/i18n'
import { authenticatedFetch as fetch, authHeaders } from '@/lib/auth'

interface ChatInterfaceProps {
	messages: ChatMessage[];
	isTyping: boolean;
	agentId?: string;
	status: "connecting" | "connected" | "disconnected";
	onSend: (
		message: string,
		opts?: {
			uploadIds?: string[];
			attachmentLabels?: string[];
			retrievalMode?: RetrievalMode;
		},
	) => void;
	onOpenConfig?: () => void;
	apiConfigured?: boolean;
	sessionKey: string;
}

// SPEC B-01~B-05 Case — question templates. The actual strings live in
// the i18n message tables; only the icon + key references are static.
interface QuickQuestion {
	icon: string;
	qKey: MessageKey;
	descKey: MessageKey;
}

const QUICK_QUESTIONS: QuickQuestion[] = [
	{ icon: "target", qKey: "chat.quick.b01.q", descKey: "chat.quick.b01.desc" },
	{ icon: "clock", qKey: "chat.quick.b02.q", descKey: "chat.quick.b02.desc" },
	{ icon: "search", qKey: "chat.quick.b03.q", descKey: "chat.quick.b03.desc" },
	{ icon: "clipboard", qKey: "chat.quick.b04.q", descKey: "chat.quick.b04.desc" },
	{ icon: "chart", qKey: "chat.quick.b05.q", descKey: "chat.quick.b05.desc" },
];

function QuickCardIcon({ icon, size = 16 }: { icon: string; size?: number }) {
	const cls = "text-insurance-gold";
	switch (icon) {
		case "target":
			return <TargetIcon className={cls} size={size} />;
		case "chart":
			return <BarChartIcon className={cls} size={size} />;
		case "search":
			return <SearchIcon className={cls} size={size} />;
		case "clipboard":
			return <ClipboardIcon className={cls} size={size} />;
		case "clock":
			return <ClockIcon className={cls} size={size} />;
		default:
			return null;
	}
}

export function ChatInterface({
	messages,
	isTyping,
	status,
	onSend,
	onOpenConfig,
	apiConfigured,
	agentId,
	sessionKey,
}: ChatInterfaceProps) {
	const { t } = useTranslation();
	// Fetch current agent name for personalized questions
	const [agentName, setAgentName] = useState<string>("");
	useEffect(() => {
		if (!agentId) return;
		fetch(`/api/agent-info?agent_id=${encodeURIComponent(agentId)}`, { headers: authHeaders() })
			.then((r) => r.json())
			.then((d) => setAgentName(d?.data?.nickname || d?.data?.name_zh || d?.data?.name_en || ""))
			.catch(() => {});
	}, [agentId]);
	const [input, setInput] = useState("");
	const [voiceError, setVoiceError] = useState<string | null>(null);
	const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);
	const [pendingUploads, setPendingUploads] = useState<UploadPillState[]>([]);
	const [isInputFocused, setIsInputFocused] = useState(false);
	const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>("keyword");
	const [vectorCapability, setVectorCapability] = useState<{
		available: boolean;
		reason: string | null;
	}>({ available: false, reason: null });
	const [capabilityLoading, setCapabilityLoading] = useState(true);

	useEffect(() => {
		const controller = new AbortController();
		fetch("/api/retrieval/capabilities", { signal: controller.signal })
			.then(async (response) => {
				if (!response.ok) throw new Error(`HTTP ${response.status}`);
				return response.json();
			})
			.then((body) => {
				const available = body?.vector?.available === true;
				setVectorCapability({
					available,
					reason:
						typeof body?.vector?.reason === "string"
							? body.vector.reason
							: null,
				});
				if (!available) setRetrievalMode("keyword");
			})
			.catch((error) => {
				if (error instanceof DOMException && error.name === "AbortError") return;
				setVectorCapability({ available: false, reason: null });
				setRetrievalMode("keyword");
			})
			.finally(() => {
				if (!controller.signal.aborted) setCapabilityLoading(false);
			});
		return () => controller.abort();
	}, []);

	const removeUpload = (uploadId: string) =>
		setPendingUploads((prev: UploadPillState[]) =>
			prev.filter((p: UploadPillState) => p.uploadId !== uploadId),
		);

	const updateUpload = (next: UploadPillState) =>
		setPendingUploads((prev: UploadPillState[]) =>
			prev.map((p: UploadPillState) => (p.uploadId === next.uploadId ? next : p)),
		);
	useEffect(() => {
		if (!voiceError) return;
		const id = window.setTimeout(() => setVoiceError(null), 4000);
		return () => window.clearTimeout(id);
	}, [voiceError]);
	const messagesEndRef = useRef<HTMLDivElement>(null);
	const textareaRef = useRef<HTMLTextAreaElement>(null);

	// Drive the "keyboard up" state (which hides the voice/file buttons on
	// mobile to make room) from the visual viewport's OWN baseline height —
	// the tallest it has been, i.e. no keyboard.
	useEffect(() => {
		const vv = typeof window !== "undefined" ? window.visualViewport : undefined;
		if (!vv) return;
		let baseline = vv.height;
		const handler = () => {
			baseline = Math.max(baseline, vv.height);
			const keyboardUp = baseline - vv.height > 120;
			setIsInputFocused(keyboardUp);
		};
		vv.addEventListener("resize", handler);
		return () => vv.removeEventListener("resize", handler);
	}, []);

	// ── Daily briefing ────────────────────────────────────────────────────
	const [briefingOpen, setBriefingOpen] = useState(false);
	const [briefingSummary, setBriefingSummary] =
		useState<BriefingSummary | null>(null);
	const [topActions, setTopActions] = useState<BriefingActionItem[]>([]);
	const refreshBriefingSummary = () => {
		if (!agentId) return;
		fetchBriefingSummary(agentId)
			.then(setBriefingSummary)
			.catch(() => {});
	};
	useEffect(() => {
		refreshBriefingSummary();
		if (agentId) {
			fetchTodayBriefing(agentId)
				.then((data) =>
					setTopActions((data.briefing?.action_items || []).slice(0, 5)),
				)
				.catch(() => {});
		}
	}, [agentId]);

	useEffect(() => {
		messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
	}, [messages, isTyping]);

	const handleSend = () => {
		const trimmed = input.trim();
		const ready = pendingUploads.filter((p: UploadPillState) => p.status === "ready");
		const stillParsing = pendingUploads.some((p: UploadPillState) => p.status === "parsing");
		if (stillParsing) return;
		if (!trimmed && ready.length === 0) return;
		if (status !== "connected" || isTyping) return;

		onSend(trimmed, {
			uploadIds: ready.map((p: UploadPillState) => p.uploadId),
			attachmentLabels: ready.map((p: UploadPillState) => p.filename),
			retrievalMode,
		});
		setInput("");
		setPendingUploads([]);
		if (textareaRef.current) {
			textareaRef.current.style.height = "auto";
		}
	};

	const sendDirectly = (text: string) => {
		const trimmed = text.trim()
		const ready = pendingUploads.filter((p: UploadPillState) => p.status === "ready");
		if (status !== 'connected' || isTyping) return
		if (!trimmed && ready.length === 0) return
		onSend(trimmed, {
			uploadIds: ready.map((p: UploadPillState) => p.uploadId),
			attachmentLabels: ready.map((p: UploadPillState) => p.filename),
			retrievalMode,
		})
		setPendingUploads([])
	}

	const handleKeyDown = (e: React.KeyboardEvent) => {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			handleSend();
		}
	};

	const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
		setInput(e.target.value);
		const el = e.target;
		el.style.height = "auto";
		el.style.height = Math.min(el.scrollHeight, 160) + "px";
	};

	const isEmpty = messages.length === 0;

	return (
		<div className="stagger-enter stagger-enter-2 flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden bg-gradient-to-b from-slate-50 to-white dark:from-[#0f172a] dark:to-slate-900">
			<header className="stagger-enter stagger-enter-2 flex items-center justify-between gap-2 px-4 md:px-6 py-3 border-b border-slate-200/80 dark:border-slate-800 bg-white/70 dark:bg-slate-950/75 backdrop-blur-xl">
				<div className="flex items-center gap-2.5 min-w-0 flex-1">
					<h2 className="font-display text-base md:text-xl font-semibold text-insurance-blue dark:text-white tracking-tight truncate">
						{t("chat.header.title")}
					</h2>
					{/* Connection dot — minimal on mobile, badge on desktop */}
					<span className="flex items-center gap-1.5 shrink-0">
						<span className={cn(
							"relative flex h-2 w-2",
							status === "connected" && "text-emerald-500",
							status === "connecting" && "text-amber-500",
							status === "disconnected" && "text-red-500",
						)}>
							{status === "connected" && (
								<span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
							)}
							<span className={cn(
								"relative inline-flex h-2 w-2 rounded-full",
								status === "connected" && "bg-emerald-500",
								status === "connecting" && "bg-amber-500 animate-pulse",
								status === "disconnected" && "bg-red-500",
							)} />
						</span>
						<span className="hidden sm:inline text-[11px] font-medium text-slate-500 dark:text-slate-400">
							{status === "connected" && t("connection.connected")}
							{status === "connecting" && t("connection.connecting")}
							{status === "disconnected" && t("connection.disconnected")}
						</span>
					</span>
				</div>
				<div className="flex items-center gap-2">
					{/* API Config button — hide on mobile (MobileTopBar has it), show on sm+ */}
					{onOpenConfig && (
						<button
							onClick={onOpenConfig}
							title={t("apiConfig.title")}
							className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors border ${
								apiConfigured
									? "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
									: "border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400 hover:bg-amber-100 animate-pulse"
							}`}
						>
							{apiConfigured ? (
								<svg
									className="w-3.5 h-3.5"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									strokeWidth={2}
									strokeLinecap="round"
									strokeLinejoin="round"
								>
									<circle cx="7.5" cy="15.5" r="5.5" />
									<path d="M21 2l-9.6 9.6" />
									<path d="M15.5 7.5l3 3L22 7l-3-3" />
								</svg>
							) : (
								<svg
									className="w-3.5 h-3.5"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									strokeWidth={2}
									strokeLinecap="round"
									strokeLinejoin="round"
								>
									<circle cx="12" cy="12" r="3" />
									<path d="M19.07 4.93l-1.41 1.41M4.93 4.93l1.41 1.41M19.07 19.07l-1.41-1.41M4.93 19.07l1.41-1.41M12 2v2M12 20v2M2 12h2M20 12h2" />
								</svg>
							)}
							<span>{apiConfigured ? t("apiConfig.configured.aria") : t("apiConfig.notConfigured.aria")}</span>
						</button>
					)}
				</div>
			</header>

			{agentId && (
				<DailyBriefingModal
					agentId={agentId}
					open={briefingOpen}
					onClose={() => setBriefingOpen(false)}
					onAcknowledged={refreshBriefingSummary}
				/>
			)}

			<div className="stagger-enter stagger-enter-3 flex-1 min-h-0 overflow-y-auto px-4 md:px-6 py-4 scroll-smooth">
				{isEmpty ? (
					<div className="flex flex-col max-w-4xl mx-auto min-h-full my-auto">
						<div className="hero-gradient-bg dot-pattern-bg noise-overlay border-gradient relative overflow-hidden rounded-2xl px-4 py-6 sm:px-8 sm:py-12 shadow-[0_24px_50px_rgba(15,23,42,0.08)] dark:shadow-[0_24px_55px_rgba(2,6,23,0.5)]">
							{/* Signature: top gold hairline + top-right "AI Coach" mark */}
							<div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-[1.5px] bg-gradient-to-r from-transparent via-insurance-gold/80 to-transparent" />
							<div aria-hidden="true" className="pointer-events-none absolute right-4 top-4 flex items-center gap-1.5 z-20">
								<span className="h-px w-5 bg-gradient-to-r from-transparent to-insurance-gold/80" />
								<span className="text-[9px] font-mono uppercase tracking-[0.2em] text-insurance-gold/90">AI Coach</span>
							</div>
							<svg
								aria-hidden="true"
								className="pointer-events-none absolute -left-16 -top-10 h-48 w-48 opacity-25 text-insurance-gold dark:opacity-30 hidden sm:block"
								viewBox="0 0 200 200"
								fill="none"
							>
								<circle
									cx="100"
									cy="100"
									r="88"
									stroke="currentColor"
									strokeWidth="2"
									strokeDasharray="7 7"
								/>
								<path
									d="M52 120 C80 80 122 148 150 104"
									stroke="currentColor"
									strokeWidth="4"
									strokeLinecap="round"
								/>
							</svg>
							<svg
								aria-hidden="true"
								className="pointer-events-none absolute -right-10 bottom-0 h-52 w-52 opacity-20 text-insurance-blue dark:text-insurance-gold dark:opacity-30 hidden sm:block"
								viewBox="0 0 200 200"
								fill="none"
							>
								<path
									d="M42 150V70m32 80V52m32 98v-62m32 62V85"
									stroke="currentColor"
									strokeWidth="10"
									strokeLinecap="round"
								/>
								<path
									d="M100 28l42 22v30c0 32-18 56-42 72-24-16-42-40-42-72V50l42-22Z"
									stroke="currentColor"
									strokeWidth="6"
									strokeLinejoin="round"
								/>
							</svg>

							<div className="relative z-10 text-center sm:text-left max-w-2xl">
								<h3 className="font-display text-xl sm:text-3xl md:text-4xl font-semibold mb-1.5 sm:mb-3 text-gradient-gold leading-tight">
									{t("chat.empty.title")}
								</h3>
								<p className="hidden sm:block text-sm md:text-base text-slate-600 dark:text-slate-300 leading-relaxed mb-3 sm:mb-4">
									{t("chat.empty.subtitle")}
								</p>
							</div>

							{/* Briefing previews - full width, aligned with question cards below */}
							<div className="relative z-10 mb-4 space-y-3">
								{/* Compliance reminder — collapsible */}
								{(briefingSummary?.compliance_warnings?.length ?? 0) > 0 && (
									<details className="group relative overflow-hidden rounded-xl border border-rose-200 dark:border-rose-800/60 bg-gradient-to-br from-rose-50 via-rose-50/70 to-transparent dark:from-rose-950/40 dark:via-rose-950/20 dark:to-transparent shadow-[0_2px_8px_rgba(225,29,72,0.06)]">
										<span aria-hidden="true" className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-rose-400 via-rose-500 to-rose-600" />
										<summary className="flex items-center gap-2 px-3 py-2 cursor-pointer list-none min-h-[40px]">
											<span className="shrink-0 flex h-6 w-6 items-center justify-center rounded-full bg-rose-500/15 text-rose-600 dark:text-rose-300">
												<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>
											</span>
											<span className="text-[11px] font-bold text-rose-700 dark:text-rose-300">{t("chat.empty.compliance.summary", { count: briefingSummary?.compliance_warnings?.length ?? 0 })}</span>
											<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="ml-auto shrink-0 text-rose-400 group-open:rotate-180 transition-transform"><path d="m6 9 6 6 6-6"/></svg>
										</summary>
										<div className="px-3 pb-2.5 space-y-1">
											{(briefingSummary?.compliance_warnings ?? []).slice(0, 3).map((w, idx) => (
												<p key={idx} className="text-[11px] text-rose-800 dark:text-rose-200 leading-snug pl-8">
													<span className="font-semibold">{w.title}</span> · {w.message}
												</p>
											))}
										</div>
									</details>
								)}

								{/* Today's top priority — collapsible */}
								{(topActions.length > 0 || (briefingSummary && briefingSummary.message_count > 0)) && (
									<details className="group relative rounded-xl border border-insurance-gold/30 dark:border-insurance-gold/25 bg-gradient-to-br from-insurance-gold/10 via-insurance-gold/5 to-transparent dark:from-insurance-gold/15 dark:via-insurance-gold/8 dark:to-transparent shadow-[0_2px_8px_rgba(201,168,76,0.08)]">
										<span aria-hidden="true" className="absolute inset-x-4 top-0 h-[1.5px] bg-gradient-to-r from-transparent via-insurance-gold/80 to-transparent" />
										<summary className="flex items-center gap-2 px-3 py-2 cursor-pointer list-none min-h-[40px]">
											<span className="shrink-0 flex h-6 w-6 items-center justify-center rounded-full bg-insurance-gold/20 text-insurance-gold-dark dark:text-insurance-gold">
												<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
											</span>
											<span className="text-[11px] font-bold text-insurance-blue dark:text-insurance-gold-light">{t("chat.empty.todayActions.summary", { count: topActions.length })}</span>
											<button
												onClick={(e) => { e.preventDefault(); e.stopPropagation(); setBriefingOpen(true); }}
												className="ml-auto text-[10px] text-insurance-blue dark:text-insurance-gold-light font-semibold hover:underline cursor-pointer whitespace-nowrap"
											>
												{t("chat.empty.todayActions.detail")}
											</button>
											<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-insurance-gold group-open:rotate-180 transition-transform"><path d="m6 9 6 6 6-6"/></svg>
										</summary>
										<div className="px-3 pb-2.5 max-h-[35vh] overflow-y-auto overscroll-contain">
											{topActions.length > 0 ? (
												<ul className="space-y-2">
													{topActions.map((item, idx) => (
														<li key={idx} className="relative rounded-lg border border-slate-200/60 dark:border-slate-700/40 bg-white/60 dark:bg-slate-800/40 px-3 py-2">
															<div className="flex items-start gap-2">
																<span className="shrink-0 mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-insurance-gold/20 text-[10px] font-bold font-mono text-insurance-gold-dark dark:text-insurance-gold ring-1 ring-insurance-gold/30">
																	{idx + 1}
																</span>
																<div className="flex-1 min-w-0">
																	<p className="text-[11px] text-slate-800 dark:text-slate-200 leading-relaxed whitespace-pre-line">
																		{item.action.replace(/\s*(\d+[)）])\s*/g, "\n$1 ").trim()}
																	</p>
																	{(item.policy_no || item.customer_name) && (
																		<p className="mt-1 text-[10px] text-slate-500 dark:text-slate-400">
																			{item.policy_no && <span className="font-mono">{item.policy_no}</span>}
																			{item.policy_no && item.customer_name && " · "}
																			{item.customer_name}
																		</p>
																	)}
																</div>
															</div>
														</li>
													))}
												</ul>
											) : briefingSummary ? (
												<p className="text-[11px] text-slate-700 dark:text-slate-300 pl-8">
													{t("chat.empty.todaySummary", { count: briefingSummary.message_count })}
													{briefingSummary.p0_count > 0 && <span className="text-rose-600 font-semibold"> · P0 {briefingSummary.p0_count}</span>}
													{briefingSummary.p1_count > 0 && <span className="text-amber-600"> · P1 {briefingSummary.p1_count}</span>}
												</p>
											) : null}
										</div>
									</details>
								)}

								{/* If only compliance warnings (no messages, no actions), still provide button to open modal */}
								{(briefingSummary?.compliance_warnings?.length ?? 0) > 0 &&
									topActions.length === 0 &&
									(briefingSummary?.message_count ?? 0) === 0 && (
										<div className="text-right">
											<button
												onClick={() => setBriefingOpen(true)}
												className="text-[11px] text-insurance-blue dark:text-insurance-gold-light font-medium hover:underline cursor-pointer"
											>
												{t("chat.empty.viewDetail")}
											</button>
										</div>
									)}
							</div>

							<div className="relative z-10 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
								{QUICK_QUESTIONS.slice(0, 3).map((item) => (
									<button
										key={item.qKey}
										onClick={() => {
											const q = t(item.qKey, { name: agentName || "" });
											status === "connected" && !isTyping && onSend(q);
										}}
										disabled={status !== "connected" || isTyping}
										className="group relative text-left rounded-xl border border-slate-200/80 dark:border-white/10 bg-white/90 dark:bg-slate-800/80 backdrop-blur-sm shadow-[0_2px_8px_rgba(15,23,42,0.04)] dark:shadow-[0_2px_8px_rgba(2,6,23,0.3)] px-4 py-4 transition-all duration-300 ease-out hover:-translate-y-0.5 hover:shadow-[0_16px_40px_rgba(201,168,76,0.15)] hover:border-insurance-gold/50 dark:hover:border-insurance-gold/40 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer overflow-hidden"
									>
										{/* Gold left accent stripe on hover */}
										<span
											aria-hidden="true"
											className="absolute left-0 top-4 bottom-4 w-[3px] rounded-r-full bg-gradient-to-b from-insurance-gold-light via-insurance-gold to-insurance-gold-dark opacity-0 group-hover:opacity-100 transition-opacity duration-300"
										/>
										{/* Icon chip */}
										<div className="flex items-start gap-3">
											<span className="shrink-0 flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-insurance-gold/15 via-insurance-gold/10 to-insurance-gold/5 ring-1 ring-insurance-gold/20 group-hover:ring-insurance-gold/40 transition-all">
												<QuickCardIcon icon={item.icon} size={18} />
											</span>
											<div className="min-w-0 flex-1">
												<p className="text-sm font-semibold text-slate-800 dark:text-slate-100 leading-snug line-clamp-2">
													{t(item.qKey, { name: agentName || "..." })}
												</p>
												<p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400 group-hover:text-insurance-blue dark:group-hover:text-insurance-gold-light transition-colors">
													{t(item.descKey)}
												</p>
											</div>
											<svg
												aria-hidden="true"
												width="14"
												height="14"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												strokeWidth="2.5"
												strokeLinecap="round"
												strokeLinejoin="round"
												className="shrink-0 mt-1 text-slate-300 dark:text-slate-600 group-hover:text-insurance-gold group-hover:translate-x-0.5 transition-all"
											>
												<path d="m9 18 6-6-6-6" />
											</svg>
										</div>
									</button>
								))}
							</div>
						</div>
					</div>
				) : (
					<div className="max-w-5xl mx-auto space-y-1">
						{
							messages.reduce<{
								elements: React.ReactNode[];
								thinkingBatch: ChatMessage[];
							}>(
								(acc, msg, idx) => {
									const isThinkingType =
										msg.role === "tool_hint" || msg.role === "thinking";
									const nextMsg = messages[idx + 1];
									const nextIsThinking =
										nextMsg &&
										(nextMsg.role === "tool_hint" ||
											nextMsg.role === "thinking");

									if (isThinkingType) {
										acc.thinkingBatch.push(msg);
										if (!nextIsThinking) {
											acc.elements.push(
												<ThinkingProcess
													key={`thinking-${msg.id}`}
													steps={[...acc.thinkingBatch]}
												/>,
											);
											acc.thinkingBatch = [];
										}
									} else {
										acc.elements.push(
											<MessageBubble key={msg.id} message={msg} />,
										);
									}
									return acc;
								},
								{ elements: [], thinkingBatch: [] },
							).elements
						}
						{isTyping && !messages.some((m) => m.role === "thinking") && (
							<div className="flex items-center gap-2 px-4 py-3">
								<span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-insurance-gold/15 ring-1 ring-insurance-gold/30">
									<span className="relative flex h-2 w-2">
										<span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-insurance-gold opacity-75" />
										<span className="relative inline-flex h-2 w-2 rounded-full bg-insurance-gold" />
									</span>
								</span>
								<div className="flex gap-1">
									<span className="typing-dot w-1.5 h-1.5 rounded-full bg-insurance-gold/60 dark:bg-insurance-gold/70" />
									<span className="typing-dot w-1.5 h-1.5 rounded-full bg-insurance-gold/60 dark:bg-insurance-gold/70" />
									<span className="typing-dot w-1.5 h-1.5 rounded-full bg-insurance-gold/60 dark:bg-insurance-gold/70" />
								</div>
								<span className="text-[11px] text-slate-400 dark:text-slate-500 font-medium">{t("chat.thinking")}</span>
							</div>
						)}
						<div ref={messagesEndRef} />
					</div>
				)}
			</div>

			<div className="stagger-enter stagger-enter-3 border-t border-slate-200/80 dark:border-slate-800 glass-input px-4 md:px-6 py-4 pb-[calc(env(safe-area-inset-bottom)+1rem)]">
				<div className="max-w-5xl mx-auto">
					{!isEmpty && (
						<div className="flex gap-2 mb-3 overflow-x-auto pb-1">
							{QUICK_QUESTIONS.slice(0, 3).map((item) => (
								<button
									key={item.qKey}
									onClick={() => {
										const q = t(item.qKey, { name: agentName || "" });
										if (status === "connected" && !isTyping) {
											onSend(q, { retrievalMode });
										}
									}}
									disabled={status !== "connected" || isTyping}
									className="border-gradient relative flex-none text-xs px-3 py-1.5 rounded-full bg-white/80 dark:bg-slate-900/70 text-slate-600 dark:text-slate-300 hover:text-insurance-gold dark:hover:text-insurance-gold-light transition-all duration-200 ease-out hover:scale-[1.02] hover:shadow-lg active:scale-[0.98] whitespace-nowrap disabled:opacity-50 cursor-pointer"
								>
									<span className="inline-flex items-center gap-1.5">
										<QuickCardIcon icon={item.icon} />
										{t(item.qKey, { name: agentName || "..." })}
									</span>
								</button>
							))}
						</div>
					)}

					{voiceStatus && (
						<div
							role="status"
							aria-live="polite"
							className="mb-2 flex items-center gap-2 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-700 px-3 py-2 text-sm text-amber-800 dark:text-amber-200 shadow-sm"
						>
							<span
								className={cn(
									"inline-block h-2 w-2 rounded-full",
									voiceStatus.phase === "recording"
										? "bg-red-500 animate-pulse"
										: "bg-amber-500 animate-pulse",
								)}
								aria-hidden="true"
							/>
							<span className="flex-1 truncate">{voiceStatus.label}</span>
						</div>
					)}

					{voiceError && (
						<div
							role="alert"
							className="mb-2 flex items-center justify-between gap-2 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-300 dark:border-rose-700 px-3 py-2 text-sm text-rose-700 dark:text-rose-200 shadow-sm"
						>
							<span className="flex-1">{voiceError}</span>
							<button
								type="button"
								onClick={() => setVoiceError(null)}
								aria-label={t("chat.dismissError.aria")}
								className="shrink-0 -mr-1 flex h-6 w-6 items-center justify-center rounded-md hover:bg-rose-100 dark:hover:bg-rose-900/40"
							>
								<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
									<line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
								</svg>
							</button>
						</div>
					)}
					{pendingUploads.length > 0 && (
						<div className="flex flex-wrap gap-2 mb-2 px-1">
							{pendingUploads.map((p: UploadPillState) => (
								<UploadPill
									key={p.uploadId}
									state={p}
									onUpdate={updateUpload}
									onCancel={removeUpload}
								/>
							))}
						</div>
					)}
					<div className="glass border-gradient rounded-xl px-2 sm:px-3 py-2 sm:py-3">
						<div className="mb-2 flex items-center justify-between gap-3 px-1">
							<span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
								{t("chat.retrieval.label")}
							</span>
							<div
								role="radiogroup"
								aria-label={t("chat.retrieval.label")}
								className="inline-flex rounded-lg border border-slate-200/80 bg-slate-100/80 p-0.5 dark:border-slate-700 dark:bg-slate-800/80"
							>
								<button
									type="button"
									role="radio"
									aria-checked={retrievalMode === "keyword"}
									onClick={() => setRetrievalMode("keyword")}
									className={cn(
										"rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors",
										retrievalMode === "keyword"
											? "bg-white text-insurance-blue shadow-sm dark:bg-slate-700 dark:text-white"
											: "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200",
									)}
								>
									{t("chat.retrieval.keyword")}
								</button>
								<button
									type="button"
									role="radio"
									aria-checked={retrievalMode === "vector"}
									disabled={capabilityLoading || !vectorCapability.available}
									onClick={() =>
										vectorCapability.available && setRetrievalMode("vector")
									}
									title={
										capabilityLoading
											? t("chat.retrieval.checking")
											: vectorCapability.available
												? t("chat.retrieval.vectorAvailable")
												: vectorCapability.reason ||
													t("chat.retrieval.vectorUnavailable")
									}
									className={cn(
										"rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors",
										retrievalMode === "vector"
											? "bg-white text-insurance-blue shadow-sm dark:bg-slate-700 dark:text-white"
											: "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200",
										(capabilityLoading || !vectorCapability.available) &&
											"cursor-not-allowed opacity-40",
									)}
								>
									{t("chat.retrieval.vector")}
								</button>
							</div>
						</div>
						<div className="flex items-center gap-2">
							<VoiceButton
								onTranscribed={(text) => sendDirectly(text)}
								onError={(msg) => setVoiceError(msg)}
								onStatusChange={setVoiceStatus}
								disabled={status !== 'connected' || isTyping}
								className={cn(isInputFocused ? "hidden md:flex" : "flex")}
							/>
							<div className="flex-1 min-w-0">
								<textarea
									ref={textareaRef}
									value={input}
									onChange={handleInput}
									onKeyDown={handleKeyDown}
									onFocus={() => setIsInputFocused(true)}
									onBlur={() => window.setTimeout(() => setIsInputFocused(false), 120)}
									enterKeyHint="send"
									inputMode="text"
									placeholder={
										isTyping
											? t("chat.placeholder.typing")
											: status === "connected"
												? t("chat.placeholder.connected")
												: t("chat.placeholder.disconnected")
									}
									disabled={status !== "connected" || isTyping}
									rows={1}
									className="w-full resize-none rounded-lg border border-slate-200/80 dark:border-slate-700/70 bg-white/90 dark:bg-slate-900/80 px-4 py-3 text-sm text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none focus:border-insurance-gold/70 focus:ring-4 focus:ring-insurance-gold/15 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
								/>
							</div>

							<FileButton
								sessionKey={sessionKey}
								disabled={status !== "connected" || isTyping}
								className={cn(isInputFocused ? "hidden md:flex" : "flex")}
								onUploadStarted={(s: UploadPillState) =>
									setPendingUploads((prev: UploadPillState[]) => [...prev, s])
								}
								onError={(msg: string) =>
									setPendingUploads((prev: UploadPillState[]) => [
										...prev,
										{
											uploadId: `err-${Date.now()}`,
											filename: msg,
											size: 0,
											status: "failed" as const,
											error: msg,
										},
									])
								}
							/>

							<button
								onClick={handleSend}
								disabled={
									(!input.trim() && pendingUploads.filter((p: UploadPillState) => p.status === "ready").length === 0) ||
									status !== "connected" ||
									isTyping ||
									pendingUploads.some((p: UploadPillState) => p.status === "parsing")
								}
								className={cn(
									"group flex-none w-10 h-10 rounded-lg items-center justify-center transition-all duration-200 cursor-pointer",
									isInputFocused ? "flex" : "hidden md:flex",
									(input.trim() || pendingUploads.some((p: UploadPillState) => p.status === "ready")) && status === "connected" && !isTyping && !pendingUploads.some((p: UploadPillState) => p.status === "parsing")
										? "bg-gradient-to-br from-insurance-gold via-insurance-gold-light to-[#E89A4A] text-white shadow-[0_10px_24px_rgba(201,168,76,0.5)] hover:scale-110 hover:shadow-lg hover:shadow-blue-500/25 active:scale-95"
										: "bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-600 cursor-not-allowed",
								)}
								aria-label={t("chat.send.aria")}
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									width="18"
									height="18"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									strokeWidth="2"
									strokeLinecap="round"
									strokeLinejoin="round"
									className="transition-transform duration-300 group-hover:-rotate-12"
								>
									<path d="m5 12 7-7 7 7" />
									<path d="M12 19V5" />
								</svg>
							</button>
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}
