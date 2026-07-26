'use client';

import { useReducer, useCallback, useRef } from 'react';
import { sendMessageStream } from '@/lib/api';

interface Analysis {
  emotion: string;
  topic: string;
  dominantNeed: string;
  goal: string;
  goalZh: string;
  strategy: string;
}

interface HistoryEntry {
  id: string;
  role: '她' | '我';
  content: string;
}

interface ChatState {
  isLoading: boolean;
  analysis: Analysis | null;
  reply: string;
  enhancedReply: string;
  history: HistoryEntry[];
  error: string | null;
}

type Action =
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ANALYSIS'; payload: Partial<Analysis> }
  | { type: 'APPEND_REPLY'; payload: string }
  | { type: 'APPEND_ENHANCED'; payload: string }
  | { type: 'ADD_HISTORY'; payload: HistoryEntry }
  | { type: 'SET_ERROR'; payload: string }
  | { type: 'CLEAR_ERROR' }
  | { type: 'RESET' };

const initialAnalysis: Analysis = {
  emotion: '',
  topic: '',
  dominantNeed: '',
  goal: '',
  goalZh: '',
  strategy: '',
};

function reducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case 'SET_LOADING':
      return { ...state, isLoading: action.payload };
    case 'SET_ANALYSIS':
      return {
        ...state,
        analysis: { ...state.analysis!, ...action.payload },
      };
    case 'APPEND_REPLY':
      return { ...state, reply: state.reply + action.payload };
    case 'APPEND_ENHANCED':
      return { ...state, enhancedReply: state.enhancedReply + action.payload };
    case 'ADD_HISTORY':
      return { ...state, history: [...state.history, action.payload] };
    case 'SET_ERROR':
      return { ...state, error: action.payload, isLoading: false };
    case 'CLEAR_ERROR':
      return { ...state, error: null };
    case 'RESET':
      return {
        isLoading: false,
        analysis: { ...initialAnalysis },
        reply: '',
        enhancedReply: '',
        history: state.history,
        error: null,
      };
    default:
      return state;
  }
}

function makeId() {
  return 'msg_' + Math.random().toString(36).slice(2, 10);
}

const needLabels: Record<string, string> = {
  UNDERSTANDING: '被理解',
  ATTENTION: '被关注',
  VALIDATION: '被认可',
  COMPANIONSHIP: '陪伴',
  PARTICIPATION: '参与感',
  SECURITY: '安全感',
  AUTONOMY: '自主感',
  COMFORT: '安慰',
  ENCOURAGEMENT: '鼓励',
  APPRECIATION: '被欣赏',
};

const emotionLabels: Record<string, string> = {
  happy: '开心',
  sad: '难过',
  angry: '生气',
  anxious: '焦虑',
  tired: '疲惫',
  disappointed: '失望',
  neutral: '中性',
  excited: '兴奋',
  worried: '担心',
  confused: '困惑',
};

export function useChat() {
  const [state, dispatch] = useReducer(reducer, {
    isLoading: false,
    analysis: { ...initialAnalysis },
    reply: '',
    enhancedReply: '',
    history: [],
    error: null,
  });

  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (herMessage: string) => {
    dispatch({ type: 'CLEAR_ERROR' });
    dispatch({ type: 'SET_LOADING', payload: true });
    dispatch({ type: 'RESET' });
    dispatch({ type: 'ADD_HISTORY', payload: { id: makeId(), role: '她', content: herMessage } });

    const historyForApi = state.history.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    abortRef.current = new AbortController();

    try {
      let phase: 'reply' | 'enhanced' = 'reply';

      await sendMessageStream(
        herMessage,
        historyForApi,
        (eventType, data) => {
          switch (eventType) {
            case 'step': {
              const updates: Partial<Analysis> = {};
              if (data.emotion) updates.emotion = data.emotion as string;
              if (data.topic) updates.topic = data.topic as string;
              if (data.dominant_need) updates.dominantNeed = data.dominant_need as string;
              if (data.goal) updates.goal = data.goal as string;
              if (data.goal_zh) updates.goalZh = data.goal_zh as string;
              if (data.strategy) updates.strategy = data.strategy as string;
              if (Object.keys(updates).length > 0) {
                dispatch({ type: 'SET_ANALYSIS', payload: updates });
              }
              break;
            }
            case 'reply_chunk':
              if (phase === 'reply') {
                dispatch({ type: 'APPEND_REPLY', payload: (data.text as string) || '' });
              }
              break;
            case 'enhanced_chunk':
              if (phase === 'reply') phase = 'enhanced';
              dispatch({ type: 'APPEND_ENHANCED', payload: (data.text as string) || '' });
              break;
            case 'done':
              dispatch({
                type: 'SET_ANALYSIS',
                payload: {
                  strategy: (data.strategy_name as string) || '',
                  goal: (data.goal as string) || '',
                  goalZh: (data.goal_zh as string) || '',
                },
              });
              dispatch({
                type: 'ADD_HISTORY',
                payload: {
                  id: makeId(),
                  role: '我',
                  content: (data.enhanced_reply as string) || (data.reply as string) || '',
                },
              });
              dispatch({ type: 'SET_LOADING', payload: false });
              break;
            case 'error':
              dispatch({ type: 'SET_ERROR', payload: (data.error as string) || '分析失败' });
              break;
          }
        },
        abortRef.current.signal,
      );
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : '发送失败';
      dispatch({ type: 'SET_ERROR', payload: msg });
    }
  }, [state.history]);

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    dispatch({ type: 'SET_LOADING', payload: false });
  }, []);

  return {
    isLoading: state.isLoading,
    analysis: state.analysis,
    reply: state.reply,
    enhancedReply: state.enhancedReply,
    history: state.history,
    error: state.error,
    sendMessage,
    stopStreaming,
    needLabels,
    emotionLabels,
  };
}
