export interface Message {
    id: number;
    thread_id: number;
    role: 'user' | 'assistant' | 'system' | 'tool';
    content: string;
    created_at: string;
    type: 'message';
} 