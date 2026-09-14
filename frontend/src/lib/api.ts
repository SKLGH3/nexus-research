import { API_BASE_URL } from "./config";
import type { AdminOverview, AuthResponse, FileListResponse, HistoryDetail, HistoryItem, PublicConfig, ResearchTemplate, TaskResponse, CancelTaskResponse, UploadResponse, User } from "../types";

const TOKEN_KEY = "nexus-research.auth-token";
export const getAuthToken = () => localStorage.getItem(TOKEN_KEY) || "";
export const setAuthToken = (token: string) => localStorage.setItem(TOKEN_KEY, token);
export const clearAuthToken = () => localStorage.removeItem(TOKEN_KEY);
function apiUrl(path: string): string { return API_BASE_URL + path; }

async function requestJson<T>(input: RequestInfo | URL, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getAuthToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(input, { ...init, headers });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = typeof payload === "object" && payload && "detail" in payload ? String(payload.detail) : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
}

export const getPublicConfig = () => requestJson<PublicConfig>(apiUrl("/api/config"));
export async function login(email: string, password: string) { const response=await requestJson<AuthResponse>(apiUrl("/api/auth/login"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})}); setAuthToken(response.access_token); return response; }
export async function register(email: string, display_name: string, password: string) { const response=await requestJson<AuthResponse>(apiUrl("/api/auth/register"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,display_name,password})}); setAuthToken(response.access_token); return response; }
export const getMe = () => requestJson<User>(apiUrl("/api/auth/me"));
export const startTask = (query:string,threadId:string) => requestJson<TaskResponse>(apiUrl("/api/task"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query,thread_id:threadId})});
export const cancelTask = (threadId:string) => requestJson<CancelTaskResponse>(apiUrl(`/api/task/${encodeURIComponent(threadId)}/cancel`),{method:"POST"});
export function uploadSessionFiles(files:File[],threadId:string){const form=new FormData();form.append("thread_id",threadId);files.forEach(file=>form.append("files",file));return requestJson<UploadResponse>(apiUrl("/api/upload"),{method:"POST",body:form});}
export const listSessionFiles = (threadId:string) => requestJson<FileListResponse>(apiUrl(`/api/sessions/${encodeURIComponent(threadId)}/files`));
export const listHistory = () => requestJson<{items:HistoryItem[]}>(apiUrl("/api/history"));
export const getHistory = (id:string) => requestJson<HistoryDetail>(apiUrl(`/api/history/${encodeURIComponent(id)}`));
export const deleteHistory = (id:string) => requestJson<{status:string}>(apiUrl(`/api/history/${encodeURIComponent(id)}`),{method:"DELETE"});
export const listTemplates = () => requestJson<{items:ResearchTemplate[]}>(apiUrl("/api/templates"));
export const createTemplate = (payload:Pick<ResearchTemplate,"title"|"description"|"prompt"|"category">) => requestJson<ResearchTemplate>(apiUrl("/api/templates"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
export const deleteTemplate = (id:string) => requestJson<{status:string}>(apiUrl(`/api/templates/${encodeURIComponent(id)}`),{method:"DELETE"});
export const getAdminOverview = () => requestJson<AdminOverview>(apiUrl("/api/admin/overview"));
export const listUsers = () => requestJson<{items:User[]}>(apiUrl("/api/admin/users"));
export async function downloadSessionFile(threadId:string,relativePath:string){const encoded=relativePath.split("/").map(encodeURIComponent).join("/");const response=await fetch(apiUrl(`/api/sessions/${encodeURIComponent(threadId)}/files/${encoded}`),{headers:{Authorization:`Bearer ${getAuthToken()}`}});if(!response.ok) throw new Error(`下载失败：HTTP ${response.status}`);const blob=await response.blob();const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download=relativePath.split("/").pop()||"download";link.click();URL.revokeObjectURL(url);}

export function getDownloadUrl(threadId:string,relativePath:string){const encoded=relativePath.split("/").map(encodeURIComponent).join("/");return apiUrl(`/api/sessions/${encodeURIComponent(threadId)}/files/${encoded}`);}
