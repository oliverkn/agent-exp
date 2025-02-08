import React, { useEffect, useState, useRef } from 'react';

interface ThreadMessage {
  id: number;
  content: string;
  thread_id: number;
  created_at: string;
  sender: string;
  sequence_number: number;
  is_tool_call: boolean;
  tool_name?: string;
  tool_args?: string;
  tool_result?: string;
}

interface Thread {
  id: number;
  title: string;
  created_at: string;
  updated_at: string | null;
  is_running: boolean;
  messages?: ThreadMessage[];
}

const API_BASE = 'http://localhost:8000';

const Threads: React.FC = () => {
  const [selectedThreadId, setSelectedThreadId] = useState<number | null>(null);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [newThreadTitle, setNewThreadTitle] = useState('');
  const [selectedThread, setSelectedThread] = useState<Thread | null>(null);
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    fetchThreads();
  }, []);

  useEffect(() => {
    if (selectedThreadId) {
      fetchThread(selectedThreadId);
      fetchMessages(selectedThreadId);
      connectWebSocket();
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [selectedThreadId]);

  const connectWebSocket = () => {
    if (!selectedThreadId || wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    console.log(`Connecting to WebSocket for thread ${selectedThreadId}`);
    const ws = new WebSocket(`ws://${API_BASE.replace('http://', '')}/threads/${selectedThreadId}/ws`);

    ws.onopen = () => {
      console.log(`WebSocket Connected for thread ${selectedThreadId}`);
      setError(null);
    };

    ws.onmessage = (event) => {
      console.log('Received WebSocket message:', event.data);
      try {
        const message = JSON.parse(event.data);
        console.log('Parsed message:', message);
        setMessages(prev => {
          // Check if message already exists
          if (prev.some(m => m.id === message.id)) {
            return prev;
          }
          return [...prev, message];
        });
      } catch (e) {
        console.error('Error parsing message:', e);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setError('Connection error. Messages may not be real-time.');
    };

    ws.onclose = (event) => {
      console.log(`WebSocket disconnected for thread ${selectedThreadId}. Code: ${event.code}, Reason: ${event.reason}`);
      if (event.code !== 4004) {
        setTimeout(connectWebSocket, 3000);
      }
    };

    wsRef.current = ws;
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const fetchThreads = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/threads/`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      console.log('Fetched threads:', data);
      setThreads(data);
      setError(null);
    } catch (error) {
      console.error('Error fetching threads:', error);
      setError('Failed to load threads. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const fetchThread = async (id: number) => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/threads/${id}`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setSelectedThread(data);
      setError(null);
    } catch (error) {
      console.error('Error fetching thread:', error);
      setError('Failed to load thread details');
    } finally {
      setLoading(false);
    }
  };

  const fetchMessages = async (id: number) => {
    try {
      const response = await fetch(`${API_BASE}/threads/${id}/messages/`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setMessages(data);
      setError(null);
    } catch (error) {
      console.error('Error fetching messages:', error);
      setError('Failed to load messages');
    }
  };

  const handleCreateThread = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newThreadTitle.trim()) return;

    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/threads/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ title: newThreadTitle }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const thread = await response.json();
      console.log('Created thread:', thread);
      setThreads(prev => [...prev, thread]);
      setNewThreadTitle('');
      setSelectedThreadId(thread.id);
      setError(null);
      
      // Refresh the threads list
      fetchThreads();
    } catch (error) {
      console.error('Error creating thread:', error);
      setError('Failed to create thread. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMessage.trim() || sendingMessage || !wsRef.current || !selectedThreadId) return;

    setSendingMessage(true);
    setError(null);

    try {
      wsRef.current.send(JSON.stringify({
        content: newMessage
      }));
      
      setNewMessage('');
    } catch (error) {
      console.error('Error sending message:', error);
      setError('Failed to send message');
    } finally {
      setSendingMessage(false);
    }
  };

  const handleStartAgent = async () => {
    if (!selectedThreadId) return;

    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/threads/${selectedThreadId}/start`, {
        method: 'POST'
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log('Agent started:', data);
      await fetchThread(selectedThreadId);
      setError(null);
    } catch (error) {
      console.error('Error starting agent:', error);
      setError('Failed to start agent. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleStopAgent = async () => {
    if (!selectedThreadId) return;

    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/threads/${selectedThreadId}/stop`, {
        method: 'POST'
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log('Agent stopped:', data);
      await fetchThread(selectedThreadId);
      setError(null);
    } catch (error) {
      console.error('Error stopping agent:', error);
      setError('Failed to stop agent. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date.toDateString() === today.toDateString()) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (date.toDateString() === yesterday.toDateString()) {
      return `Yesterday ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    } else {
      return date.toLocaleDateString([], { 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    }
  };

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Thread List Sidebar */}
      <div className="w-80 bg-white border-r flex flex-col">
        <div className="p-4 border-b">
          <h1 className="text-xl font-bold mb-4">Threads</h1>
          <form onSubmit={handleCreateThread}>
            <div className="space-y-2">
              <input
                type="text"
                value={newThreadTitle}
                onChange={(e) => setNewThreadTitle(e.target.value)}
                placeholder="Enter thread title..."
                className="w-full p-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="submit"
                className="w-full px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 focus:outline-none focus:ring-2 focus:ring-green-500"
              >
                Create New Thread
              </button>
            </div>
          </form>
        </div>
        
        <div className="flex-1 overflow-y-auto">
          {threads.map((thread) => (
            <div
              key={thread.id}
              onClick={() => setSelectedThreadId(thread.id)}
              className={`block p-4 border-b hover:bg-gray-50 transition-colors cursor-pointer ${
                selectedThreadId === thread.id ? 'bg-blue-50' : ''
              }`}
            >
              <h2 className="font-semibold">{thread.title}</h2>
              <p className="text-sm text-gray-500">
                {new Date(thread.created_at).toLocaleDateString()}
              </p>
              <p className="text-xs text-gray-400">
                {thread.is_running ? 'Agent Running' : 'Agent Stopped'}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Thread Area */}
      {selectedThreadId ? (
        <div className="flex-1 flex flex-col">
          {/* Thread Header */}
          <div className="p-4 border-b bg-white flex justify-between items-center">
            <div>
              <h2 className="text-xl font-bold">{selectedThread?.title}</h2>
              <p className="text-sm text-gray-500">
                Created {formatTimestamp(selectedThread?.created_at || '')}
              </p>
            </div>
            <div className="space-x-2">
              {selectedThread?.is_running ? (
                <button
                  onClick={handleStopAgent}
                  className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 focus:outline-none focus:ring-2 focus:ring-red-500"
                >
                  Stop Agent
                </button>
              ) : (
                <button
                  onClick={handleStartAgent}
                  className="px-4 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 focus:outline-none focus:ring-2 focus:ring-green-500"
                >
                  Start Agent
                </button>
              )}
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex flex-col ${
                  message.sender === 'user' ? 'items-end' : 'items-start'
                }`}
              >
                <div
                  className={`max-w-3/4 p-3 rounded-lg ${
                    message.sender === 'user'
                      ? 'bg-blue-500 text-white'
                      : message.sender === 'assistant'
                      ? 'bg-gray-200 text-gray-800'
                      : 'bg-green-100 text-gray-800'
                  }`}
                >
                  {message.is_tool_call ? (
                    <div>
                      <p className="font-semibold">{message.content}</p>
                      {message.tool_name && (
                        <p className="text-sm opacity-75">Tool: {message.tool_name}</p>
                      )}
                      {message.tool_args && (
                        <p className="text-sm opacity-75">Args: {message.tool_args}</p>
                      )}
                      {message.tool_result && (
                        <p className="text-sm mt-2">Result: {message.tool_result}</p>
                      )}
                    </div>
                  ) : (
                    <p>{message.content}</p>
                  )}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  {formatTimestamp(message.created_at)} • #{message.sequence_number}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Message Input */}
          <div className="p-4 border-t bg-white">
            <form onSubmit={handleSendMessage}>
              <div className="flex space-x-4">
                <input
                  type="text"
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  placeholder="Type a message..."
                  className="flex-1 p-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  disabled={sendingMessage}
                />
                <button
                  type="submit"
                  className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                  disabled={sendingMessage}
                >
                  Send
                </button>
              </div>
            </form>
            {error && (
              <p className="text-red-500 text-sm mt-2">{error}</p>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-gray-500">
          Select a thread to start messaging
        </div>
      )}
    </div>
  );
};

export default Threads; 