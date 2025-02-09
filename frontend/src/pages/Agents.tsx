import React, { useEffect, useState, useRef } from 'react';
import axios from 'axios';

interface Thread {
  id: number;
  title: string;
  created_at: string;
  updated_at: string | null;
  messages: Message[];
}

interface MessageContent {
  type: string;
  text: string;
}

interface Message {
  role: 'assistant' | 'tool' | 'user' | 'developer';
  content?: string | MessageContent[];
  tool_call_id?: string;
  tool_calls?: Array<{
    function: {
      name: string;
      arguments: string;
    };
  }>;
}

interface WebSocketMessage {
  type: 'assistant' | 'tool_result';
  content?: string | null;
  tool_calls?: Array<{
    name: string;
    arguments: string;
  }>;
  tool?: string;
  result?: any;
}

export default function Agents() {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [selectedThread, setSelectedThread] = useState<Thread | null>(null);
  const [newThreadTitle, setNewThreadTitle] = useState('');
  const [userInput, setUserInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isStartingAgent, setIsStartingAgent] = useState(false);
  const [isAgentRunning, setIsAgentRunning] = useState(false);
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const API_BASE_URL = 'http://localhost:8000';
  const WS_BASE_URL = 'ws://localhost:8000';

  useEffect(() => {
    fetchThreads();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Add polling for thread updates
  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval>;

    const fetchThreadUpdates = async () => {
      if (!selectedThread) return;

      try {
        const response = await axios.get(`${API_BASE_URL}/api/threads/${selectedThread.id}/get_thread`, {
          params: { from_sequence_number: 0 }
        });
        
        setMessages(response.data.messages);
        setIsAgentRunning(response.data.running);
      } catch (error: any) {
        console.error('Error fetching thread updates:', error);
        // Don't show error to user since this is a background poll
      }
    };

    if (selectedThread) {
      // Initial fetch
      fetchThreadUpdates();
      // Set up polling interval
      intervalId = setInterval(fetchThreadUpdates, 1000);
    }

    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [selectedThread]);

  const connectWebSocket = (threadId: number) => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    const ws = new WebSocket(`${WS_BASE_URL}/ws/threads/${threadId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      setMessages(prev => [...prev, message]);
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setError('WebSocket connection error');
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      wsRef.current = null;
    };
  };

  const fetchThreads = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await axios.get(`${API_BASE_URL}/api/threads/list`);
      console.log('Fetched threads:', response.data);
      setThreads(response.data);
    } catch (error: any) {
      console.error('Error fetching threads:', error);
      setError(error.response?.data?.detail || 'Failed to fetch threads. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const createThread = async () => {
    if (!newThreadTitle.trim()) {
      setError('Please enter a thread title');
      return;
    }

    try {
      setIsLoading(true);
      setError(null);
      console.log('Creating thread with title:', newThreadTitle);
      const response = await axios.post(`${API_BASE_URL}/api/threads/create`, {
        title: newThreadTitle
      });
      console.log('Created thread:', response.data);
      setThreads(prevThreads => [response.data, ...prevThreads]);
      setNewThreadTitle('');
    } catch (error: any) {
      console.error('Error creating thread:', error);
      setError(error.response?.data?.detail || 'Failed to create thread. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleThreadSelect = (thread: Thread) => {
    setSelectedThread(thread);
    setMessages([]);
    connectWebSocket(thread.id);
  };

  const startAgent = async () => {
    if (!selectedThread) return;
    
    try {
      setIsStartingAgent(true);
      setError(null);
      const response = await axios.post(`${API_BASE_URL}/api/threads/${selectedThread.id}/start_agent_loop`);
      console.log('Started agent for thread:', selectedThread.id);
      if (response.data.status === "started") {
        setIsAgentRunning(true);
      }
    } catch (error: any) {
      console.error('Error starting agent:', error);
      setError(error.response?.data?.detail || 'Failed to start agent. Please try again.');
    } finally {
      setIsStartingAgent(false);
    }
  };

  const sendUserInput = async () => {
    if (!selectedThread || !userInput.trim() || isAgentRunning) return;
    
    try {
      setIsSendingMessage(true);
      setError(null);
      await axios.post(`${API_BASE_URL}/api/threads/${selectedThread.id}/user_input`, {
        message: userInput
      });
      setUserInput('');
    } catch (error: any) {
      console.error('Error sending message:', error);
      setError(error.response?.data?.detail || 'Failed to send message. Please try again.');
    } finally {
      setIsSendingMessage(false);
    }
  };

  const renderMessage = (message: Message) => {
    const renderContent = (content: string | MessageContent[] | undefined) => {
      if (!content) return null;
      if (typeof content === 'string') return content;
      return content.map((item, index) => (
        <div key={index} className="text-gray-800">
          {item.text}
        </div>
      ));
    };

    switch (message.role) {
      case 'assistant':
        return (
          <div className="bg-blue-50 p-4 rounded-lg mb-4">
            <div className="font-medium text-blue-800">Assistant</div>
            <div className="text-gray-800 mt-2">{renderContent(message.content)}</div>
            {message.tool_calls && message.tool_calls.length > 0 && (
              <div className="mt-2">
                <div className="font-medium text-blue-800">Using tools:</div>
                {message.tool_calls.map((tool, index) => (
                  <div key={index} className="bg-blue-100 p-2 rounded mt-1">
                    <code>{tool.function.name}({tool.function.arguments})</code>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      case 'tool':
        return (
          <div className="bg-green-50 p-4 rounded-lg mb-4">
            <div className="font-medium text-green-800">Tool Result</div>
            <pre className="bg-green-100 p-2 rounded mt-2 overflow-x-auto">
              <code>{renderContent(message.content)}</code>
            </pre>
          </div>
        );
      case 'user':
        return (
          <div className="bg-gray-50 p-4 rounded-lg mb-4">
            <div className="font-medium text-gray-800">User</div>
            <div className="text-gray-800 mt-2">{renderContent(message.content)}</div>
          </div>
        );
      case 'developer':
        return (
          <div className="bg-purple-50 p-4 rounded-lg mb-4">
            <div className="font-medium text-purple-800">Developer</div>
            <div className="text-gray-800 mt-2">{renderContent(message.content)}</div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Thread List Sidebar */}
      <div className="w-1/4 bg-white border-r border-gray-200 p-4">
        <div className="mb-4">
          <div className="flex flex-col gap-2">
            <input
              type="text"
              value={newThreadTitle}
              onChange={(e) => {
                setNewThreadTitle(e.target.value);
                setError(null);
              }}
              onKeyPress={(e) => e.key === 'Enter' && !isLoading && createThread()}
              placeholder="New Thread Title"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={createThread}
              disabled={isLoading || !newThreadTitle.trim()}
              className={`px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                (isLoading || !newThreadTitle.trim()) ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            >
              {isLoading ? 'Creating...' : 'Create'}
            </button>
            {error && (
              <div className="text-red-500 text-sm mt-2">{error}</div>
            )}
          </div>
        </div>
        
        <div className="space-y-2">
          {threads.map((thread) => (
            <div
              key={thread.id}
              onClick={() => handleThreadSelect(thread)}
              className={`p-3 rounded-md cursor-pointer ${
                selectedThread?.id === thread.id
                  ? 'bg-blue-100 border-blue-300'
                  : 'hover:bg-gray-100'
              }`}
            >
              <h3 className="font-medium">{thread.title}</h3>
              <p className="text-sm text-gray-500">
                {new Date(thread.created_at).toLocaleDateString()}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Messages View */}
      <div className="flex-1 flex flex-col h-full">
        {selectedThread ? (
          <>
            <div className="flex justify-between items-center p-4 border-b">
              <h2 className="text-2xl font-bold">{selectedThread.title}</h2>
              {isAgentRunning ? (
                <div className="flex items-center gap-2 px-4 py-2 bg-green-100 text-green-800 rounded-md">
                  <div className="animate-spin h-4 w-4">
                    <svg className="h-full w-full text-green-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                  </div>
                  <span className="font-medium">Agent Running</span>
                </div>
              ) : (
                <button
                  onClick={startAgent}
                  disabled={isStartingAgent}
                  className={`px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 ${
                    isStartingAgent ? 'opacity-50 cursor-not-allowed' : ''
                  }`}
                >
                  {isStartingAgent ? 'Starting Agent...' : 'Start Agent'}
                </button>
              )}
            </div>
            
            <div className="flex-1 overflow-y-auto p-4">
              {messages.map((message, index) => (
                <div key={index}>
                  {renderMessage(message)}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            <div className="p-4 border-t">
              <div className="flex gap-2">
                <textarea
                  value={userInput}
                  onChange={(e) => setUserInput(e.target.value)}
                  onKeyPress={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey && !isSendingMessage) {
                      e.preventDefault();
                      sendUserInput();
                    }
                  }}
                  placeholder={!isAgentRunning ? "Type your message..." : "Please wait for the agent to finish..."}
                  disabled={isAgentRunning || isSendingMessage}
                  className={`flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none h-[50px] ${
                    isAgentRunning ? 'bg-gray-100 cursor-not-allowed' : ''
                  }`}
                />
                <button
                  onClick={sendUserInput}
                  disabled={isAgentRunning || isSendingMessage || !userInput.trim()}
                  className={`px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                    (isAgentRunning || isSendingMessage || !userInput.trim()) ? 'opacity-50 cursor-not-allowed' : ''
                  }`}
                >
                  {isSendingMessage ? 'Sending...' : 'Send'}
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500">
            Select a thread to view messages
          </div>
        )}
      </div>
    </div>
  );
} 