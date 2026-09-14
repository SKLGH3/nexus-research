export type ConnectionState = "connecting" | "connected" | "reconnecting" | "closed";
export type MonitorEventName = "session_created" | "tool_start" | "assistant_call" | "sources_found" | "task_result" | "task_cancelled" | "error" | string;
export interface MonitorMessage { type: "monitor_event"; event: MonitorEventName; message: string; data: Record<string, unknown>; timestamp: string; }
export interface PongMessage { type: "pong"; message: string; }
export type SocketMessage = MonitorMessage | PongMessage;
export interface TaskResponse { status: string; thread_id: string; }
export interface CancelTaskResponse { status: string; thread_id: string; message?: string; }
export interface UploadResponse { status: string; files: string[]; }
export interface OutputFile { name: string; type: string; path: string; size: number; mtime: number; }
export interface FileListResponse { files?: OutputFile[]; error?: string; }
export interface UploadedItem { uid: string; name: string; size: number; raw: File; }
export interface IntegrationState { ready: boolean; provider?: string; driver?: string; detail?: string; }
export interface PublicConfig { app_name: string; version: string; environment: string; allow_registration?: boolean; model: { provider: string; name: string; base_url: string; ready: boolean; }; integrations: { database: IntegrationState; web_search: IntegrationState; knowledge_base: IntegrationState; }; }
export interface User { id: string; email: string; display_name: string; role: "admin" | "member"; active: number | boolean; created_at: string; last_login_at?: string | null; task_count?: number; }
export interface AuthResponse { access_token: string; token_type: string; user: User; }
export interface Citation { id: number; title: string; url: string; domain: string; snippet: string; created_at: string; }
export interface HistoryItem { id: string; thread_id: string; user_id: string; query: string; status: string; result: string; error: string; created_at: string; updated_at: string; completed_at?: string | null; citation_count?: number; event_count?: number; }
export interface HistoryDetail extends HistoryItem { events: MonitorMessage[]; citations: Citation[]; files: OutputFile[]; }
export interface ResearchTemplate { id: string; title: string; description: string; prompt: string; category: string; created_by?: string | null; is_public: number | boolean; created_at: string; updated_at: string; }
export interface AdminOverview { users: number; tasks: number; completed_tasks: number; citations: number; recent_tasks: Array<HistoryItem & { display_name: string; email: string }>; }
