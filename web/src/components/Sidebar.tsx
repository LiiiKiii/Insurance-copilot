"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { authFetch, clearAuth, getChatUser } from "@/lib/auth";
import { ThemeToggle } from "./ThemeToggle";
import { ConfirmModal } from "./ConfirmModal";
import { useTranslation, LOCALE_BCP47 } from "@/lib/i18n";

interface AgentProfile {
	agent_id: string;
	name_zh: string;
	nickname?: string;
	rank?: string;
	tier?: string;
}

interface ChatSession {
	id: string;
	agentId: string;
	title: string;
	updatedAt: string;
	messageCount: number;
}

export interface SidebarBaseProps {
	agentId: string;
	onAgentChange?: (id: string) => void;
	status: "connecting" | "connected" | "disconnected";
	onNewChat: () => void;
	chatSessions?: ChatSession[];
	onLoadSession?: (sessionId: string) => void;
	onDeleteSession?: (sessionId: string) => void;
	activeSessionId?: string;
	/** Called when user wants to logout — parent handles the confirm modal */
	onLogoutRequest?: () => void;
	/** Called when user wants to delete a session — parent handles the confirm modal */
	onDeleteRequest?: (sessionId: string) => void;
}

interface SidebarProps extends SidebarBaseProps {
	onSend?: (message: string) => void;
}

interface SidebarContentProps extends SidebarBaseProps {
	/** desktop: respects isCollapsed and shows collapse button; drawer: always expanded, no collapse */
	variant?: "desktop" | "drawer";
	isCollapsed?: boolean;
	onToggleCollapse?: () => void;
	/** drawer variant: called when a nav item that should close the drawer is activated */
	onRequestClose?: () => void;
}

export function Sidebar(props: SidebarProps) {
	const [isCollapsed, setIsCollapsed] = useState(false);

	return (
		<aside
			className={cn(
				"glass-sidebar mesh-overlay noise-overlay stagger-enter stagger-enter-1 relative flex flex-col border-r border-slate-200/60 dark:border-white/10 bg-gradient-to-b from-insurance-blue-dark via-insurance-blue to-[#102640] transition-all duration-300 overflow-hidden",
				isCollapsed ? "w-16" : "w-72",
			)}
		>
			<div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-insurance-gold-dark via-insurance-gold-light to-insurance-gold" />
			<SidebarContent
				{...props}
				variant="desktop"
				isCollapsed={isCollapsed}
				onToggleCollapse={() => setIsCollapsed(!isCollapsed)}
			/>
		</aside>
	);
}

export function SidebarContent({
	agentId,
	onAgentChange,
	status,
	onNewChat,
	chatSessions = [],
	onLoadSession,
	onDeleteSession,
	activeSessionId,
	variant = "drawer",
	isCollapsed = false,
	onToggleCollapse,
	onRequestClose,
	onLogoutRequest,
	onDeleteRequest,
}: SidebarContentProps) {
	const { t, locale } = useTranslation();
	const [showHistory, setShowHistory] = useState(true);
	const [currentAgent, setCurrentAgent] = useState<AgentProfile | null>(null);
	const [confirmLogout, setConfirmLogout] = useState(false);
	const handleLogoutClick = () => {
		if (variant === "drawer" && onLogoutRequest) {
			onRequestClose?.();
			onLogoutRequest();
		} else {
			setConfirmLogout(true);
		}
	};
	const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

	const showCollapseBtn = variant === "desktop";
	const effectiveCollapsed = variant === "desktop" ? isCollapsed : false;
	const touchClass = variant === "drawer" ? "min-h-11" : "";

	// the chat UI always uses the logged-in username as agentId; switching views is not supported
	useEffect(() => {
		const me = getChatUser();
		if (me?.username && me.username !== agentId) {
			onAgentChange?.(me.username);
		}
	}, []); // eslint-disable-line react-hooks/exhaustive-deps

	// fetch the current agent's profile (name / rank) for the header
	useEffect(() => {
		if (!agentId) return;
		let cancelled = false;
		authFetch(`/api/agent-info?agent_id=${encodeURIComponent(agentId)}`)
			.then((r) => r.json())
			.then((d) => {
				if (!cancelled && d?.data) setCurrentAgent(d.data);
			})
			.catch(() => {});
		return () => {
			cancelled = true;
		};
	}, [agentId]);

	const agentName = currentAgent?.name_zh || agentId;
	const agentTitle = currentAgent?.rank || "";
	const agentInitial = agentName[0] || "A";

	const statusConfig = {
		connected: { color: "bg-emerald-400 pulse-ring", text: t("connection.connected") },
		connecting: { color: "bg-amber-400 animate-pulse", text: t("connection.connecting") },
		disconnected: { color: "bg-red-400", text: t("connection.disconnected") },
	};
	const currentStatus = statusConfig[status];

	const handleNewChat = () => {
		onNewChat();
		onRequestClose?.();
	};

	return (
		<>
			{/* Header */}
			<div
				className={cn(
					"flex items-center p-4 border-b border-white/10 transition-[gap] duration-300",
					effectiveCollapsed ? "gap-0 justify-center" : "gap-3",
				)}
			>
				<div
					className={cn(
						"rounded-lg  border-white/15  whitespace-nowrap transition-all duration-300",
						effectiveCollapsed
							? "opacity-0 w-0 min-w-0 p-0 border-0 overflow-hidden"
							: "opacity-100 flex-1 min-w-0 px-3 py-2.5",
					)}
				>
					<h1 className="font-display text-lg font-bold text-white tracking-tight">
						{t("app.title")}
					</h1>
					<p className="text-xs text-insurance-gold-light tracking-wide">
						{t("app.subtitle")}
					</p>
				</div>
				{showCollapseBtn && (
					<button
						onClick={onToggleCollapse}
						className="shrink-0 p-1.5 rounded-lg text-white/60 hover:text-white hover:bg-white/10 hover:translate-x-1 transition-all duration-200 ease-out cursor-pointer"
						aria-label={effectiveCollapsed ? t("sidebar.expand.aria") : t("sidebar.collapse.aria")}
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
						>
							{effectiveCollapsed ? (
								<path d="m9 18 6-6-6-6" />
							) : (
								<path d="m15 18-6-6 6-6" />
							)}
						</svg>
					</button>
				)}
			</div>

			{/* Agent Card */}
			<div
				className={cn(
					"p-4 whitespace-nowrap transition-opacity duration-300",
					effectiveCollapsed ? "opacity-0 h-0 p-0 overflow-hidden" : "opacity-100",
				)}
			>
				<div className="glass rounded-lg p-3.5 border border-white/15">
					<div className="flex items-center gap-3">
						<div className="w-10 h-10 rounded-full bg-insurance-gold/20 flex items-center justify-center text-insurance-gold font-display font-bold text-sm shrink-0">
							{agentInitial}
						</div>
						<div className="flex-1 min-w-0">
							<p className="text-sm font-semibold text-white truncate">
								{agentName}
							</p>
							<p className="text-xs text-white/70">{agentTitle}</p>
						</div>
					</div>
					<div className="mt-3 flex items-center gap-2">
						<span className="text-xs text-white/50 font-mono">{agentId}</span>
						<span className="flex items-center gap-1.5 text-xs text-white/80">
							<span
								className={cn("w-1.5 h-1.5 rounded-full", currentStatus.color)}
							/>
							{currentStatus.text}
						</span>
					</div>
				</div>
			</div>

			{/* Navigation */}
			<nav className="flex-1 px-3 py-2 space-y-1 min-h-0 overflow-y-auto overscroll-contain">
				<button
					onClick={handleNewChat}
					className={cn(
						"flex items-center w-full rounded-lg text-white/85 hover:text-white hover:bg-white/10 hover:translate-x-1 transition-all duration-200 ease-out cursor-pointer",
						touchClass,
						effectiveCollapsed ? "p-2 justify-center gap-0" : "px-3 py-2.5 gap-3",
					)}
				>
					<svg
						className="shrink-0"
						xmlns="http://www.w3.org/2000/svg"
						width="18"
						height="18"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						strokeWidth="2"
						strokeLinecap="round"
						strokeLinejoin="round"
					>
						<path d="M12 5v14M5 12h14" />
					</svg>
					<span
						className={cn(
							"text-sm whitespace-nowrap transition-opacity duration-300",
							effectiveCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100",
						)}
					>
						{t("sidebar.newChat")}
					</span>
				</button>
				<button
					onClick={() => setShowHistory(!showHistory)}
					className={cn(
						"flex items-center w-full rounded-lg text-white/85 hover:text-white hover:bg-white/10 transition-all duration-200 cursor-pointer",
						touchClass,
						effectiveCollapsed ? "p-2 justify-center gap-0" : "px-3 py-2.5 gap-3",
						showHistory && "bg-white/10 text-white",
					)}
				>
					<svg
						className="shrink-0"
						xmlns="http://www.w3.org/2000/svg"
						width="18"
						height="18"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						strokeWidth="2"
						strokeLinecap="round"
						strokeLinejoin="round"
					>
						<path d="M12 8v4l3 3" />
						<circle cx="12" cy="12" r="10" />
					</svg>
					<span
						className={cn(
							"text-sm whitespace-nowrap transition-opacity duration-300",
							effectiveCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100",
						)}
					>
						{t("sidebar.history")}
					</span>
					{(() => {
						const visibleCount = chatSessions.filter(
							(s) => !agentId || s.agentId === agentId,
						).length;
						return !effectiveCollapsed && visibleCount > 0 ? (
							<span className="ml-auto text-[10px] text-white/40 bg-white/10 px-1.5 py-0.5 rounded-full whitespace-nowrap">
								{visibleCount}
							</span>
						) : null;
					})()}
				</button>

				{/* History list */}
				{showHistory && (
					<div
						className={cn(
							"mt-1 max-h-60 overflow-y-auto space-y-0.5 px-1 whitespace-nowrap transition-opacity duration-300",
							effectiveCollapsed ? "opacity-0 overflow-hidden" : "opacity-100",
						)}
					>
						{chatSessions.filter((s) => !agentId || s.agentId === agentId)
							.length === 0 ? (
							<p className="text-xs text-white/30 px-2 py-2">{t("sidebar.history.empty")}</p>
						) : (
							chatSessions
								.filter((s) => !agentId || s.agentId === agentId)
								.map((s) => (
									<div
										key={s.id}
										className={cn(
											"group flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors",
											s.id === activeSessionId
												? "bg-white/15 text-white"
												: "text-white/60 hover:bg-white/10 hover:text-white/80",
										)}
									>
										<button
											onClick={() => {
												onLoadSession?.(s.id);
												onRequestClose?.();
											}}
											className="flex-1 min-w-0 text-left"
										>
											<p className="text-xs truncate">{s.title}</p>
											<p className="text-[10px] text-white/30">
												{t("sidebar.history.itemMeta", {
													count: s.messageCount,
													date: new Date(s.updatedAt).toLocaleDateString(LOCALE_BCP47[locale], {
														month: "short",
														day: "numeric",
														hour: "2-digit",
														minute: "2-digit",
													}),
												})}
											</p>
										</button>
										<button
											onClick={(e) => {
												e.stopPropagation();
												if (variant === "drawer" && onDeleteRequest) {
													onRequestClose?.();
													onDeleteRequest(s.id);
												} else {
													setConfirmDeleteId(s.id);
												}
											}}
											className="opacity-0 group-hover:opacity-100 p-1 text-white/30 hover:text-red-400 transition-all"
											title={t("common.delete")}
										>
											<svg
												width="12"
												height="12"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												strokeWidth="2"
												strokeLinecap="round"
												strokeLinejoin="round"
											>
												<line x1="18" y1="6" x2="6" y2="18" />
												<line x1="6" y1="6" x2="18" y2="18" />
											</svg>
										</button>
									</div>
								))
						)}
					</div>
				)}
			</nav>

			{/* Logout */}
			<div
				className={cn(
					"px-4 pb-3 whitespace-nowrap transition-opacity duration-300",
					effectiveCollapsed ? "opacity-0 h-0 p-0 overflow-hidden" : "opacity-100",
				)}
			>
				<button
					onClick={handleLogoutClick}
					className={cn(
						"flex items-center gap-2 w-full rounded-lg bg-white/10 border border-white/20 text-white/70 hover:text-white hover:bg-white/15 text-sm px-3 py-2 transition-colors cursor-pointer",
						touchClass,
					)}
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						width="14"
						height="14"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						strokeWidth="2"
						strokeLinecap="round"
						strokeLinejoin="round"
					>
						<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
						<polyline points="16 17 21 12 16 7" />
						<line x1="21" y1="12" x2="9" y2="12" />
					</svg>
					{t("common.logout")}
				</button>
			</div>

			{/* Footer */}
			<div
				className={cn(
					"border-t border-white/10 p-3",
					effectiveCollapsed
						? "flex justify-center"
						: "flex items-center justify-between",
				)}
			>
				<ThemeToggle />
				<span
					className={cn(
						"text-xs text-white/30 whitespace-nowrap transition-opacity duration-300",
						effectiveCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100",
					)}
				>
					v2.0
				</span>
			</div>
			<ConfirmModal
				open={confirmLogout}
				onClose={() => setConfirmLogout(false)}
				title={t("confirm.logout.title")}
				message={t("confirm.logout.message")}
				confirmText={t("common.logout")}
				danger
				onConfirm={() => {
					clearAuth();
					window.location.href = "/login";
				}}
			/>
			<ConfirmModal
				open={!!confirmDeleteId}
				onClose={() => setConfirmDeleteId(null)}
				title={t("confirm.deleteSession.title")}
				message={t("confirm.deleteSession.message")}
				confirmText={t("common.delete")}
				danger
				onConfirm={() => {
					if (confirmDeleteId) onDeleteSession?.(confirmDeleteId);
				}}
			/>
		</>
	);
}
