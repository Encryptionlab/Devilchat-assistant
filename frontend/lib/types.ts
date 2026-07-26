/* TypeScript types matching backend Pydantic schemas */

export interface ChatMessage {
  id: string;
  role: '她' | '我';
  content: string;
  timestamp: string;
  isStreaming?: boolean;
  strategy?: string;
  goal?: string;
}

export interface ChatResponse {
  reply: string;
  enhanced_reply: string;
  strategy_name: string;
  goal: string;
  goal_zh: string;
  conversation_switched: boolean;
  closed_conversation: ClosedConversation | null;
  debug?: Record<string, unknown>;
}

export interface ClosedConversation {
  id: string;
  topic: string;
  start_time: string;
  end_time: string | null;
  summary: string | null;
  outcome: string | null;
  key_points: KeyPoint[];
}

export interface KeyPoint {
  text: string;
  type: 'unresolved' | 'info' | 'emotion';
}

export interface ConversationOut {
  id: string;
  topic: string;
  status: string;
  start_time: string;
  end_time: string | null;
  last_message_time: string;
  current_goal: string | null;
  summary: string | null;
  outcome: string | null;
  message_ids: string[];
  key_points: KeyPoint[];
}

export interface RelationshipState {
  stage: string;
  temperature: string;
  attachment_style: string | null;
  trust_level: number;
  intimacy_level: number;
  conflict_status: string;
  conflict_level: number;
  recurring_topics: string[];
  unresolved_topics: string[];
  recent_events: string[];
  future_events: string[];
  preferences: string[];
  personality_traits: string[];
}

export interface SSEEvent {
  type: 'step' | 'reply_chunk' | 'enhanced_chunk' | 'done' | 'error';
  data: Record<string, unknown>;
}
